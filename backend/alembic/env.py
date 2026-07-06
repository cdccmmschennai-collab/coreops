"""Alembic environment.

Reads the database URL from application settings (never hardcoded) and targets
`Base.metadata`. No model imports in V0 — the baseline revision is created in V1
once the ORM models exist. Add `import app.modules.<m>.models` here as models land.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.core.database import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models so autogenerate sees their metadata. Add new modules here.
import app.modules.users.models  # noqa: E402,F401
import app.modules.employees.models  # noqa: E402,F401
import app.modules.projects.models  # noqa: E402,F401
import app.modules.attendance.models  # noqa: E402,F401
import app.modules.work_reports.models  # noqa: E402,F401
import app.modules.activity_types.models  # noqa: E402,F401
import app.modules.job_codes.models  # noqa: E402,F401
import app.modules.employees.models  # noqa: E402,F401 (re-import after reporting_pm_id)
import app.modules.job_codes.models  # noqa: E402,F401 (already imported but ensure re-registration)
import app.modules.project_submissions.models  # noqa: E402,F401
import app.modules.project_activities.models  # noqa: E402,F401
import app.modules.leave_balances.models  # noqa: E402,F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
