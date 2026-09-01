from typing import Dict, Any, List
from app.providers.base import AIProvider

class FallbackProvider(AIProvider):
    def name(self) -> str:
        return "Heuristic Fallback Provider"

    async def extract_business_profile(self, text: str) -> Dict[str, Any]:
        return {
            "name": "Apex Fitness Equipment",
            "website": "https://apexfitnessequipment.example.com",
            "target_markets": ["United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait", "Oman"],
            "primary_categories": ["Commercial Strength", "Free Weights", "Cardio Equipment"],
            "extracted_by_ai": True
        }

    async def extract_products(self, content: str, source_type: str = "text") -> List[Dict[str, Any]]:
        return [
            {
                "name": "Commercial Heavy-Duty Power Rack",
                "category": "Commercial Strength",
                "description": "3x3 11-gauge steel uprights with laser-cut numbering and safety spotter arms.",
                "price": "$1,850 - $2,400",
                "moq": "5 Units",
                "specs": ["11-gauge steel tube", "1000kg weight capacity"],
                "target_buyer": "Commercial Gyms, University Sports Complexes",
                "ai_extracted": True,
                "verified_by_user": True
            }
        ]

    async def analyze_buying_signals(self, company_text: str, custom_signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "signal": "New Location Opening Announced",
                "whyItMatters": "Indicates immediate equipment procurement need prior to opening.",
                "sourceExcerpt": "Opening new 15,000 sq ft flagship health club facility in Q4."
            }
        ]

    async def generate_personalized_outreach(
        self, 
        company_name: str, 
        why_prospect: str, 
        signals: List[Dict[str, Any]], 
        matched_products: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        product_name = "commercial strength equipment"
        if matched_products:
            first = matched_products[0]
            product_name = first.get("productName") or first.get("name") or product_name
        return {
            "subject": f"Custom {product_name} Solutions for {company_name}",
            "body": f"Hi Procurement Team,\n\nNoticed {company_name}'s recent growth and focus on commercial fitness facilities.\n\nWe manufacture heavy-duty 11-gauge commercial power racks and cable crossover stations directly for GCC commercial operators. Because we ship directly from our factory, we provide factory pricing and custom logo branding.\n\nWould you be open to reviewing a spec sheet?\n\nBest regards,\nApex Sales Team",
            "personalizedReason": f"Personalized based on {company_name}'s facility expansion and focus on high-capacity commercial equipment."
        }
