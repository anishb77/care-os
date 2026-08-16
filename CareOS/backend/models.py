"""Pydantic request/response models, matching the spec's core data model:
Person, Medication, Dose. A Medication is rules; a Dose is one event."""
from pydantic import BaseModel
from typing import Optional
from datetime import date


class GenerateScheduleRequest(BaseModel):
    person_id: str
    dose_date: Optional[date] = None  # defaults to today in the endpoint


class MarkTakenRequest(BaseModel):
    dose_id: str
    actual_time_min: int  # minutes-from-midnight when it was actually taken


class MarkMissedRequest(BaseModel):
    dose_id: str


class DoseOut(BaseModel):
    medication_id: str
    medication_name: str
    scheduled_time_min: int


class ScheduleResult(BaseModel):
    feasible: bool
    doses: list[dict]
    conflicts: list[dict]
