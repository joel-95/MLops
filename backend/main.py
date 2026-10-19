import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.routes import webhook, repos, status
from backend.db.models import init_db
from deploy.local_deploy import recover_deployments

app = FastAPI(
    title="AutoMLOps Platform API",
    description="Automated MLOps lifecycle, quality gating, monitoring, and auto-retraining engine.",
    version="1.0.0"
)

# 1. CORS Configuration for React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Register Routers
app.include_router(webhook.router, prefix="/webhook", tags=["Webhook"])
app.include_router(repos.router, prefix="/repos", tags=["Repositories"])
app.include_router(status.router, prefix="/status", tags=["Status Dashboard"])

# 3. Mount Static Directory for Evidently HTML Reports
reports_dir = Path("reports")
reports_dir.mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(reports_dir)), name="reports")


@app.on_event("startup")
async def on_startup():
    """Initializes SQLite tables and recovers running container deployments."""
    init_db()
    recover_deployments()
    print("🚀 AutoMLOps Backend initialized and ready.")


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "AutoMLOps Backend",
        "version": "1.0.0"
    }


@app.get("/")
def root():
    return {
        "platform": "AutoMLOps",
        "docs_url": "/docs",
        "status_endpoint": "/status/{repo_id}",
        "repos_endpoint": "/repos"
    }
