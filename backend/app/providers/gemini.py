import json
from typing import Dict, Any, List
from app.providers.base import AIProvider
from app.config import settings

class GeminiProvider(AIProvider):
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.available = bool(self.api_key)

    def name(self) -> str:
        return "Google Gemini API Provider"

    async def extract_business_profile(self, text: str) -> Dict[str, Any]:
        if not self.available:
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().extract_business_profile(text)
        
        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            prompt = f"Extract structured JSON with keys (name, website, target_markets, primary_categories) from: {text}"
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            # Try multiple ways to extract JSON from the provider response
            resp_text = getattr(response, 'text', None) or getattr(response, 'content', None)
            if resp_text:
                try:
                    return json.loads(resp_text)
                except Exception:
                    pass
            # Fallback: try dict/obj conversion if available
            try:
                as_dict = getattr(response, 'to_dict', None)
                if callable(as_dict):
                    return as_dict()
                data = getattr(response, 'data', None)
                if data:
                    return data
            except Exception:
                pass
            # If parsing fails, defer to fallback provider
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().extract_business_profile(text)
        except Exception:
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().extract_business_profile(text)

    async def extract_products(self, content: str, source_type: str = "text") -> List[Dict[str, Any]]:
        if not self.available:
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().extract_products(content, source_type)

        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            prompt = f"Extract an array of products as JSON from the following {source_type} content: {content}"
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            resp_text = getattr(response, 'text', None) or getattr(response, 'content', None)
            if resp_text:
                try:
                    prods = json.loads(resp_text)
                    return prods if isinstance(prods, list) else []
                except Exception:
                    pass
            as_dict = getattr(response, 'to_dict', None)
            if callable(as_dict):
                data = as_dict()
                if isinstance(data, list):
                    return data
            data = getattr(response, 'data', None)
            if isinstance(data, list):
                return data
        except Exception:
            pass

        from app.providers.fallback import FallbackProvider
        return await FallbackProvider().extract_products(content, source_type)

    async def analyze_buying_signals(self, company_text: str, custom_signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.available:
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().analyze_buying_signals(company_text, custom_signals)

        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            prompt = f"Identify buying signals in the following company text. Return a JSON array of signals with keys (signal, whyItMatters, sourceExcerpt): {company_text}\nCustomSignals:{custom_signals}"
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            resp_text = getattr(response, 'text', None) or getattr(response, 'content', None)
            if resp_text:
                try:
                    sigs = json.loads(resp_text)
                    return sigs if isinstance(sigs, list) else []
                except Exception:
                    pass
            as_dict = getattr(response, 'to_dict', None)
            if callable(as_dict):
                data = as_dict()
                if isinstance(data, list):
                    return data
            data = getattr(response, 'data', None)
            if isinstance(data, list):
                return data
        except Exception:
            pass

        from app.providers.fallback import FallbackProvider
        return await FallbackProvider().analyze_buying_signals(company_text, custom_signals)

    async def generate_personalized_outreach(
        self, 
        company_name: str, 
        why_prospect: str, 
        signals: List[Dict[str, Any]], 
        matched_products: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        if not self.available:
            from app.providers.fallback import FallbackProvider
            return await FallbackProvider().generate_personalized_outreach(company_name, why_prospect, signals, matched_products)

        try:
            from google import genai
            client = genai.Client(api_key=self.api_key)
            prompt = (
                f"Draft a personalized outreach email subject, body, and personalizedReason as JSON for {company_name}. "
                f"Context: {why_prospect}. Signals: {signals}. MatchedProducts: {matched_products}"
            )
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            resp_text = getattr(response, 'text', None) or getattr(response, 'content', None)
            if resp_text:
                try:
                    out = json.loads(resp_text)
                    return out if isinstance(out, dict) else {}
                except Exception:
                    pass
            as_dict = getattr(response, 'to_dict', None)
            if callable(as_dict):
                data = as_dict()
                if isinstance(data, dict):
                    return data
            data = getattr(response, 'data', None)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        from app.providers.fallback import FallbackProvider
        return await FallbackProvider().generate_personalized_outreach(company_name, why_prospect, signals, matched_products)
