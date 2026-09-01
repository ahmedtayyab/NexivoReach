from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import onboarding, discovery, products, icp, prospects
import app.models.schemas  # ensure SQLModel models are imported so metadata is registered
from app.database.session import init_db

app = FastAPI(
    title="NexivoReach API",
    description="AI B2B Sales Prospecting Agent Engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(onboarding.router)
app.include_router(discovery.router)
app.include_router(products.router)
app.include_router(icp.router)
app.include_router(prospects.router)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "app": "NexivoReach API",
        "tagline": "Turn products into prospects."
    }

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "NexivoReach Backend"}
