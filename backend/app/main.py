"""FastAPI application factory.

V0 wires configuration, CORS, the uniform error envelope, and the health
router. Domain routers are registered in later phases.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.health import router as health_router
from app.modules.attendance.router import (
    employee_router as attendance_employee_router,
    router as attendance_router,
)
from app.modules.auth.router import router as auth_router
from app.modules.employees.router import router as employees_router
from app.modules.offices.router import router as offices_router
from app.modules.projects.router import router as projects_router
from app.modules.users.router import router as users_router
from app.modules.work_reports.router import router as work_reports_router
from app.shared.errors import register_error_handlers


def create_app() -> FastAPI:
    app = FastAPI(
        title="Workforce Management System API",
        version="1.0.0",
        docs_url=f"{settings.API_V1_PREFIX}/docs",
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    # Routers (one module per phase).
    app.include_router(health_router, prefix=settings.API_V1_PREFIX)
    app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
    app.include_router(users_router, prefix=settings.API_V1_PREFIX)
    app.include_router(employees_router, prefix=settings.API_V1_PREFIX)
    app.include_router(projects_router, prefix=settings.API_V1_PREFIX)
    app.include_router(attendance_router, prefix=settings.API_V1_PREFIX)
    app.include_router(attendance_employee_router, prefix=settings.API_V1_PREFIX)
    app.include_router(work_reports_router, prefix=settings.API_V1_PREFIX)
    app.include_router(offices_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
