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

    IMPORTANT -- relative-time model: every clock time in this function
    (window bounds, exact/preferred times, meal times, fixed/previous
    doses) is converted into "minutes since this person's wake time"
    before being handed to the solver, and converted back to a normal
    clock time on the way out. This lets a bedtime that falls after
    midnight (e.g. wake 8:00 AM, sleep 1:00 AM the next day) work as one
    continuous awake window instead of being mathematically impossible --
    absolute clock time alone can't express "8:00 AM to 1:00 AM" as a
    single increasing range, since 1:00 AM (60) is numerically less than
    8:00 AM (480).

    Returns: {feasible: bool, doses: [...], conflicts: [...]}
    """
    fixed_doses = fixed_doses or []
    previous_times = previous_times or {}
    fixed_by_med = {}
    for fd in fixed_doses:
        fixed_by_med.setdefault(fd["medication_id"], []).append(fd["actual_time_min"])

    wake_min = person["wake_time_min"]
    sleep_min = person["sleep_time_min"]

    def to_relative_minutes(abs_min: int) -> int:
        """
        Clock time -> minutes since wake, wrapping across midnight. If
        abs_min is at/after wake_min it's simply abs_min - wake_min; if
        it's "earlier" in raw clock terms (e.g. sleep_min = 1:00 AM = 60
        while wake_min = 8:00 AM = 480), the modulo pushes it past
        midnight into the next day's relative timeline instead.
        """
        return (abs_min - wake_min) % DAY_MINUTES

    def to_relative_slot(abs_min: int) -> int:
        return _slot(to_relative_minutes(abs_min))

    def from_relative_minutes(rel_min: int) -> int:
        """Inverse of to_relative_minutes -- back to a normal clock time."""
        return (wake_min + rel_min) % DAY_MINUTES

    model = cp_model.CpModel()
    wake_slot = 0  # by definition, relative to itself
    sleep_slot = to_relative_slot(sleep_min)  # length of the awake window, in slots

    if sleep_slot <= wake_slot:
        # Wake and sleep resolve to the same instant -- zero-length day.
        # Nothing is schedulable; every medication is a conflict.
        conflicts = [{
            "med_a": None,
            "med_b": None,
            "message": "This person's wake and sleep times leave no time awake to schedule anything.",
        }]
        return {"feasible": False, "doses": [], "conflicts": conflicts}

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

        # 'exact' medications aren't bounded by window_start_min/window_end_min at
        # all -- that field is only meaningful for window/n_per_day/every_n_hours
        # and is hidden in the UI for 'exact', but the form still sends its
        # leftover default value. Using it here would silently clamp the dose
        # variable's domain and make ANY exact time outside that default
        # (e.g. a bedtime or early-morning medication) mathematically
        # infeasible, regardless of any caregiver rules.
        if med["frequency_type"] == "exact":
            window_start = wake_slot
            window_end = sleep_slot
        else:
            window_start = max(wake_slot, to_relative_slot(med.get("window_start_min", wake_min)))
            window_end = min(sleep_slot, to_relative_slot(med.get("window_end_min", sleep_min)))
            if window_end <= window_start:
                window_end = min(sleep_slot, window_start + 12)  # fallback: ~1 hour

        doses = []
        for i in range(n_doses):
            v = model.NewIntVar(window_start, window_end, f"{med_id}_d{i}")
            doses.append(v)
        dose_vars[med_id] = doses

        # --- Frequency-type-specific hard constraints ---
        if med["frequency_type"] == "exact" and med.get("exact_time_min") is not None:
            model.Add(doses[0] == to_relative_slot(med["exact_time_min"]))

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
            target = to_relative_slot(med["preferred_time_min"])
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
            prev_slot = to_relative_slot(previous_times[med_id])
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
                meal_slot = to_relative_slot(meal_min)
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
                    meal_slot = to_relative_slot(meal_min)
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
                    rel_slot = to_relative_slot(actual_min)
                    c = model.NewIntVar(rel_slot, rel_slot, f"fixed_{med_id}_{i}")
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
        if not conflicts:
            # No cross-medication rules were involved -- infeasibility comes
            # from one or more medications' own constraints (e.g. a food
            # requirement that can't fit inside the allowed window, or
            # doses_per_day * min_spacing exceeding the window). Surface
            # which medications so the caregiver isn't staring at nothing.
            med_names = ", ".join(m["name"] for m in medications)
            conflicts = [{
                "med_a": None,
                "med_b": None,
                "message": (
                    f"Couldn't fit a valid time for: {med_names}. Check that "
                    f"each medication's allowed window is wide enough for its "
                    f"frequency, dose count, and food requirement."
                ),
            }]
        return {"feasible": False, "doses": [], "conflicts": conflicts}

    med_lookup = {m["id"]: m["name"] for m in medications}
    doses_out = []
    for med_id, vars_ in dose_vars.items():
        if vars_ is None:  # already taken today, skip -- caller already has it
            continue
        for v in vars_:
            rel_minutes = _minutes(solver.Value(v))
            doses_out.append({
                "medication_id": med_id,
                "medication_name": med_lookup[med_id],
                "scheduled_time_min": from_relative_minutes(rel_minutes),
            })
    doses_out.sort(key=lambda d: to_relative_minutes(d["scheduled_time_min"]))

    return {"feasible": True, "doses": doses_out, "conflicts": []}
