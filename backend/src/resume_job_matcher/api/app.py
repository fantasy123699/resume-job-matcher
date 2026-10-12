from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from resume_job_matcher.api.routes.agent_runs import router as agent_runs_router
from resume_job_matcher.api.routes.auth import router as auth_router
from resume_job_matcher.api.routes.exports import router as exports_router
from resume_job_matcher.api.routes.health import router as health_router
from resume_job_matcher.api.routes.jobs import router as jobs_router
from resume_job_matcher.api.routes.optimizations import router as optimizations_router
from resume_job_matcher.api.routes.resume_versions import router as resume_versions_router
from resume_job_matcher.api.routes.resumes import router as resumes_router
from resume_job_matcher.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Resume Job Matcher API",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(agent_runs_router)
    app.include_router(exports_router)
    app.include_router(jobs_router)
    app.include_router(optimizations_router)
    app.include_router(resumes_router)
    app.include_router(resume_versions_router)
    return app


app = create_app()
