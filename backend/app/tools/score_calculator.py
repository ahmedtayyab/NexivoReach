from typing import Dict, Any, List, Optional


class ScoreCalculatorTool:
    def name(self) -> str:
        return "ScoreCalculatorTool"

    def calculate_fit_score(
        self,
        company_industry: str,
        company_location: str,
        target_countries: List[str],
        buying_signals: List[Dict[str, Any]],
        product_matches: List[Dict[str, Any]],
        target_buyer_types: Optional[List[str]] = None,
        research_text: str = "",
    ) -> Dict[str, Any]:
        """
        Transparent 100-Point Formula:
        - Industry fit: max 25
        - Location fit: max 20
        - Product match: max 20
        - Buying signals: max 20
        - Company fit: max 15
        """
        industry_score = self._industry_fit(
            company_industry=company_industry,
            research_text=research_text,
            target_buyer_types=target_buyer_types or [],
        )
        location_score = self._location_fit(company_location, target_countries or [])

        high_fits = [p for p in product_matches if p.get("fitLevel") == "High"]
        if not product_matches:
            product_score = 8
        elif len(high_fits) >= 2:
            product_score = 20
        elif len(high_fits) == 1:
            product_score = 16
        else:
            product_score = 12

        if buying_signals:
            signal_score = min(20, sum(int(sig.get("weight", 10)) for sig in buying_signals))
        else:
            signal_score = 8

        company_fit = 12 if (company_industry or research_text) else 8
        total_score = industry_score + location_score + product_score + signal_score + company_fit

        return {
            "total_score": min(100, total_score),
            "breakdown": {
                "industryFit": industry_score,
                "locationFit": location_score,
                "productMatch": product_score,
                "buyingSignals": min(20, signal_score),
                "companyFit": company_fit,
            },
        }

    def _industry_fit(self, company_industry: str, research_text: str, target_buyer_types: List[str]) -> int:
        blob = f"{company_industry} {research_text}".lower()
        if not target_buyer_types:
            return 15 if company_industry else 10
        hits = 0
        for buyer in target_buyer_types:
            tokens = [t for t in buyer.lower().replace("/", " ").split() if len(t) > 3]
            if buyer.lower() in blob or (tokens and all(t in blob for t in tokens[:2])):
                hits += 1
            elif tokens and any(t in blob for t in tokens):
                hits += 1
        if hits >= 2:
            return 25
        if hits == 1:
            return 20
        return 12

    def _location_fit(self, company_location: str, target_countries: List[str]) -> int:
        if not target_countries:
            return 15
        loc = (company_location or "").lower()
        aliases = {
            "united arab emirates": ["uae", "dubai", "abu dhabi", "sharjah"],
            "saudi arabia": ["ksa", "riyadh", "jeddah"],
            "united states": ["usa", "u.s.", "united states of america"],
            "united kingdom": ["uk", "britain", "england"],
        }
        for country in target_countries:
            c = country.lower().strip()
            if not c:
                continue
            if c in loc:
                return 20
            for alias in aliases.get(c, []):
                if alias in loc:
                    return 20
            # Also match short names the user typed (Germany, India, etc.)
            token = c.split(",")[0].strip()
            if len(token) > 3 and token in loc:
                return 20
        return 8
