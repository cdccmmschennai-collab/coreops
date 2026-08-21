"""FastAPI application factory.

V0 wires configuration, CORS, the uniform error envelope, and the health
router. Domain routers are registered in later phases.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.context import set_request_context
from app.health import router as health_router
from app.modules.activity_master.router import router as activity_master_router
from app.modules.activity_requests.router import router as activity_requests_router
from app.modules.activity_types.router import router as activity_types_router
from app.modules.audit.router import router as audit_router
from app.modules.benchmarks.router import router as benchmarks_router
from app.modules.biometric.router import (
    admin_router as biometric_admin_router,
    router as biometric_ingestion_router,
)
from app.modules.calendar.router import router as calendar_router
from app.modules.job_codes.router import router as job_codes_router
from app.modules.notifications.router import router as notifications_router
from app.modules.attendance.router import (
    employee_router as attendance_employee_router,
    router as attendance_router,
)
from app.modules.auth.router import router as auth_router
from app.modules.employees.router import router as employees_router
from app.modules.leave.router import router as leave_router
from app.modules.leave_balances.router import router as leave_balances_router
from app.modules.offices.router import router as offices_router
from app.modules.permissions.router import router as permissions_router
from app.modules.plants.router import router as plants_router
from app.modules.projects.router import router as projects_router
from app.modules.users.router import router as users_router
from app.modules.project_activities.router import router as project_activities_router
from app.modules.project_deliverables.router import router as deliverables_router
from app.modules.project_submissions.router import router as submissions_router
from app.modules.production_status.router import router as production_status_router
from app.modules.production_status.router import (
    report_router as production_status_report_router,
)
from app.modules.report_compliance.router import router as report_compliance_router
from app.modules.reports_export.router import router as reports_export_router
from app.modules.work_reports.router import router as work_reports_router
from app.shared.errors import register_error_handlers


def create_app() -> FastAPI:
    # Interactive docs are opt-in via ENABLE_API_DOCS (default false, so
    # production exposes no schema). When enabled the URLs are exactly the ones
    # this app has always served: Swagger at {prefix}/docs, ReDoc at FastAPI's
    # default /redoc, schema at {prefix}/openapi.json. When disabled all three
    # are None, so FastAPI never mounts the routes and they return 404.
    docs_enabled = settings.ENABLE_API_DOCS
    app = FastAPI(
        title="Coreops API",
        version="1.0.0",
        docs_url=f"{settings.API_V1_PREFIX}/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # Let the browser read the XLSX download filename on cross-origin
        # fetches (frontend :3100 -> API :8100).
        expose_headers=["Content-Disposition"],
    )

    register_error_handlers(app)

    @app.middleware("http")
    async def _capture_request_context(request: Request, call_next):
        # Stash client IP / user-agent for the audit logger (read via ContextVars
        # in app.modules.audit.service). Starlette copies the contextvars Context
        # into the threadpool that runs sync endpoints, so this is visible there.
        set_request_context(
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        return await call_next(request)

    # Routers (one module per phase).
    app.include_router(health_router, prefix=settings.API_V1_PREFIX)
    app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
    app.include_router(users_router, prefix=settings.API_V1_PREFIX)
    app.include_router(employees_router, prefix=settings.API_V1_PREFIX)
    app.include_router(projects_router, prefix=settings.API_V1_PREFIX)
    app.include_router(attendance_router, prefix=settings.API_V1_PREFIX)
    app.include_router(attendance_employee_router, prefix=settings.API_V1_PREFIX)
    app.include_router(work_reports_router, prefix=settings.API_V1_PREFIX)
    app.include_router(reports_export_router, prefix=settings.API_V1_PREFIX)
    app.include_router(report_compliance_router, prefix=settings.API_V1_PREFIX)
    app.include_router(offices_router, prefix=settings.API_V1_PREFIX)
    app.include_router(leave_router, prefix=settings.API_V1_PREFIX)
    app.include_router(leave_balances_router, prefix=settings.API_V1_PREFIX)
    # Permission (Phase 11) = 1h/2h of sanctioned absence inside a working day,
    # against a 4h monthly allowance. Not RBAC.
    app.include_router(permissions_router, prefix=settings.API_V1_PREFIX)
    app.include_router(calendar_router, prefix=settings.API_V1_PREFIX)
    app.include_router(notifications_router, prefix=settings.API_V1_PREFIX)
    app.include_router(activity_types_router, prefix=settings.API_V1_PREFIX)
    app.include_router(activity_master_router, prefix=settings.API_V1_PREFIX)
    app.include_router(activity_requests_router, prefix=settings.API_V1_PREFIX)
    app.include_router(benchmarks_router, prefix=settings.API_V1_PREFIX)
    app.include_router(job_codes_router, prefix=settings.API_V1_PREFIX)
    app.include_router(audit_router, prefix=settings.API_V1_PREFIX)
    app.include_router(project_activities_router, prefix=settings.API_V1_PREFIX)
    app.include_router(deliverables_router, prefix=settings.API_V1_PREFIX)
    app.include_router(submissions_router, prefix=settings.API_V1_PREFIX)
    app.include_router(production_status_router, prefix=settings.API_V1_PREFIX)
    # The PM cumulative report spans every project, so it hangs off its own
    # /production-status prefix rather than /projects/{id}.
    app.include_router(production_status_report_router, prefix=settings.API_V1_PREFIX)
    app.include_router(plants_router, prefix=settings.API_V1_PREFIX)
    # Biometric (Phase 2). The ingestion route is always mounted but answers 404
    # to everyone while EASYTIME_INGESTION_ENABLED is false; the admin routes are
    # ordinary project_manager endpoints and do not depend on that flag.
    app.include_router(biometric_ingestion_router, prefix=settings.API_V1_PREFIX)
    app.include_router(biometric_admin_router, prefix=settings.API_V1_PREFIX)

    # Temporary notification debug endpoints — mounted only when explicitly
    # enabled (and each route still requires the project_manager role).
    if settings.ENABLE_DEBUG_ENDPOINTS:
        from app.modules.debug.router import router as debug_router

        app.include_router(debug_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
