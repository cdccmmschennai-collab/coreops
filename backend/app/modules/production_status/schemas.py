"""Production Status pydantic schemas.

The read schema is deliberately flat and fully resolved: project/plant labels,
the activity name and the author's full name are all included, so a client
never has to turn a user id into a person or a project id into a plant.
"""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Mirrors VALID_PRODUCTION_STATUSES in models.py; kept as a Literal so an
# unknown status is rejected as a 422 by FastAPI before it reaches the service.
ProductionStatusValue = Literal["in_progress", "closed"]


class ProductionStatusCreate(BaseModel):
    # Project is NEVER supplied in the body - it comes from the path, which is
    # what the caller is authorized against. Plant information is derived from
    # the project, so it is not accepted here either.
    revision: str = Field(min_length=1, max_length=50)

    # The activity, named exactly ONE of two ways (see models.py and migration
    # 0072). `activity_id` picks an Activity Master activity; `activity_label`
    # is a name a Project Head typed for an activity that is not in Activity
    # Master and deliberately never enters it. Sending both, or neither, is a
    # 422 - see `_exactly_one_activity`.
    activity_id: uuid.UUID | None = None
    activity_label: str | None = Field(default=None, max_length=200)
    # The Maintenance Plant this update belongs to. OPTIONAL: a project whose
    # Planning Plant has no Maintenance Plants simply has none to offer, and the
    # form must not be blocked by that. Validated in the service against the
    # plants the project's Planning Plant actually has - it is never derived
    # from the Planning Plant, and never guessed.
    maintenance_plant_id: uuid.UUID | None = None
    status: ProductionStatusValue
    # Four independent units; same `default=0, ge=0` convention the work report
    # task schema uses for its counts.
    tag_count: int = Field(default=0, ge=0)
    doc_count: int = Field(default=0, ge=0)
    spares_count: int = Field(default=0, ge=0)
    crs_count: int = Field(default=0, ge=0)
    completed_on: date | None = None
    remarks: str | None = None

    @model_validator(mode="after")
    def _exactly_one_activity(self) -> "ProductionStatusCreate":
        """An update is about ONE activity, named once.

        Rejected here rather than left to the database's CHECK so a client gets
        a 422 that says what is wrong, instead of a 500 from a constraint
        violation. A label of only whitespace is not a name.
        """
        label = (self.activity_label or "").strip()
        if self.activity_id is not None and label:
            raise ValueError(
                "Choose an existing activity or type a new one, not both."
            )
        if self.activity_id is None and not label:
            raise ValueError("An activity is required.")
        # Normalised once, here, so the service and the database both see the
        # trimmed value and a stored label never carries stray whitespace.
        self.activity_label = label or None
        return self


class ProductionStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID

    # --- project (derived from the project, never entered) -----------------
    project_id: uuid.UUID
    project_code: str | None = None
    project_name: str
    # The project's own Planning Plant. Context only: it is what scopes the
    # Maintenance Plant dropdown, and it is NEVER shown as this record's plant.
    planning_plant_code: str | None = None
    planning_plant_description: str | None = None

    # --- maintenance plant: THIS RECORD's selection (migration 0071) -------
    # Resolved from `maintenance_plant_id` on the row, not from the project.
    # All three are null when no plant was chosen, which is a normal state and
    # is never filled in from the Planning Plant.
    maintenance_plant_id: uuid.UUID | None = None
    maintenance_plant_code: str | None = None
    maintenance_plant_description: str | None = None

    revision: str

    # --- activity ---------------------------------------------------------
    # Null when the activity was typed rather than chosen (migration 0072).
    activity_id: uuid.UUID | None = None
    # Resolved from Activity Master when there is an id, else the typed label.
    # A client renders THIS and never has to know which kind of row it is on.
    activity_name: str | None = None
    activity_code: str | None = None
    # The typed name itself, null for an Activity Master activity. Carried so a
    # client can tell the two apart when it needs to (the form re-selecting a
    # value), never so it has to combine them for display.
    activity_label: str | None = None

    status: str
    tag_count: int
    doc_count: int
    spares_count: int
    crs_count: int
    completed_on: date | None = None
    remarks: str | None = None

    # --- author: the real person, resolved server-side --------------------
    created_by: uuid.UUID
    created_by_name: str = ""
    created_at: datetime


# ---------------------------------------------------------------------------
# PM cumulative report (Phase 4)
# ---------------------------------------------------------------------------


class ProductionStatusReportRow(BaseModel):
    """One line of the PM's cumulative report - the latest update for one
    project + revision + activity.

    Deliberately a FLAT, fully-rendered row rather than `ProductionStatusOut`:
    the same dict is serialised to the browser and rendered into the .xlsx, so
    every cell that needs a decision (which plant label, which status wording,
    which serial number) is decided once here on the server. A client that
    formatted these itself would be a second implementation of the report, and
    the preview and the file could then disagree.

    What is NOT rendered: the four counts stay integers and `completed_on` stays
    a date, because Excel must receive real numbers and a real date to filter,
    sort and sum them. Formatting those is each renderer's job, the VALUE is
    not.
    """

    model_config = ConfigDict(from_attributes=True)

    # 1-based, stamped from the report's single ordering - so the preview's
    # S.NO and the workbook's S.NO are the same number for the same row.
    serial: int

    # The underlying production status record, so a client can key rows on
    # something stable without inventing a composite key.
    id: uuid.UUID

    project_id: uuid.UUID
    project_code: str | None = None
    # The rendered "PROJECT / PLANT" cell - project, this record's Maintenance
    # Plant and the revision combined into one clean string (see
    # service._project_plant_display). One field, not a second project/plant
    # record, and never containing "null", "-" or a dangling separator.
    project_plant: str
    # The parts behind that cell, for a client that needs them individually.
    # Null when no plant was chosen.
    maintenance_plant_id: uuid.UUID | None = None
    maintenance_plant_code: str | None = None

    # Kept in the dataset even though the workbook no longer gives it a column
    # of its own: revision is part of what identifies a production status row
    # (project + revision + activity) and of how its history is looked up, so
    # dropping it from the payload would break far more than a column heading.
    revision: str

    # Null when the activity was typed rather than chosen (migration 0072).
    activity_id: uuid.UUID | None = None
    # The rendered ACTIVITY cell: the Activity Master name (else its code), or
    # the typed label. ONE column - the report never says which kind it was.
    activity: str

    # The stored value ('in_progress' / 'closed') AND its display wording. The
    # vocabulary is unchanged; `status_label` is only how it reads.
    status: str
    status_label: str

    # Four independent units. Never summed, never combined into one column.
    tag_count: int
    doc_count: int
    spares_count: int
    crs_count: int

    # Null when the update has not completed. No date is ever invented.
    completed_on: date | None = None
    # Exactly what the author typed - never truncated.
    remarks: str | None = None
    # The real person's name, resolved server-side. Never a role word.
    by: str = ""


class ProductionStatusReportOut(BaseModel):
    generated_at: datetime

    # --- month filter (Phase 5) -------------------------------------------
    # The month this dataset was built for ("2026-08"), echoed back so a client
    # can tell which report it is holding. Null is the cumulative all-months
    # report - the original, unfiltered behaviour.
    month: str | None = None
    # Every month that has production status records, ascending ("2026-08",
    # "2026-09", ...). Derived from all records rather than from the rows below,
    # so the choice on offer does not shrink to the month already selected. Sent
    # with the report itself rather than from a second endpoint - one request
    # still answers the whole dialog.
    months: list[str] = []

    # Describes `rows` and nothing else: when a month is selected this is that
    # month's count, which is what the screen shows and what the file contains.
    row_count: int
    rows: list[ProductionStatusReportRow]
