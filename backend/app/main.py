import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from app.api import onboarding, discovery, products, icp, prospects, auth
import app.models.schemas  # ensure SQLModel models are imported so metadata is registered
from app.database.session import init_db
from app.config import settings, effective_app_url

STATIC_DIR = Path(os.getenv("STATIC_DIR", str(Path(__file__).resolve().parent.parent / "static")))

app = FastAPI(
    title="NexivoReach API",
    description="AI B2B Sales Prospecting Agent Engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        effective_app_url(),
        settings.APP_URL,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(discovery.router)
app.include_router(products.router)
app.include_router(icp.router)
app.include_router(prospects.router)


@app.on_event("startup")
def on_startup():
    init_db()
    if STATIC_DIR.is_dir():
        print(f"Serving frontend from {STATIC_DIR}")
    else:
        print(f"No frontend build at {STATIC_DIR} — API-only mode")


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "NexivoReach Backend", "static": STATIC_DIR.is_dir()}


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")
else:

    @app.get("/")
    def read_root():
        return JSONResponse({
            "status": "online",
            "app": "NexivoReach API",
            "tagline": "Turn products into prospects.",
            "hint": "Frontend static files not found. Redeploy with Docker (Dockerfile).",
        })
