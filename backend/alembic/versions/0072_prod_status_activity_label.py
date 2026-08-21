"""0072 prod status activity label

(Production Status -> a typed-in activity. The revision id is abbreviated
because `alembic_version.version_num` is VARCHAR(32).)

Two changes to `project_production_statuses`, both about ONE thing: a Project
Head may now record production status against an activity that is not in
Activity Master, by typing its name.

  activity_id     UUID NOT NULL -> NULL
  activity_label  TEXT NULL      (new)

Why a label on this row and not a new Activity Master entry
    Activity Master is company-wide master data: its rows drive work reports,
    staffing, benchmarks and the benchmark guide. Creating an entry there every
    time a Head types a heading would put a typo into all of them, permanently
    and globally. The typed name is therefore recorded ON the production status
    row, where it means exactly what it says - "this one update was about this"
    - and nothing else in CoreOps is touched by it.

    A record therefore names its activity in exactly ONE of two ways, and the
    CHECK below is what makes that literal:

      activity_id set, activity_label NULL   an Activity Master activity
      activity_id NULL, activity_label set   a typed-in activity

    Never both, and never neither. The service resolves the display name from
    whichever is present, so the tab, the report and the .xlsx print one
    ACTIVITY column and never have to explain which kind of row they are on.

Identity
    A production status is still current FOR project + revision + activity, and
    the typed name is part of that identity exactly as an activity id is: two
    updates typed "HIERARCHY QA/QC" on the same project and revision are the
    same combination, and the newer supersedes the older. The identity index is
    rebuilt below to carry both columns, so Postgres groups them the same way
    the DISTINCT ON in the service does (NULLs compare equal there, which is
    what makes a NULL activity_id group cleanly by label).

Existing rows
    Untouched and unchanged in meaning: every row recorded before this migration
    has an activity_id and gets activity_label NULL, which is exactly the
    "an Activity Master activity" case above. Nothing is backfilled, no history
    is rewritten, and the append-only model is unaffected.

Downgrade drops the label, restores NOT NULL on activity_id and restores the
original index. It DELETES any typed-activity rows first - they have no
activity_id and cannot satisfy the restored NOT NULL. That is unavoidable and
is why the deletion is explicit here rather than an unexplained failure.

Revision ID: 0072_prod_status_activity
Revises: 0071_prod_status_plant
Create Date: 2026-08-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0072_prod_status_activity"
down_revision: Union[str, None] = "0071_prod_status_plant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_IDENTITY_INDEX = "project_production_statuses_project_revision_activity_idx"
_ACTIVITY_INDEX = "project_production_statuses_project_activity_created_idx"


def upgrade() -> None:
    op.add_column(
        "project_production_statuses",
        sa.Column("activity_label", sa.Text(), nullable=True),
    )
    op.alter_column(
        "project_production_statuses",
        "activity_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # Exactly one of the two. Enforced in the database rather than only in the
    # service, because "an activity" is what makes a row meaningful and a row
    # naming none - or two - is not a state any caller should be able to reach.
    #
    # `activity_label IS NOT NULL` is spelled out rather than left implicit in
    # the btrim comparison. Without it, a row with BOTH columns NULL evaluates
    # to `false OR (true AND NULL)` = NULL, and a CHECK constraint PASSES on
    # NULL - so the one state this constraint exists to forbid would have been
    # the one it let through.
    op.create_check_constraint(
        "project_production_statuses_activity_named_once",
        "project_production_statuses",
        "(activity_id IS NOT NULL AND activity_label IS NULL)"
        " OR (activity_id IS NULL AND activity_label IS NOT NULL"
        " AND btrim(activity_label) <> '')",
    )

    # The identity index gains the label, so "latest per project + revision +
    # activity" is still one index lookup whichever way the activity is named.
    op.drop_index(_IDENTITY_INDEX, table_name="project_production_statuses")
    op.create_index(
        _IDENTITY_INDEX,
        "project_production_statuses",
        ["project_id", "revision", "activity_id", "activity_label",
         sa.text("created_at DESC")],
    )


def downgrade() -> None:
    # Typed-activity rows cannot survive activity_id going back to NOT NULL.
    op.execute(
        "DELETE FROM project_production_statuses WHERE activity_id IS NULL"
    )

    op.drop_index(_IDENTITY_INDEX, table_name="project_production_statuses")
    op.create_index(
        _IDENTITY_INDEX,
        "project_production_statuses",
        ["project_id", "revision", "activity_id", sa.text("created_at DESC")],
    )
    op.drop_constraint(
        "project_production_statuses_activity_named_once",
        "project_production_statuses",
        type_="check",
    )
    op.alter_column(
        "project_production_statuses",
        "activity_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_column("project_production_statuses", "activity_label")
