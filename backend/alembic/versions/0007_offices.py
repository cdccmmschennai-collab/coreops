"""0007 offices

Creates the offices table and seeds the three initial branch offices.
Seed is idempotent (INSERT ... ON CONFLICT DO NOTHING).

Revision ID: 0007_offices
Revises: 0006_daily_report_fields
Create Date: 2026-06-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_offices"
down_revision: Union[str, None] = "0006_daily_report_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Seed data — idempotent via ON CONFLICT DO NOTHING.
# Hyderabad shift_end: seeded as 17:30 (interpreted from spec value "05:30"
# which is assumed to mean 17:30 / 5:30 PM — update if incorrect).
_SEED_OFFICES = [
    {
        "name": "Chennai",
        "timezone": "Asia/Kolkata",
        "shift_start": "09:00",
        "shift_end": "17:30",
        "break_minutes": 30,
        "is_active": True,
    },
    {
        "name": "Hyderabad",
        "timezone": "Asia/Kolkata",
        "shift_start": "09:00",
        "shift_end": "17:30",
        "break_minutes": 60,
        "is_active": True,
    },
    {
        "name": "Qatar",
        "timezone": "Asia/Qatar",
        "shift_start": "09:00",
        "shift_end": "18:00",
        "break_minutes": 60,
        "is_active": True,
    },
]


def upgrade() -> None:
    op.create_table(
        "offices",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False),
        sa.Column("shift_start", sa.Time(), nullable=False),
        sa.Column("shift_end", sa.Time(), nullable=False),
        sa.Column(
            "break_minutes", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("offices_name_uq", "offices", ["name"], unique=True)

    # Idempotent seed — values are known at migration write time, so we use
    # literal SQL rather than mixing psycopg parameter styles with ::time casts.
    conn = op.get_bind()
    for office in _SEED_OFFICES:
        conn.execute(
            sa.text(
                "INSERT INTO offices (name, timezone, shift_start, shift_end, break_minutes, is_active) "
                "VALUES (:name, :timezone, CAST(:shift_start AS TIME), CAST(:shift_end AS TIME), "
                ":break_minutes, :is_active) "
                "ON CONFLICT (name) DO NOTHING"
            ).bindparams(
                name=office["name"],
                timezone=office["timezone"],
                shift_start=office["shift_start"],
                shift_end=office["shift_end"],
                break_minutes=office["break_minutes"],
                is_active=office["is_active"],
            )
        )


def downgrade() -> None:
    op.drop_index("offices_name_uq", table_name="offices")
    op.drop_table("offices")
