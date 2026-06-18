"""Plant master data — SAP Planning Plant / Maintenance Plant reference codes.

Two flat tables (not a self-referencing hierarchy like activity_master): a
Planning Plant and a Maintenance Plant are genuinely different entity types
with different code formats (4-digit numeric vs 4-letter codes), not two
levels of the same thing. Each Maintenance Plant belongs to exactly one
Planning Plant.

Static reference data (~9 Planning Plants, ~100 Maintenance Plants) seeded
once via `scripts/seed_plants.py`; read-only via the API for now — no admin
CRUD UI yet, since these codes don't change in normal operation.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlanningPlant(Base):
    __tablename__ = "planning_plants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        Index("planning_plants_code_uq", "code", unique=True, postgresql_where=text("is_active = true")),
    )


class MaintenancePlant(Base):
    __tablename__ = "maintenance_plants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    planning_plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planning_plants.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        Index("maintenance_plants_code_uq", "code", unique=True, postgresql_where=text("is_active = true")),
        Index("maintenance_plants_planning_plant_idx", "planning_plant_id"),
    )
