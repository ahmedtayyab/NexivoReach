import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Request, UploadFile, File
from pydantic import BaseModel
from typing import List, Dict, Any
from sqlmodel import Session, select
from app.providers.factory import get_ai_provider
from app.tools.web_search import WebSearchTool
from app.database.session import engine
from app.models.schemas import ProductItem, Business
from app.api.serializers import product_to_frontend, normalize_extracted_product
from app.api.deps import AuthUser, get_current_user, resolve_business_id
from app.integrations import sheets as sheets_mod

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/products", tags=["products"])


def _sync_products_to_sheets(business_id: str, products: list[dict]) -> None:
    try:
        with Session(engine) as session:
            biz = session.get(Business, business_id)
            company_name = sheets_mod.resolve_company_tab_name(biz, products)
            if (
                biz
                and sheets_mod.is_placeholder_company_name(biz.name)
                and company_name
                and not sheets_mod.is_placeholder_company_name(company_name)
            ):
                biz.name = company_name
                if not (biz.website or "").strip():
                    first_url = next(
                        (
                            (p.get("sourceUrl") or p.get("source_url") or p.get("productUrl") or p.get("product_url") or "").strip()
                            for p in products
                            if (p.get("sourceUrl") or p.get("source_url") or p.get("productUrl") or p.get("product_url"))
                        ),
                        "",
                    )
                    if first_url:
                        biz.website = first_url
                session.add(biz)
                session.commit()
        result = sheets_mod.sync_products(company_name, products)
        log.info("Sheets product sync (%s): %s", company_name, result)
    except Exception as exc:
        log.warning("Sheets product sync failed: %s", exc)


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
    pages, shop_products = await scraper.scrape_shop_catalog(req.url)
    combined = "\n".join(text for _, text in pages) or req.url
    provider = get_ai_provider()
    fallback_products = await provider.extract_products(combined, source_type="url")
    merged: list[dict] = []
    seen = set()
    for raw in shop_products + fallback_products:
        item = normalize_extracted_product(raw, len(merged))
        key = (item.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return {
        "sourceUrl": req.url,
        "pagesScanned": len(pages),
        "products": merged,
        "message": (
            f"Found {len(merged)} product{'s' if len(merged) != 1 else ''} from {len(pages)} page{'s' if len(pages) != 1 else ''}."
            if merged
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
def list_products(request: Request, user: AuthUser = Depends(get_current_user)):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        rows = session.exec(
            select(ProductItem).where(ProductItem.business_id == business_id)
        ).all()
        return [product_to_frontend(row) for row in rows]


@router.post("/save")
def save_products(
    req: ProductSaveRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
):
    with Session(engine) as session:
        business_id = resolve_business_id(request, user, session)
        for row in session.exec(select(ProductItem).where(ProductItem.business_id == business_id)).all():
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
                product_url=normalized.get("productUrl"),
                image_url=normalized.get("imageUrl"),
                source_url=normalized.get("sourceUrl"),
                in_stock=normalized.get("inStock"),
                user_id=user.id,
                business_id=business_id,
            )
            session.add(item)
            saved.append(item)
        session.commit()
        result = [product_to_frontend(item) for item in saved]

        if sheets_mod.is_configured():
            background_tasks.add_task(_sync_products_to_sheets, business_id, result)

        return result
