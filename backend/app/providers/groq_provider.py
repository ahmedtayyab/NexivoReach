from typing import Any, Dict, List
from app.providers.base import AIProvider
from app.providers.json_util import parse_json_payload
from app.config import settings


class GroqProvider(AIProvider):
    def __init__(self):
        self.api_key = settings.GROQ_API_KEY
        self.available = bool(self.api_key)
        self.model = "llama-3.3-70b-versatile"

    def name(self) -> str:
        return "Groq API Provider"

    def _client(self):
        from groq import Groq
        return Groq(api_key=self.api_key)

    def _complete(self, prompt: str) -> str:
        client = self._client()
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return (response.choices[0].message.content or "").strip()

    async def extract_business_profile(self, text: str) -> Dict[str, Any]:
        if not self.available:
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().extract_business_profile(text)
        try:
            prompt = (
                "Extract a business profile as JSON with keys "
                "name, website, target_markets (array), primary_categories (array) from:\n"
                f"{text}"
            )
            parsed = parse_json_payload(self._complete(prompt))
            if isinstance(parsed, dict) and parsed.get("name"):
                parsed["extracted_by_ai"] = True
                return parsed
        except Exception:
            pass
        from app.providers.fallback import FallbackProvider
        return await FallbackProvider().extract_business_profile(text)

    async def extract_products(self, content: str, source_type: str = "text") -> List[Dict[str, Any]]:
        if not self.available:
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().extract_products(content, source_type)
        try:
            prompt = (
                f"Extract an array of products as JSON from this {source_type} content. "
                "Each item must include name, category, description, price, moq, specs (array), target_buyer.\n"
                f"{content[:6000]}"
            )
            parsed = parse_json_payload(self._complete(prompt))
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict) and isinstance(parsed.get("products"), list):
                return parsed["products"]
        except Exception:
            pass
        from app.providers.fallback import FallbackProvider
        return await FallbackProvider().extract_products(content, source_type)

    async def analyze_buying_signals(self, company_text: str, custom_signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.available:
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().analyze_buying_signals(company_text, custom_signals)
        try:
            prompt = (
                "Identify buying signals in the company text. Return a JSON array with keys "
                "signal, whyItMatters, sourceExcerpt, sourceUrl (optional).\n"
                f"Custom signal rules: {custom_signals}\n\nCompany text:\n{company_text[:5000]}"
            )
            parsed = parse_json_payload(self._complete(prompt))
            if isinstance(parsed, list) and parsed:
                return parsed
        except Exception:
            pass
        from app.providers.fallback import FallbackProvider
        return await FallbackProvider().analyze_buying_signals(company_text, custom_signals)

    async def match_catalog_products(
        self,
        products: List[Dict[str, Any]],
        company_text: str,
        company_name: str,
    ) -> List[Dict[str, Any]]:
        if not self.available:
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().match_catalog_products(products, company_text, company_name)
        try:
            catalog = [
                {
                    "name": p.get("name") or p.get("productName"),
                    "category": p.get("category"),
                    "description": p.get("description"),
                }
                for p in products
            ]
            prompt = (
                f"Match catalog products to {company_name}. Return a JSON array of "
                "{productName, fitLevel (High|Medium|Low), reasoning}.\n"
                f"Catalog: {catalog}\n\nCompany materials:\n{company_text[:4000]}"
            )
            parsed = parse_json_payload(self._complete(prompt))
            if isinstance(parsed, list) and parsed:
                return parsed
        except Exception:
            pass
        from app.providers.fallback import FallbackProvider
        return await FallbackProvider().match_catalog_products(products, company_text, company_name)

    async def generate_personalized_outreach(
        self,
        company_name: str,
        why_prospect: str,
        signals: List[Dict[str, Any]],
        matched_products: List[Dict[str, Any]],
        seller_name: str = "Sales Team",
    ) -> Dict[str, str]:
        if not self.available:
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().generate_personalized_outreach(
                company_name, why_prospect, signals, matched_products, seller_name
            )
        try:
            prompt = (
                f"You represent {seller_name}. Draft a B2B outreach email as JSON with keys "
                f"subject, body, personalizedReason for {company_name}. Sign as {seller_name}. "
                f"Context: {why_prospect}. Signals: {signals}. Matched products: {matched_products}"
            )
            parsed = parse_json_payload(self._complete(prompt))
            if isinstance(parsed, dict) and parsed.get("subject") and parsed.get("body"):
                return parsed
        except Exception:
            pass
        from app.providers.fallback import FallbackProvider
        return await FallbackProvider().generate_personalized_outreach(
            company_name, why_prospect, signals, matched_products, seller_name
        )

    async def generate_follow_up_outreach(
        self,
        company_name: str,
        why_prospect: str,
        prior_subject: str,
        prior_body: str,
        reply_summary: str = "",
        seller_name: str = "Sales Team",
    ) -> Dict[str, str]:
        if not self.available:
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().generate_follow_up_outreach(
                company_name, why_prospect, prior_subject, prior_body, reply_summary, seller_name
            )
        try:
            mode = "their reply" if reply_summary.strip() else "no reply yet (polite bump)"
            prompt = (
                f"You represent {seller_name}. Draft a short B2B follow-up email as JSON with keys "
                f"subject, body, personalizedReason for {company_name}. Mode: {mode}. "
                f"Prior subject: {prior_subject}. Prior body: {prior_body[:600]}. "
                f"Reply summary: {reply_summary[:500]}. Context: {why_prospect}. "
                f"Sign as {seller_name}. Keep under 120 words."
            )
            parsed = parse_json_payload(self._complete(prompt))
            if isinstance(parsed, dict) and parsed.get("subject") and parsed.get("body"):
                return parsed
        except Exception:
            pass
        from app.providers.fallback import FallbackProvider
        return await FallbackProvider().generate_follow_up_outreach(
            company_name, why_prospect, prior_subject, prior_body, reply_summary, seller_name
        )
