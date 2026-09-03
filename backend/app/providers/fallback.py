import re
from typing import Dict, Any, List
from app.providers.base import AIProvider


KNOWN_MARKETS = [
    "United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait", "Oman", "Bahrain",
    "United States", "United Kingdom", "Germany", "France", "Netherlands",
    "India", "Pakistan", "China", "Singapore", "Malaysia", "Australia", "Canada",
    "UAE", "USA", "UK",
]


class FallbackProvider(AIProvider):
    def name(self) -> str:
        return "Heuristic Fallback Provider"

    async def extract_business_profile(self, text: str) -> Dict[str, Any]:
        raw = (text or "").strip()
        urls = re.findall(r"https?://[^\s]+", raw)
        website = urls[0].rstrip(".,)") if urls else ""

        name = ""
        patterns = [
            r"(?:company|business|brand)\s+(?:is|called|named)\s+([A-Z][\w&.\- ]{1,60})",
            r"^([A-Z][\w&.\- ]{1,60}?)\s+(?:is|are)\s+a\b",
            r"^([A-Z][\w&.\- ]{1,60}?)\s+(?:manufactures|exports|sells|produces|builds|provides|distributes)",
        ]
        for pattern in patterns:
            match = re.search(pattern, raw, re.M)
            if match:
                candidate = match.group(1).strip(" .,-")
                if candidate.lower() not in {"we", "our", "i", "this", "the"}:
                    name = candidate
                    break

        markets = []
        lowered = raw.lower()
        for market in KNOWN_MARKETS:
            if market.lower() in lowered and market not in markets:
                markets.append(market)

        categories = []
        cat_match = re.search(
            r"(?:products?|categories|sell(?:s|ing)?)\s*[:\-]\s*([^\n.]+)",
            raw,
            re.I,
        )
        if cat_match:
            categories = [c.strip() for c in re.split(r",|/| and ", cat_match.group(1)) if c.strip()][:6]

        return {
            "name": name,
            "website": website,
            "target_markets": markets,
            "primary_categories": categories,
            "extracted_by_ai": False,
        }

    async def extract_products(self, content: str, source_type: str = "text") -> List[Dict[str, Any]]:
        products: List[Dict[str, Any]] = []
        seen = set()
        skip_prefixes = (
            "home", "about", "contact", "search", "welcome", "our categories",
            "feature products", "get special", "download", "links", "skip",
            "view category", "products", "customer care",
        )
        skip_exact = {
            "alwasi", "alwasi enterprises", "enterprise", "fitness & bodybuilding",
            "sports wears", "sports goods", "all kind of gloves", "catalogue",
        }
        for raw_line in (content or "").splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip(" -•\t|")
            if len(line) < 4 or len(line) > 90:
                continue
            if not re.search(r"[A-Za-z]", line):
                continue
            lowered = line.lower()
            if any(lowered.startswith(prefix) for prefix in skip_prefixes):
                continue
            if lowered in skip_exact:
                continue
            if re.search(r"\b(copyright|privacy|cookie|login|cart|wishlist)\b", lowered):
                continue
            if re.match(r"^art\s*#", lowered) or re.match(r"^awe-\d+", lowered):
                continue
            looks_like_product = bool(re.search(
                r"\b(glove|belt|strap|hoodie|jacket|shirt|suit|bag|wrap|sleeve|hook|band|coverall)\b",
                lowered,
            ))
            if not looks_like_product:
                continue
            name = re.split(r"\s[-–:|]\s", line)[0][:80].strip()
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            products.append({
                "name": name,
                "category": _guess_category(name),
                "description": line,
                "ai_extracted": False,
                "verified_by_user": False,
            })
            if len(products) >= 16:
                break
        return products

    async def analyze_buying_signals(self, company_text: str, custom_signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        text = (company_text or "").lower()
        signals: List[Dict[str, Any]] = []
        rules = custom_signals or [
            {"name": "Expansion", "description": "New site, branch, or capacity coming online."},
            {"name": "Hiring", "description": "Active hiring that implies growth."},
            {"name": "Funding", "description": "Investment or capital that often precedes procurement."},
        ]
        keyword_map = [
            (["opening", "flagship", "new location", "expansion", "new plant", "new facility", "sq ft", "sqft"], "Expansion"),
            (["upgrade", "renovat", "refresh", "replace", "moderniz"], "Upgrade / replacement"),
            (["hiring", "job", "we're hiring", "we are hiring"], "Hiring"),
            (["funding", "investment", "series", "capital", "raised"], "Funding"),
            (["rfp", "tender", "procurement", "supplier", "vendor"], "Procurement"),
        ]
        for keywords, label in keyword_map:
            if any(k in text for k in keywords):
                matched_rule = next((r for r in rules if label.lower() in (r.get("name") or "").lower()), None)
                name = (matched_rule or {}).get("name") or label
                signals.append({
                    "signal": name,
                    "whyItMatters": (matched_rule or {}).get("description")
                    or "Public activity that often precedes a buying decision.",
                    "sourceExcerpt": _excerpt_around(company_text, keywords),
                })
        if not signals and company_text:
            signals.append({
                "signal": "Public profile match",
                "whyItMatters": "Company materials overlap the configured buyer profile.",
                "sourceExcerpt": (company_text or "")[:180],
            })
        return signals[:3]

    async def match_catalog_products(
        self,
        products: List[Dict[str, Any]],
        company_text: str,
        company_name: str,
    ) -> List[Dict[str, Any]]:
        text = (company_text or "").lower()
        demand = any(k in text for k in [
            "expand", "opening", "upgrade", "procure", "tender", "rfp", "new facility", "hiring",
        ])
        results: List[Dict[str, Any]] = []
        for product in products or []:
            name = product.get("name") or product.get("productName") or "Catalog product"
            category = (product.get("category") or "").lower()
            tokens = [t for t in f"{name} {category}".lower().split() if len(t) > 3]
            hits = sum(1 for t in tokens if t in text)
            if hits >= 2:
                fit = "High"
            elif hits >= 1 and demand:
                fit = "High"
            elif hits >= 1 or demand:
                fit = "Medium"
            else:
                fit = "Low"
            if fit == "High":
                reasoning = f"Public materials for {company_name} overlap {name}."
            elif fit == "Medium":
                reasoning = f"{name} is a plausible fit for {company_name}; confirm during outreach."
            else:
                reasoning = f"Limited public evidence for {name}."
            results.append({"productName": name, "fitLevel": fit, "reasoning": reasoning})
        order = {"High": 0, "Medium": 1, "Low": 2}
        results.sort(key=lambda row: order.get(row["fitLevel"], 9))
        return results[:4]

    async def generate_personalized_outreach(
        self,
        company_name: str,
        why_prospect: str,
        signals: List[Dict[str, Any]],
        matched_products: List[Dict[str, Any]],
        seller_name: str = "Sales Team",
    ) -> Dict[str, str]:
        product_name = "our products"
        if matched_products:
            product_name = matched_products[0].get("productName") or matched_products[0].get("name") or product_name
        signal_label = signals[0]["signal"] if signals else "recent public activity"
        sender = seller_name or "Sales Team"
        return {
            "subject": f"{product_name} for {company_name}",
            "body": (
                f"Hi {company_name} team,\n\n"
                f"I noticed {company_name}'s {signal_label.lower()} and wanted to introduce {product_name} from {sender}.\n\n"
                f"{why_prospect}\n\n"
                "If useful, I can send a short spec sheet and pricing for the items that appear to fit.\n\n"
                f"Best regards,\n{sender}"
            ),
            "personalizedReason": f"Drafted from {company_name}'s {signal_label.lower()} and catalog match on {product_name}.",
        }


def _guess_category(name: str) -> str:
    lowered = (name or "").lower()
    mapping = (
        ("glove", "Gloves"),
        ("belt", "Fitness & Bodybuilding"),
        ("strap", "Fitness & Bodybuilding"),
        ("wrap", "Fitness & Bodybuilding"),
        ("sleeve", "Fitness & Bodybuilding"),
        ("hoodie", "Sportswear"),
        ("jacket", "Sportswear"),
        ("shirt", "Sportswear"),
        ("suit", "Sportswear"),
        ("bag", "Sports Goods"),
    )
    for token, category in mapping:
        if token in lowered:
            return category
    return "Uncategorized"


def _excerpt_around(text: str, keywords: List[str], window: int = 140) -> str:
    lowered = (text or "").lower()
    for kw in keywords:
        idx = lowered.find(kw)
        if idx != -1:
            start = max(0, idx - 40)
            end = min(len(text), idx + window)
            return text[start:end].strip()
    return (text or "")[:window]
