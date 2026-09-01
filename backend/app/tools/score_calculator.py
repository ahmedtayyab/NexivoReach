from typing import Dict, Any, List

class ScoreCalculatorTool:
    def name(self) -> str:
        return "ScoreCalculatorTool"

    def calculate_fit_score(
        self,
        company_industry: str,
        company_location: str,
        target_countries: List[str],
        buying_signals: List[Dict[str, Any]],
        product_matches: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Transparent 100-Point Formula:
        - Industry fit: max 25
        - Location fit: max 20
        - Product match: max 20
        - Buying signals: max 20
        - Company fit: max 15
        """
        # Industry fit
        industry_score = 25 if any(kw in company_industry.lower() for kw in ['gym', 'fitness', 'health club', 'sports']) else 15

        # Location fit (handling abbreviations like UAE, KSA)
        location_matched = False
        loc_lower = company_location.lower()
        for country in target_countries:
            c_lower = country.lower()
            if c_lower in loc_lower or (c_lower == 'united arab emirates' and ('uae' in loc_lower or 'dubai' in loc_lower or 'abu dhabi' in loc_lower)) or (c_lower == 'saudi arabia' and ('ksa' in loc_lower or 'riyadh' in loc_lower)):
                location_matched = True
                break

        location_score = 20 if location_matched else 10

        # Product match score
        high_fits = [p for p in product_matches if p.get('fitLevel') == 'High']
        product_score = 20 if len(high_fits) >= 2 else 15

        # Buying signals score
        signal_score = min(20, sum(sig.get('weight', 15) for sig in buying_signals)) if buying_signals else 10

        # Company scale fit
        company_fit = 10

        total_score = industry_score + location_score + product_score + signal_score + company_fit

        return {
            "total_score": min(100, total_score),
            "breakdown": {
                "industryFit": industry_score,
                "locationFit": location_score,
                "productMatch": product_score,
                "buyingSignals": signal_score,
                "companyFit": company_fit
            }
        }
