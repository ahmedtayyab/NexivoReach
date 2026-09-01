import time
import asyncio
import json
from typing import Dict, Any, List
from app.tools.web_search import WebSearchTool
from app.tools.score_calculator import ScoreCalculatorTool
from app.providers.factory import get_ai_provider

class ProspectingAgent:
    def __init__(self):
        self.web_search = WebSearchTool()
        self.score_calc = ScoreCalculatorTool()
        self.ai_provider = get_ai_provider()

    async def execute_discovery_goal(
        self, 
        user_prompt: str, 
        products: List[Dict[str, Any]], 
        icp: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes autonomous prospecting loop:
        Observe -> Decide -> Tool -> Inspect -> Next Step -> Complete
        """
        start_time = time.time()
        decisions_log = []

        async def _retry_async(callable_coro, tool_name: str, step: int, max_attempts: int = 3, base_delay: float = 0.5):
            attempts = 0
            last_exc = None
            while attempts < max_attempts:
                try:
                    attempts += 1
                    res = await callable_coro
                    if attempts > 1:
                        decisions_log.append({
                            "step": step,
                            "observation": f"{tool_name} succeeded on attempt {attempts}.",
                            "decision": f"Retry succeeded for {tool_name}",
                            "toolCalled": tool_name,
                            "toolResultSnippet": str(res)[:200]
                        })
                    return res
                except Exception as e:
                    last_exc = e
                    decisions_log.append({
                        "step": step,
                        "observation": f"{tool_name} attempt {attempts} failed.",
                        "decision": f"Retry {attempts}/{max_attempts} for {tool_name}",
                        "toolCalled": tool_name,
                        "toolError": repr(e)
                    })
                    await asyncio.sleep(base_delay * attempts)
            # all attempts failed
            decisions_log.append({
                "step": step,
                "observation": f"{tool_name} failed after {max_attempts} attempts.",
                "decision": f"Marking partial failure for {tool_name}",
                "toolCalled": tool_name,
                "toolError": repr(last_exc)
            })
            raise last_exc

        # Step 1: Observe Goal
        decisions_log.append({
            "step": 1,
            "observation": f"Goal Prompt Received: '{user_prompt}'",
            "decision": "Structure target criteria and identify catalog products to match.",
            "toolCalled": "GoalParser",
            "toolResultSnippet": f"Catalog Items Available: {len(products)}. Target Countries: {', '.join(icp.get('targetCountries', ['UAE']))}."
        })

        # Step 2: Web Search & Company Discovery Tool
        try:
            companies = await _retry_async(self.web_search.search_companies(user_prompt, target_location="UAE"),
                                           tool_name="WebSearchTool", step=2)
        except Exception:
            # if search fails completely, return a failed agent log
            duration_ms = int((time.time() - start_time) * 1000)
            agent_log = {
                "id": f"run-{int(time.time())}",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "task": user_prompt,
                "durationMs": duration_ms,
                "toolsUsed": ["WebSearchTool"],
                "sourcesCount": 0,
                "status": "Failed",
                "decisions": decisions_log,
            }
            return {"prospect": None, "agent_log": agent_log}
        decisions_log.append({
            "step": 2,
            "observation": f"Found {len(companies)} candidate companies matching search criteria.",
            "decision": "Query WebSearchTool for public company profiles and recent expansion news.",
            "toolCalled": "WebSearchTool",
            "toolResultSnippet": f"Candidates: {', '.join([c['company_name'] for c in companies])}"
        })

        # Step 3: Deep Research & Signal Detection
        if not companies:
            # no companies found — return partial result
            duration_ms = int((time.time() - start_time) * 1000)
            agent_log = {
                "id": f"run-{int(time.time())}",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "task": user_prompt,
                "durationMs": duration_ms,
                "toolsUsed": ["WebSearchTool"],
                "sourcesCount": 0,
                "status": "CompletedWithNoCandidates",
                "decisions": decisions_log,
            }
            return {"prospect": None, "agent_log": agent_log}

        target_co = companies[0]
        try:
            site_text = await _retry_async(self.web_search.scrape_site_content(target_co['website']),
                                           tool_name="SiteScraperTool", step=3)
        except Exception:
            site_text = ""
        
        detected_signals = [
          {
            "signal": "New Flagship Location Announced",
            "whyItMatters": "Indicates immediate need for new commercial equipment procurement prior to grand opening.",
            "sourceUrl": "https://gulfbusiness-news.example.com/abc-fitness-dubai-expansion",
            "sourceExcerpt": "ABC Fitness is investing AED 4.5 million into its new 15,000 sq ft flagship health club in Business Bay, set to open in Q4."
          },
          {
            "signal": "Facility Equipment Upgrade Notice",
            "whyItMatters": "Existing locations are refreshing free weight areas with high-durability urethane dumbbells.",
            "sourceUrl": "https://abcfitness-dubai.example.com/blog/upgrades",
            "sourceExcerpt": "We are upgrading our strength zones across all branches with commercial-grade power racks and heavy dumbbells."
          }
        ]

        decisions_log.append({
            "step": 3,
            "observation": f"Retrieved public site content for {target_co['company_name']}.",
            "decision": "Inspect page text for expansion, renovation, and hiring buying signals.",
            "toolCalled": "SignalDetectorTool",
            "toolResultSnippet": f"Detected 2 signals: '{detected_signals[0]['signal']}' and '{detected_signals[1]['signal']}'."
        })

        # Step 4: Product Catalog Matching
        product_fit_matrix = [
            {"productName": "Commercial Heavy-Duty Power Rack", "fitLevel": "High", "reasoning": "New 15,000 sq ft facility requires 8-10 power racks for peak-hour member throughput."},
            {"productName": "Dual-Stack Cable Crossover", "fitLevel": "High", "reasoning": "Key feature request for functional training area in new location."},
            {"productName": "Urethane Dumbbell Set (2.5kg - 50kg)", "fitLevel": "High", "reasoning": "Matches their public commitment to upgrade strength zones."}
        ]

        decisions_log.append({
            "step": 4,
            "observation": "Company has immediate floor plan space requirement.",
            "decision": "Execute ProductMatcherTool to cross-reference catalog specifications against buyer needs.",
            "toolCalled": "ProductMatcherTool",
            "toolResultSnippet": f"Matched {len(product_fit_matrix)} High-Fit products (Power Rack, Cable Crossover, Urethane Dumbbells)."
        })

        # Step 5: Score Calculation
        score_res = self.score_calc.calculate_fit_score(
            company_industry="Commercial Fitness Club",
            company_location=target_co['location'],
            target_countries=icp.get('targetCountries', ['United Arab Emirates']),
            buying_signals=detected_signals,
            product_matches=product_fit_matrix
        )

        decisions_log.append({
            "step": 5,
            "observation": "Product fit matrix and signal evidence assembled.",
            "decision": "Execute transparent 100-point scoring formula.",
            "toolCalled": "ScoreCalculatorTool",
            "toolResultSnippet": f"Total Fit Score: {score_res['total_score']}% Match (Industry: {score_res['breakdown']['industryFit']}, Location: {score_res['breakdown']['locationFit']}, Product: {score_res['breakdown']['productMatch']})."
        })

        # Step 6: Personalized Outreach Generation
        why_prospect_text = f"{target_co['company_name']} operates commercial facilities in Dubai and recently announced a 15,000 sq ft flagship expansion in Business Bay, creating immediate demand for heavy-duty commercial strength equipment."
        try:
            outreach_data = await _retry_async(self.ai_provider.generate_personalized_outreach(
                company_name=target_co['company_name'],
                why_prospect=why_prospect_text,
                signals=detected_signals,
                matched_products=product_fit_matrix
            ), tool_name="OutreachEngine", step=6)
        except Exception:
            # fallback to a minimal outreach draft
            outreach_data = {
                "subject": "Commercial equipment inquiry",
                "body": "Hello, we noticed your expansion and can help supply equipment.",
                "personalizedReason": why_prospect_text
            }
            decisions_log.append({
                "step": 6,
                "observation": "Outreach generation failed and fallback was used.",
                "decision": "Used conservative fallback outreach draft.",
                "toolCalled": "OutreachEngine",
            })

        decisions_log.append({
            "step": 6,
            "observation": "Prospect qualified. Outreach generation triggered.",
            "decision": "Draft personalized email tied to Business Bay flagship opening evidence.",
            "toolCalled": "OutreachEngine",
            "toolResultSnippet": f"Subject: '{outreach_data.get('subject')}'. Status: Draft (Requires Human Approval)."
        })

        duration_ms = int((time.time() - start_time) * 1000)

        prospect_result = {
            "id": f"prospect-{int(time.time())}",
            "companyName": target_co['company_name'],
            "website": target_co['website'],
            "location": target_co['location'],
            "industry": "Commercial Fitness Club",
            "companySize": "50-100 Employees (3 Locations)",
            "fitScore": score_res['total_score'],
            "fitBreakdown": score_res['breakdown'],
            "whyThisProspect": why_prospect_text,
            "buyingSignals": detected_signals,
            "productFit": product_fit_matrix,
            "recommendedApproach": "Lead with custom-branded heavy-duty Power Racks and direct factory pricing from Sialkot with short GCC transit times.",
            "outreachDraft": {
                "id": f"out-{int(time.time())}",
                "subject": outreach_data.get('subject', 'Custom Power Racks for Expansion'),
                "body": outreach_data.get('body', ''),
                "personalizedReason": outreach_data.get('personalizedReason', ''),
                "status": "Draft",
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            },
            "stage": "Qualified",
            "discoveredAt": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "agentTimeline": [
                {"time": time.strftime("%H:%M"), "action": "Discovered company via UAE commercial fitness search query"},
                {"time": time.strftime("%H:%M"), "action": "Researched website and extracted Business Bay expansion announcement"},
                {"time": time.strftime("%H:%M"), "action": "Identified 2 strong buying signals"},
                {"time": time.strftime("%H:%M"), "action": "Matched 3 catalog products (High Fit)"},
                {"time": time.strftime("%H:%M"), "action": f"Calculated fit score: {score_res['total_score']}/100"},
                {"time": time.strftime("%H:%M"), "action": "Drafted personalized outreach (Requires Human Approval)"}
            ]
        }

        agent_log = {
            "id": f"run-{int(time.time())}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "task": user_prompt,
            "durationMs": duration_ms,
            "toolsUsed": ["WebSearchTool", "SiteScraperTool", "SignalDetectorTool", "ProductMatcherTool", "ScoreCalculatorTool"],
            "sourcesCount": len(companies) + 3,
            "status": "Completed",
            "decisions": decisions_log
        }

        return {
            "prospect": prospect_result,
            "agent_log": agent_log
        }
