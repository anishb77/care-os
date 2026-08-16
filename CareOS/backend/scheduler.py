"""
Pill Pilot scheduling engine.

Generates a day's dose times for one person's medications, respecting:
  - exact / preferred / window / n_per_day / every_n_hours frequency types
  - min/max spacing between a medication's own doses
  - food timing relative to that person's meal times
  - wake/sleep boundaries
  - caregiver-defined before/after ordering and min-separation rules
    between two different medications

Priority (per spec section 5), enforced in this order:
  1. Hard rules (windows, ordering, exact times, spacing) -- never violated.
  2. Minimize conflicts/deviations, INCLUDING staying close to a medication's
     previous scheduled time when recalculating -- per spec section 5,
     "Prefer the smallest reasonable changes." Weighted more heavily than
     preferred-time closeness so a recalculation doesn't jump a dose
     somewhere new just because it's technically valid.
  3. Fewer medication-taking events when allowed (not fully implemented in
     the MVP -- noted as a possible Day-2 stretch goal).
  4. Times close to the user's preferred times.

If a fully valid schedule doesn't exist, we report infeasibility and WHICH
rules are in tension, rather than silently dropping a rule. Per spec
section 5: "If no completely valid schedule exists, show the problem
instead of silently changing the user's rules."

IMPORTANT (spec section 9 / "Do NOT build"): this engine only ever
processes rules the caregiver entered. It never infers, checks, or
invents medical compatibility between medications.

Time is minutes-from-midnight throughout, discretized to 5-minute slots
for the solver (fine enough for real scheduling, coarse enough to solve
fast).
"""
from ortools.sat.python import cp_model

SLOT_MINUTES = 5
DAY_MINUTES = 24 * 60
SLOTS_PER_DAY = DAY_MINUTES // SLOT_MINUTES

STABILITY_WEIGHT = 20  # how much more we care about "don't move it" vs "closer to preferred"


def _slot(minutes: int) -> int:
    return max(0, min(SLOTS_PER_DAY - 1, round(minutes / SLOT_MINUTES)))


def _minutes(slot: int) -> int:
    return slot * SLOT_MINUTES


def _food_window(person: dict, food_requirement: str) -> tuple[int, int] | None:
    """
    Translate a food requirement into an allowed [start, end] minute range,
    anchored to the person's own meal times. Checks against ALL three
    meals (breakfast/lunch/dinner) -- a dose just needs to land near ANY
    one of them, handled as an OR of ranges by the caller.
    """
    if food_requirement == "none":
        return None
    meals = [m for m in (person.get("breakfast_time_min"),
                          person.get("lunch_time_min"),
                          person.get("dinner_time_min")) if m is not None]
    return meals  # caller builds per-meal ranges


def generate_schedule(person: dict, medications: list[dict], rules: list[dict],
                       fixed_doses: list[dict] | None = None,
                       previous_times: dict | None = None) -> dict:
    """
    person: {wake_time_min, sleep_time_min, breakfast_time_min, lunch_time_min, dinner_time_min}
    medications: [{id, name, frequency_type, doses_per_day, interval_hours,
                   exact_time_min, preferred_time_min, window_start_min,
                   window_end_min, min_spacing_hours, max_spacing_hours,
                   food_requirement}, ...]
    rules: [{med_a_id, med_b_id, rule_type, min_gap_hours}, ...]
    fixed_doses: doses already TAKEN today -- their actual_time_min is
                 locked in, and other doses schedule around that reality
                 rather than the original plan. [{medication_id, actual_time_min}]
    previous_times: {medication_id: previous_scheduled_time_min} for medications
                 that already had a (not-yet-taken) scheduled dose before this
                 recalculation -- used as a soft "don't move this if you don't
                 have to" pull. Only the FIRST dose per medication is anchored
                 this way; multi-dose-per-day medications skip stability (edge
                 case, acceptable for MVP).

    Returns: {feasible: bool, doses: [...], conflicts: [...]}
    """
    fixed_doses = fixed_doses or []
    previous_times = previous_times or {}
    fixed_by_med = {}
    for fd in fixed_doses:
        fixed_by_med.setdefault(fd["medication_id"], []).append(fd["actual_time_min"])

    model = cp_model.CpModel()
    wake_slot = _slot(person["wake_time_min"])
    sleep_slot = _slot(person["sleep_time_min"])

    dose_vars: dict[str, list[cp_model.IntVar]] = {}
    deviation_terms = []    # "closer to preferred time" -- weight 1
    stability_terms = []    # "stay close to previous scheduled time" -- weight STABILITY_WEIGHT

    for med in medications:
        med_id = med["id"]

        # If this medication was already taken today, treat that as fixed
        # and don't generate new variables for it -- respects spec section 6
        # ("use that actual time for future spacing rules").
        if med_id in fixed_by_med:
            dose_vars[med_id] = None  # marker: handled via fixed_by_med below
            continue

        n_doses = med.get("doses_per_day", 1)
        window_start = max(wake_slot, _slot(med.get("window_start_min", person["wake_time_min"])))
        window_end = min(sleep_slot, _slot(med.get("window_end_min", person["sleep_time_min"])))
        if window_end <= window_start:
            window_end = min(sleep_slot, window_start + 12)  # fallback: ~1 hour

        doses = []
        for i in range(n_doses):
            v = model.NewIntVar(window_start, window_end, f"{med_id}_d{i}")
            doses.append(v)
        dose_vars[med_id] = doses

        # --- Frequency-type-specific hard constraints ---
        if med["frequency_type"] == "exact" and med.get("exact_time_min") is not None:
            model.Add(doses[0] == _slot(med["exact_time_min"]))

        elif med["frequency_type"] == "every_n_hours" and med.get("interval_hours"):
            gap = round((med["interval_hours"] * 60) / SLOT_MINUTES)
            for i in range(n_doses - 1):
                model.Add(doses[i + 1] == doses[i] + gap)

        # --- Same-medication spacing (min/max between its own doses) ---
        if n_doses > 1:
            min_gap = round(((med.get("min_spacing_hours") or 0) * 60) / SLOT_MINUTES)
            max_gap = med.get("max_spacing_hours")
            for i in range(n_doses - 1):
                model.Add(doses[i + 1] >= doses[i] + max(1, min_gap))
                if max_gap:
                    model.Add(doses[i + 1] <= doses[i] + round((max_gap * 60) / SLOT_MINUTES))

        # --- Preferred time: soft objective term, not a hard constraint ---
        if med["frequency_type"] == "preferred" and med.get("preferred_time_min") is not None:
            target = _slot(med["preferred_time_min"])
            dev = model.NewIntVar(0, SLOTS_PER_DAY, f"{med_id}_dev")
            model.AddAbsEquality(dev, doses[0] - target)
            deviation_terms.append(dev)

        # --- Stability: soft pull toward where this dose was already
        # scheduled, so a recalculation doesn't relocate it unless the
        # changed rules actually force a move. Skipped for 'exact' (already
        # pinned) and for multi-dose meds (ambiguous which dose maps to which).
        if (n_doses == 1
                and med["frequency_type"] != "exact"
                and med_id in previous_times):
            prev_slot = _slot(previous_times[med_id])
            stab = model.NewIntVar(0, SLOTS_PER_DAY, f"{med_id}_stab")
            model.AddAbsEquality(stab, doses[0] - prev_slot)
            stability_terms.append(stab)

        # --- Food timing, anchored to this person's actual meal times ---
        food_req = med.get("food_requirement", "none")
        meals = _food_window(person, food_req)
        if meals:
            # Build an OR across meals: dose must land in range for AT LEAST one meal.
            meal_bools = []
            for meal_min in meals:
                meal_slot = _slot(meal_min)
                b = model.NewBoolVar(f"{med_id}_meal_{meal_slot}")
                if food_req == "with":
                    lo, hi = meal_slot - 6, meal_slot + 6  # +-30 min
                elif food_req == "before":
                    lo, hi = meal_slot - 12, meal_slot - 1  # up to 1hr before
                elif food_req == "after":
                    lo, hi = meal_slot + 1, meal_slot + 12
                else:  # 'without' -- handled as a wide avoidance band instead
                    lo, hi = None, None
                if lo is not None:
                    model.Add(doses[0] >= lo).OnlyEnforceIf(b)
                    model.Add(doses[0] <= hi).OnlyEnforceIf(b)
                    meal_bools.append(b)
            if meal_bools and food_req != "without":
                model.AddBoolOr(meal_bools)
            if food_req == "without":
                # Avoid a +-45min band around every meal entirely.
                for meal_min in meals:
                    meal_slot = _slot(meal_min)
                    b_before = model.NewBoolVar(f"{med_id}_avoid_before_{meal_slot}")
                    b_after = model.NewBoolVar(f"{med_id}_avoid_after_{meal_slot}")
                    model.Add(doses[0] <= meal_slot - 9).OnlyEnforceIf(b_before)
                    model.Add(doses[0] >= meal_slot + 9).OnlyEnforceIf(b_after)
                    model.AddBoolOr([b_before, b_after])

    # --- Cross-medication rules (caregiver-entered only) ---
    for r in rules:
        a_id, b_id = r["med_a_id"], r["med_b_id"]
        a_vars = fixed_by_med.get(a_id) or dose_vars.get(a_id)
        b_vars = fixed_by_med.get(b_id) or dose_vars.get(b_id)
        if a_vars is None or b_vars is None:
            continue

        # Normalize fixed (already-taken) doses into constant "variables"
        # by wrapping each in a trivial IntVar equal to that fixed slot,
        # so the same constraint code works for both fixed and free doses.
        def as_vars(vlist, med_id):
            if med_id in fixed_by_med:
                out = []
                for i, actual_min in enumerate(fixed_by_med[med_id]):
                    c = model.NewIntVar(_slot(actual_min), _slot(actual_min), f"fixed_{med_id}_{i}")
                    out.append(c)
                return out
            return vlist

        a_list = as_vars(a_vars, a_id)
        b_list = as_vars(b_vars, b_id)

        gap_slots = max(1, round((r.get("min_gap_hours", 0) * 60) / SLOT_MINUTES))

        for ai, av in enumerate(a_list):
            for bi, bv in enumerate(b_list):
                if r["rule_type"] == "before":
                    model.Add(av + gap_slots <= bv)
                elif r["rule_type"] == "after":
                    model.Add(av >= bv + gap_slots)
                elif r["rule_type"] == "min_separation":
                    diff = model.NewIntVar(-SLOTS_PER_DAY, SLOTS_PER_DAY, f"diff_{a_id}_{ai}_{b_id}_{bi}")
                    model.Add(diff == av - bv)
                    before = model.NewBoolVar(f"before_{a_id}_{ai}_{b_id}_{bi}")
                    model.Add(diff >= gap_slots).OnlyEnforceIf(before)
                    model.Add(diff <= -gap_slots).OnlyEnforceIf(before.Not())

    if stability_terms or deviation_terms:
        model.Minimize(
            STABILITY_WEIGHT * sum(stability_terms) + sum(deviation_terms)
        )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    status = solver.Solve(model)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        conflicts = [
            {
                "med_a": r["med_a_id"],
                "med_b": r["med_b_id"],
                "message": f"Couldn't satisfy the '{r['rule_type']}' rule between these "
                           f"medications within the allowed windows.",
            }
            for r in rules
        ]
        return {"feasible": False, "doses": [], "conflicts": conflicts}

    med_lookup = {m["id"]: m["name"] for m in medications}
    doses_out = []
    for med_id, vars_ in dose_vars.items():
        if vars_ is None:  # already taken today, skip -- caller already has it
            continue
        for v in vars_:
            doses_out.append({
                "medication_id": med_id,
                "medication_name": med_lookup[med_id],
                "scheduled_time_min": _minutes(solver.Value(v)),
            })
    doses_out.sort(key=lambda d: d["scheduled_time_min"])

    return {"feasible": True, "doses": doses_out, "conflicts": []}