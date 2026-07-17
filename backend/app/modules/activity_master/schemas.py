"""ActivityMaster pydantic schemas."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# NUMERIC / TASK_BASED are LEGACY values kept so historical rows still validate
# on read; new configuration uses the three explicit modes. See
# activity_master/models.py for the behaviour each one implies.
BenchmarkType = Literal[
    "NUMERIC",
    "TASK_BASED",
    "NUMERIC_DAILY",
    "TASK_STATUS_ONLY",
    "TASK_WITH_QUANTITY",
]
RelevantCountField = Literal["tags", "docs", "bom", "spares", "pages", "records"]


class ActivityMasterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_id: uuid.UUID | None
    code: str | None
    name: str
    level: str
    benchmark_type: BenchmarkType | None
    benchmark_value: Decimal | None
    benchmark_period_days: int | None
    benchmark_unit_note: str | None
    benchmark_remarks: str | None
    relevant_count_field: RelevantCountField | None
    is_active: bool
    sort_order: int
    created_at: datetime


class SubActivityFlatOut(BaseModel):
    """Leaf rows flattened with the parent Activity's name — for the work-report
    cascading-select / combobox use case.

    Carries the FULL benchmark configuration, not just the calculation inputs:
    the report form renders the master's own guidance (benchmark_remarks) and
    measurement unit next to the selection. Those two fields were missing here
    while present on the column and on ActivityMasterOut, which is precisely why
    guidance such as "500 REQUIRED PAGES/DAY" never reached the employee."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    activity_id: uuid.UUID
    activity_name: str
    name: str
    benchmark_type: BenchmarkType | None
    benchmark_value: Decimal | None
    benchmark_period_days: int | None
    # Supplementary display text written by the business. benchmark_remarks is
    # the Activity Master's guidance to the employee — NOT the employee's own
    # report remarks (WorkReportTask.description / DailyWorkReport.remarks), and
    # it is read-only on the report page.
    benchmark_unit_note: str | None
    benchmark_remarks: str | None
    # The real, calculation-driving unit. benchmark_unit_note is free text and
    # must never be used as the unit's source.
    relevant_count_field: RelevantCountField | None
    is_active: bool


class ActivityCreate(BaseModel):
    """Top-level Activity. parent_id is implicit (None) — never accepted here."""

    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    sort_order: int = 0
    is_active: bool = True


class SubActivityCreate(BaseModel):
    """Sub-Activity created under a path-param Activity id."""

    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    benchmark_type: BenchmarkType | None = None
    benchmark_value: Decimal | None = Field(default=None, ge=0)
    benchmark_period_days: int | None = Field(default=None, ge=0)
    benchmark_unit_note: str | None = Field(default=None, max_length=100)
    benchmark_remarks: str | None = Field(default=None, max_length=500)
    relevant_count_field: RelevantCountField | None = None
    sort_order: int = 0
    is_active: bool = True

    @model_validator(mode="after")
    def _quantity_modes_require_value_and_count_field(self) -> "SubActivityCreate":
        # Mirrors the DB constraints: every mode that carries a quantity needs a
        # target and a unit to read the actual from. TASK_STATUS_ONLY needs
        # neither. Imported here (not at module import) to keep the schema layer
        # free of a hard dependency on the model at import time.
        from app.modules.activity_master.models import QUANTITY_BENCHMARK_TYPES

        if self.benchmark_type in QUANTITY_BENCHMARK_TYPES:
            if self.benchmark_value is None:
                raise ValueError(
                    f"benchmark_value is required when benchmark_type is "
                    f"{self.benchmark_type}."
                )
            if self.relevant_count_field is None:
                raise ValueError(
                    f"relevant_count_field is required when benchmark_type is "
                    f"{self.benchmark_type} (it's the benchmark's actual-value source)."
                )
        return self


class ActivityMasterUpdate(BaseModel):
    """Shared update shape for both levels. Service rejects benchmark_* edits
    on a level='activity' row (benchmarks only apply to sub-activities)."""

    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    benchmark_type: BenchmarkType | None = None
    benchmark_value: Decimal | None = Field(default=None, ge=0)
    benchmark_period_days: int | None = Field(default=None, ge=0)
    benchmark_unit_note: str | None = Field(default=None, max_length=100)
    benchmark_remarks: str | None = Field(default=None, max_length=500)
    relevant_count_field: RelevantCountField | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class ActivityMasterPage(BaseModel):
    items: list[ActivityMasterOut]
    total: int
    limit: int
    offset: int
