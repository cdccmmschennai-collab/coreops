"""0060 work report periods (Full-Day / Split-Day architecture)

Additive-only foundation for split-day reporting. One daily_work_reports header
per (employee, report_date) is UNCHANGED — the emp+date unique constraint is
kept; a report now owns one or two work_report_periods child rows instead of
two headers:

  report_mode = 'full_day'  -> exactly one 'full_day' period
  report_mode = 'split_day' -> exactly 'first_half' + 'second_half'

Schema changes (all additive; nothing dropped, nothing rewritten in place):

1. daily_work_reports  + report_mode VARCHAR(20) NOT NULL DEFAULT 'full_day'
   (VARCHAR + CHECK, following the activity_requests.status precedent — no new
   Postgres enum type to manage).
2. NEW TABLE work_report_periods — one reporting period of a report.
   period_status / location reuse the EXISTING day_status / work_location enum
   types so periods and headers stay one taxonomy. work_fraction is
   server-derived (1.0 full day, 0.5 per half) and CHECK-limited to those two
   values. is_legacy_half_day marks periods backfilled from historical
   half_day reports (see below).
3. work_report_tasks   + period_id -> work_report_periods (CASCADE), indexed.
4. work_report_tasks   + benchmark_base_value_snapshot / benchmark_fraction_snapshot.
   The existing benchmark_value_snapshot KEEPS its meaning: the effective
   target after applying the period fraction. The two new columns record how
   it was derived (base x fraction), frozen at submit time.
5. activity_requests   + period_id -> work_report_periods (SET NULL), indexed,
   so an approved additional activity lands in the correct period.

Backfill (idempotent by construction — every statement is guarded by
"NOT EXISTS" / "IS NULL" predicates, so re-running cannot duplicate or
double-scale anything):

  * Every existing report gets ONE 'full_day' period copying its day_status ->
    period_status and location. Period remarks stay NULL — day remarks remain
    a header-level field; per-period remarks are new data.
  * Historical day_status = 'half_day' reports: we deliberately DO NOT guess
    whether the worked half was first or second. The period stays a 'full_day'
    (legacy) period with work_fraction = 0.5 and is_legacy_half_day = TRUE,
    preserving the report's current effective half-day benchmark.
  * Every work_report_tasks row is linked to its report's period.
  * Task rows with a frozen benchmark_value_snapshot get their base/fraction
    snapshots derived: fraction = 0.5 on a half_day report else 1.0;
    base = effective / fraction (x2 on a half day). The effective snapshot
    itself is NEVER touched.
  * Activity requests linked to a report point at that report's period.

Downgrade drops the additions in reverse order. Period rows (and any
period-level data created after upgrade) are lost on downgrade — headers, task
rows, requests and every pre-existing column survive untouched, which is as
reversible as an additive child table can be.

Revision ID: 0060_work_report_periods
Revises: 0059_activity_req_pages_records
Create Date: 2026-07-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision: str = "0060_work_report_periods"
down_revision: Union[str, None] = "0059_activity_req_pages_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Header mode. Server default keeps every legacy writer valid.
    op.add_column(
        "daily_work_reports",
        sa.Column(
            "report_mode",
            sa.String(length=20),
            nullable=False,
            server_default="full_day",
        ),
    )
    op.create_check_constraint(
        "work_reports_report_mode_valid",
        "daily_work_reports",
        "report_mode IN ('full_day', 'split_day')",
    )

    # 2. Periods. Existing enum types are REFERENCED, never created/dropped here.
    op.create_table(
        "work_report_periods",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("daily_work_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("day_part", sa.String(length=20), nullable=False),
        sa.Column(
            "period_status",
            postgresql.ENUM(name="day_status", create_type=False),
            nullable=True,
        ),
        sa.Column(
            "location",
            postgresql.ENUM(name="work_location", create_type=False),
            nullable=True,
        ),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("work_fraction", sa.Numeric(3, 2), nullable=False),
        sa.Column(
            "is_legacy_half_day",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "day_part IN ('full_day', 'first_half', 'second_half')",
            name="work_report_periods_day_part_valid",
        ),
        sa.CheckConstraint(
            "work_fraction IN (0.5, 1.0)",
            name="work_report_periods_fraction_valid",
        ),
        sa.UniqueConstraint(
            "report_id", "day_part", name="work_report_periods_report_part_uq"
        ),
    )
    op.create_index(
        "work_report_periods_report_idx", "work_report_periods", ["report_id"]
    )

    # 3. Task -> period link.
    op.add_column(
        "work_report_tasks",
        sa.Column(
            "period_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "work_report_periods.id",
                name="work_report_tasks_period_id_fkey",
                ondelete="CASCADE",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "work_report_tasks_period_idx", "work_report_tasks", ["period_id"]
    )

    # 4. Benchmark derivation snapshots (effective snapshot column untouched).
    op.add_column(
        "work_report_tasks",
        sa.Column("benchmark_base_value_snapshot", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "work_report_tasks",
        sa.Column("benchmark_fraction_snapshot", sa.Numeric(3, 2), nullable=True),
    )

    # 5. Activity request -> period link.
    op.add_column(
        "activity_requests",
        sa.Column(
            "period_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "work_report_periods.id",
                name="activity_requests_period_id_fkey",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "activity_requests_period_idx", "activity_requests", ["period_id"]
    )

    # --- backfill --------------------------------------------------------
    backfill(op.get_bind())


def backfill(bind) -> None:
    """The data half of 0060, callable from tests against synthetic
    pre-period rows (0058 precedent). Idempotent: every statement is guarded
    by NOT EXISTS / IS NULL predicates, so re-running cannot duplicate a
    period, relink a row, or double-scale a snapshot."""
    # One legacy full_day period per existing report. Historical half_day
    # reports keep their effective half benchmark via work_fraction = 0.5 and
    # are flagged is_legacy_half_day — the worked half is never guessed.
    bind.execute(
        text(
            """
            INSERT INTO work_report_periods
                (report_id, day_part, period_status, location, work_fraction,
                 is_legacy_half_day, created_at, updated_at)
            SELECT r.id,
                   'full_day',
                   r.day_status,
                   r.location,
                   CASE WHEN r.day_status = 'half_day' THEN 0.5 ELSE 1.0 END,
                   (r.day_status = 'half_day') IS TRUE,
                   now(),
                   now()
            FROM daily_work_reports r
            WHERE NOT EXISTS (
                SELECT 1 FROM work_report_periods p WHERE p.report_id = r.id
            )
            """
        )
    )

    # Link every task row to its report's (single) period.
    bind.execute(
        text(
            """
            UPDATE work_report_tasks t
            SET period_id = p.id
            FROM work_report_periods p
            WHERE p.report_id = t.report_id
              AND t.period_id IS NULL
            """
        )
    )

    # Derive base/fraction for rows whose effective benchmark was already
    # frozen. effective = base x fraction, so base = effective / fraction.
    # The stored effective value is preserved bit-for-bit.
    bind.execute(
        text(
            """
            UPDATE work_report_tasks t
            SET benchmark_fraction_snapshot =
                    CASE WHEN r.day_status = 'half_day' THEN 0.5 ELSE 1.0 END,
                benchmark_base_value_snapshot =
                    CASE WHEN r.day_status = 'half_day'
                         THEN t.benchmark_value_snapshot * 2
                         ELSE t.benchmark_value_snapshot
                    END
            FROM daily_work_reports r
            WHERE r.id = t.report_id
              AND t.benchmark_value_snapshot IS NOT NULL
              AND t.benchmark_base_value_snapshot IS NULL
            """
        )
    )

    # Point report-linked activity requests at that report's period.
    bind.execute(
        text(
            """
            UPDATE activity_requests a
            SET period_id = p.id
            FROM work_report_periods p
            WHERE a.report_id IS NOT NULL
              AND p.report_id = a.report_id
              AND a.period_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index("activity_requests_period_idx", table_name="activity_requests")
    op.drop_column("activity_requests", "period_id")
    op.drop_column("work_report_tasks", "benchmark_fraction_snapshot")
    op.drop_column("work_report_tasks", "benchmark_base_value_snapshot")
    op.drop_index("work_report_tasks_period_idx", table_name="work_report_tasks")
    op.drop_column("work_report_tasks", "period_id")
    op.drop_index("work_report_periods_report_idx", table_name="work_report_periods")
    op.drop_table("work_report_periods")
    op.drop_constraint(
        "work_reports_report_mode_valid", "daily_work_reports", type_="check"
    )
    op.drop_column("daily_work_reports", "report_mode")
