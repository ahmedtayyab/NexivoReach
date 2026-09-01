"""
NexivoReach FastAPI Main Application Entrypoint
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
