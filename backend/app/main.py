from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.api import onboarding, discovery, products, icp, prospects, auth
import app.models.schemas  # ensure SQLModel models are imported so metadata is registered
from app.database.session import init_db
from app.config import settings, effective_app_url

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

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

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(auth.router)
app.include_router(onboarding.router)
app.include_router(discovery.router)
app.include_router(products.router)
app.include_router(icp.router)
app.include_router(prospects.router)

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "NexivoReach Backend"}


def _mount_frontend():
    if not STATIC_DIR.is_dir():
        return

    assets_dir = STATIC_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/")
    async def spa_index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        if full_path.startswith("api/") or full_path == "health":
            raise HTTPException(status_code=404)
        candidate = STATIC_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC_DIR / "index.html")


_mount_frontend()


if not STATIC_DIR.is_dir():

    @app.get("/")
    def read_root():
        return {
            "status": "online",
            "app": "NexivoReach API",
            "tagline": "Turn products into prospects.",
        }
