"""ActivityMaster pydantic schemas."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

BenchmarkType = Literal["NUMERIC", "TASK_BASED"]
RelevantCountField = Literal["tags", "docs", "bom", "spares"]


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
    cascading-select / combobox use case."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    activity_id: uuid.UUID
    activity_name: str
    name: str
    benchmark_type: BenchmarkType | None
    benchmark_value: Decimal | None
    benchmark_period_days: int | None
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
    def _numeric_requires_value_and_count_field(self) -> "SubActivityCreate":
        if self.benchmark_type == "NUMERIC":
            if self.benchmark_value is None:
                raise ValueError("benchmark_value is required when benchmark_type is NUMERIC.")
            if self.relevant_count_field is None:
                raise ValueError(
                    "relevant_count_field is required when benchmark_type is NUMERIC "
                    "(it's the benchmark's actual-value source)."
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
