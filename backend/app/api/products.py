from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from app.providers.factory import get_ai_provider

router = APIRouter(prefix="/api/products", tags=["products"])

class UrlParseRequest(BaseModel):
    url: str

@router.post("/extract-url")
async def extract_products_from_url(req: UrlParseRequest):
    provider = get_ai_provider()
    prods = await provider.extract_products(req.url, source_type="url")
    return {"products": prods}

@router.post("/upload-file")
async def upload_catalog_file(file: UploadFile = File(...)):
    provider = get_ai_provider()
    content = await file.read()
    prods = await provider.extract_products(str(content), source_type="file")
    return {"filename": file.filename, "products": prods}
