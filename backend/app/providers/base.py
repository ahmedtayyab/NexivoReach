from abc import ABC, abstractmethod
from typing import Dict, Any, List


class AIProvider(ABC):
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def extract_business_profile(self, text: str) -> Dict[str, Any]:
        """Extract structured business profile from natural language description."""
        pass

    @abstractmethod
    async def extract_products(self, content: str, source_type: str = "text") -> List[Dict[str, Any]]:
        """Extract structured products from text/web page/document."""
        pass

    @abstractmethod
    async def analyze_buying_signals(self, company_text: str, custom_signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Identify buying signals in company content."""
        pass

    @abstractmethod
    async def match_catalog_products(
        self,
        products: List[Dict[str, Any]],
        company_text: str,
        company_name: str,
    ) -> List[Dict[str, Any]]:
        """Match seller catalog items against a researched buyer."""
        pass

    @abstractmethod
    async def generate_personalized_outreach(
        self,
        company_name: str,
        why_prospect: str,
        signals: List[Dict[str, Any]],
        matched_products: List[Dict[str, Any]],
        seller_name: str = "Sales Team",
    ) -> Dict[str, str]:
        """Draft personalized B2B outreach email."""
        pass
