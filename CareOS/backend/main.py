"""
Pill Pilot backend.

Two responsibilities:
  1. Generate today's schedule for a person (POST /schedule/generate).
  2. Handle the dynamic loop: mark a dose taken/missed, then recalculate
     the REMAINING doses for that day around what actually happened
     (POST /doses/{id}/taken, POST /doses/{id}/missed).

Per spec section 9, this service never evaluates medical compatibility,
never invents interactions, and never recommends dosage changes -- it
only arranges caregiver-provided rules into a schedule.

Plain CRUD (add/edit people, medications, rules) is expected to happen
directly from Next.js against Supabase -- it doesn't need to touch this
backend at all. This backend is specifically the Scheduling Engine
surface, per the architecture in spec section 10.
"""
import os
from datetime import date, datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from supabase import create_client, Client

from models import GenerateScheduleRequest, MarkTakenRequest, MarkMissedRequest
from scheduler import generate_schedule

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

app = FastAPI(title="Pill Pilot Scheduling Engine")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


def _fetch_person_meds_rules(person_id: str):
    person_resp = supabase.table("people").select("*").eq("id", person_id).single().execute()
    person = person_resp.data
    if not person:
        raise HTTPException(404, "Person not found")

    meds_resp = supabase.table("medications").select("*").eq("person_id", person_id).execute()
    medications = meds_resp.data
    if not medications:
        raise HTTPException(404, "This person has no medications yet")

    med_ids = [m["id"] for m in medications]
    rules_resp = supabase.table("med_rules").select("*").in_("med_a_id", med_ids).execute()
    rules = rules_resp.data

    return person, medications, rules


def _is_med_active(med: dict, target_date: date) -> bool:
    """
    A medication is only scheduled on days it's actually active:
      - on/after its start_date
      - on/before its end_date, if one is set (null end_date = ongoing/indefinite)
      - on one of its days_of_week, if set (null/empty = every day)

    days_of_week uses 0 = Sunday ... 6 = Saturday (set from the frontend's
    day-toggle buttons). Python's date.weekday() is Monday=0..Sunday=6, so
    it's converted to match that convention below.
    """
    start_date = med.get("start_date")
    if start_date:
        start = start_date if isinstance(start_date, date) else datetime.fromisoformat(str(start_date)).date()
        if target_date < start:
            return False

    end_date = med.get("end_date")
    if end_date:
        end = end_date if isinstance(end_date, date) else datetime.fromisoformat(str(end_date)).date()
        if target_date > end:
            return False

    days_of_week = med.get("days_of_week")
    if days_of_week:
        # Python: Mon=0..Sun=6  ->  convert to Sun=0..Sat=6
        today_dow = (target_date.weekday() + 1) % 7
        if today_dow not in days_of_week:
            return False

    return True


@app.post("/schedule/generate")
def generate_today_schedule(req: GenerateScheduleRequest):
    """
    Builds/rebuilds today's schedule. Safe to call at any point in the
    day -- if some doses were already taken, those actual times are
    treated as fixed anchors (see _solve_and_save), so this is really
    "generate" and "recalculate everything" unified into one call.
    """
    target_date = req.dose_date or date.today()
    return _solve_and_save(req.person_id, target_date)


@app.post("/schedule/recalculate")
def recalculate_schedule(req: GenerateScheduleRequest):
    """
    Call this any time the INPUTS to the schedule change and today's plan
    might no longer fit -- a medication was added, edited, or deleted, or
    a med_rule was added/edited/deleted. Same underlying logic as
    /schedule/generate; this is just the explicit "something changed,
    re-check everything" entry point the frontend should hit right after
    any Supabase write to medications/med_rules.

    If the new rules make today unsolvable, nothing in the `doses` table
    is touched and the conflict is returned so the caregiver sees exactly
    what's wrong -- per spec section 5, we never silently drop a rule to
    make it fit.
    """
    target_date = req.dose_date or date.today()
    return _solve_and_save(req.person_id, target_date)


@app.get("/schedule/today/{person_id}")
def get_today(person_id: str, dose_date: date | None = None):
    """Returns today's doses for a person, sorted by time, for the Today screen."""
    target_date = dose_date or date.today()
    meds_resp = supabase.table("medications").select("id,name").eq("person_id", person_id).execute()
    med_lookup = {m["id"]: m["name"] for m in meds_resp.data}
    med_ids = list(med_lookup.keys())
    if not med_ids:
        return {"doses": []}

    doses_resp = supabase.table("doses").select("*") \
        .in_("medication_id", med_ids) \
        .eq("dose_date", str(target_date)) \
        .execute()

    doses = doses_resp.data
    for d in doses:
        d["medication_name"] = med_lookup.get(d["medication_id"], "Unknown")
    doses.sort(key=lambda d: d.get("actual_time_min") or d["scheduled_time_min"])
    return {"doses": doses}


@app.post("/doses/{dose_id}/taken")
def mark_taken(dose_id: str, req: MarkTakenRequest):
    """
    Records the actual time a dose was taken, then recalculates the
    REST of that day's not-yet-taken doses around that reality --
    per spec section 6: "Use that actual time for future spacing rules."
    """
    dose_resp = supabase.table("doses").select("*").eq("id", dose_id).single().execute()
    dose = dose_resp.data
    if not dose:
        raise HTTPException(404, "Dose not found")

    supabase.table("doses").update({
        "actual_time_min": req.actual_time_min,
        "status": "taken",
    }).eq("id", dose_id).execute()

    med_resp = supabase.table("medications").select("person_id").eq("id", dose["medication_id"]).single().execute()
    return _solve_and_save(med_resp.data["person_id"], dose["dose_date"])


@app.post("/doses/{dose_id}/missed")
def mark_missed(dose_id: str, req: MarkMissedRequest):
    """Marks a dose missed and recalculates the rest of the day's schedule."""
    dose_resp = supabase.table("doses").select("*").eq("id", dose_id).single().execute()
    dose = dose_resp.data
    if not dose:
        raise HTTPException(404, "Dose not found")

    supabase.table("doses").update({"status": "missed"}).eq("id", dose_id).execute()

    med_resp = supabase.table("medications").select("person_id").eq("id", dose["medication_id"]).single().execute()
    return _solve_and_save(med_resp.data["person_id"], dose["dose_date"])


@app.get("/schedule/week/{person_id}")
def get_week(person_id: str, start_date: date | None = None):
    """
    Returns a 7-day view starting from start_date (defaults to today).
    For each day in the range, generates/loads that day's schedule using
    the exact same _solve_and_save logic as the single-day endpoints --
    no separate week-solving model, since every rule in this system
    (min_separation, before/after) is a same-day constraint per the
    schema, so each day can be solved independently.

    Returns: {days: [{date, feasible, doses, conflicts}, ...]}
    """
    range_start = start_date or date.today()
    days_out = []

    for offset in range(7):
        target_date = range_start + timedelta(days=offset)
        try:
            result = _solve_and_save(person_id, target_date)
        except HTTPException as e:
            # e.g. "This person has no medications yet" -- treat as an
            # empty-but-valid day rather than failing the whole week.
            result = {"feasible": True, "doses": [], "conflicts": [], "message": str(e.detail)}
        days_out.append({
            "date": str(target_date),
            "feasible": result.get("feasible", True),
            "doses": result.get("doses", []),
            "conflicts": result.get("conflicts", []),
        })

    return {"days": days_out}


def _solve_and_save(person_id: str, dose_date) -> dict:
    """
    The single source of truth for "what should today look like right now."
    Used by /schedule/generate, /schedule/recalculate, /schedule/week, and
    after every taken/missed update. Handles ALL of these cases correctly
    by always re-deriving from current state rather than patching
    incrementally:

      - First-ever generation for the day (no doses exist yet)
      - A new medication was just added mid-day (some doses already taken)
      - A medication/rule was edited or deleted
      - A dose was just marked taken (locks in its actual time as an anchor)
      - A dose was just marked missed (excluded, nothing to anchor)

    Medications with a 'taken' dose today keep that fixed actual time and
    are NOT rescheduled. Medications with a 'missed' dose today are also
    excluded (that dose is gone for today). Everything else -- including
    a medication that has no dose row yet because it was just added --
    gets (re)scheduled together, so a newly added medication can shift
    other not-yet-taken doses to make room, and vice versa.

    Medications that aren't ACTIVE on this date at all (outside their
    start/end date range, or today's weekday isn't one of their
    days_of_week) are filtered out before any of the above -- they simply
    don't get a dose generated for this day, no conflict, nothing to solve.

    Recalculation is anchored to each medication's PREVIOUS scheduled time
    (via previous_times) so a Taken/Missed action or a newly added
    medication doesn't cause unrelated doses to relocate unless a rule
    genuinely requires it -- see scheduler.py's stability objective.

    If the resulting set of rules has no valid solution, the `doses`
    table is left untouched and the conflict is returned as-is -- per
    spec section 5, we surface the problem instead of guessing which
    rule to break.
    """
    dose_date_str = str(dose_date)
    target_date = dose_date if isinstance(dose_date, date) else datetime.fromisoformat(dose_date_str).date()

    person, all_medications, all_rules = _fetch_person_meds_rules(person_id)

    # Only medications actually active on this date go anywhere near the solver.
    medications = [m for m in all_medications if _is_med_active(m, target_date)]
    med_ids = {m["id"] for m in medications}
    rules = [r for r in all_rules if r["med_a_id"] in med_ids and r["med_b_id"] in med_ids]

    if not medications:
        return {"feasible": True, "doses": [], "conflicts": [], "message": "No medications are active on this date"}

    existing_resp = supabase.table("doses").select("*") \
        .in_("medication_id", list(med_ids)) \
        .eq("dose_date", dose_date_str) \
        .execute()
    existing = existing_resp.data

    fixed_doses = [
        {"medication_id": d["medication_id"], "actual_time_min": d["actual_time_min"]}
        for d in existing
        if d["status"] == "taken" and d["actual_time_min"] is not None
    ]
    resolved_med_ids = {d["medication_id"] for d in existing if d["status"] in ("taken", "missed")}

    to_schedule = [m for m in medications if m["id"] not in resolved_med_ids]
    if not to_schedule:
        return {"feasible": True, "doses": [], "conflicts": [], "message": "Nothing left to schedule today"}

    # Anchor recalculation to where each medication was ALREADY scheduled
    # (not yet taken/missed) before this run, so a Taken/Missed action or
    # a new medication doesn't cause unrelated doses to relocate unless a
    # rule genuinely requires it. Only single-dose medications get this
    # treatment (see scheduler.py's docstring on previous_times).
    previous_times = {
        d["medication_id"]: d["scheduled_time_min"]
        for d in existing
        if d["status"] == "scheduled"
    }

    result = generate_schedule(person, to_schedule, rules, fixed_doses=fixed_doses, previous_times=previous_times)

    if not result["feasible"]:
        # IMPORTANT: don't touch the doses table. The caregiver sees the
        # conflict and the previous (still-consistent) schedule stays put
        # rather than being replaced with something broken or partial.
        return result

    to_schedule_ids = [m["id"] for m in to_schedule]
    supabase.table("doses").delete() \
        .in_("medication_id", to_schedule_ids) \
        .eq("dose_date", dose_date_str) \
        .eq("status", "scheduled") \
        .execute()

    rows = [
        {
            "medication_id": d["medication_id"],
            "dose_date": dose_date_str,
            "scheduled_time_min": d["scheduled_time_min"],
            "status": "scheduled",
        }
        for d in result["doses"]
    ]
    if rows:
        supabase.table("doses").insert(rows).execute()

    return result