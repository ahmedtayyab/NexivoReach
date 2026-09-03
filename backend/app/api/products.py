from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel
from typing import List, Dict, Any
from sqlmodel import Session, select
from app.providers.factory import get_ai_provider
from app.tools.web_search import WebSearchTool
from app.database.session import engine
from app.models.schemas import ProductItem
from app.api.serializers import product_to_frontend, normalize_extracted_product
from app.api.deps import AuthUser, get_current_user

router = APIRouter(prefix="/api/products", tags=["products"])


class UrlParseRequest(BaseModel):
    url: str


class ProductSaveRequest(BaseModel):
    products: List[Dict[str, Any]] = []


def _file_to_text(filename: str, raw: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith((".csv", ".xlsx", ".xls")):
        import io
        import pandas as pd
        buffer = io.BytesIO(raw)
        df = pd.read_csv(buffer) if name.endswith(".csv") else pd.read_excel(buffer)
        return df.to_csv(index=False)
    return raw.decode("utf-8", errors="ignore")


@router.post("/extract-url")
async def extract_products_from_url(req: UrlParseRequest, _user: AuthUser = Depends(get_current_user)):
    scraper = WebSearchTool()
    pages = await scraper.scrape_catalog_pages(req.url)
    combined = "\n".join(text for _, text in pages) or req.url
    provider = get_ai_provider()
    prods = await provider.extract_products(combined, source_type="url")
    return {
        "sourceUrl": req.url,
        "pagesScanned": len(pages),
        "products": [normalize_extracted_product(p, i) for i, p in enumerate(prods)],
        "message": (
            f"Found {len(prods)} product{'s' if len(prods) != 1 else ''} from the website."
            if prods
            else "No products were found on that page. Try a product or catalog URL, or add items manually."
        ),
    }


@router.post("/upload-file")
async def upload_catalog_file(file: UploadFile = File(...), _user: AuthUser = Depends(get_current_user)):
    provider = get_ai_provider()
    content = await file.read()
    text = _file_to_text(file.filename or "", content)
    prods = await provider.extract_products(text or str(content), source_type="file")
    return {
        "filename": file.filename,
        "products": [normalize_extracted_product(p, i) for i, p in enumerate(prods)],
    }


@router.get("/")
def list_products(user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        rows = session.exec(select(ProductItem).where(ProductItem.user_id == user.id)).all()
        return [product_to_frontend(row) for row in rows]


@router.post("/save")
def save_products(req: ProductSaveRequest, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        for row in session.exec(select(ProductItem).where(ProductItem.user_id == user.id)).all():
            session.delete(row)
        saved = []
        for index, raw in enumerate(req.products):
            normalized = normalize_extracted_product(raw, index)
            item = ProductItem(
                id=normalized["id"],
                name=normalized["name"],
                category=normalized["category"],
                description=normalized["description"],
                price=normalized.get("price"),
                moq=normalized.get("moq"),
                specs=normalized.get("specs") or [],
                target_buyer=normalized.get("targetBuyer"),
                features=normalized.get("features") or [],
                product_url=normalized.get("productUrl"),
                image_url=normalized.get("imageUrl"),
                ai_extracted=normalized.get("aiExtracted", True),
                verified_by_user=normalized.get("verifiedByUser", False),
                user_id=user.id,
            )
            session.add(item)
            saved.append(item)
        session.commit()
        return [product_to_frontend(item) for item in saved]
