from typing import Optional, List
from sqlmodel import SQLModel, Field, JSON

class Business(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    name: str
    website: str
    description: str
    target_markets: List[str] = Field(default=[], sa_type=JSON)
    primary_categories: List[str] = Field(default=[], sa_type=JSON)
    extracted_by_ai: bool = True

class ProductItem(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    name: str
    category: str
    description: str
    price: Optional[str] = None
    moq: Optional[str] = None
    specs: List[str] = Field(default=[], sa_type=JSON)
    target_buyer: Optional[str] = None
    features: List[str] = Field(default=[], sa_type=JSON)
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    ai_extracted: bool = True
    verified_by_user: bool = False

class ICPConfig(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    target_buyer_types: List[str] = Field(default=[], sa_type=JSON)
    target_countries: List[str] = Field(default=[], sa_type=JSON)
    company_size: str = "Medium"
    min_deal_size: Optional[str] = None
    shipping_markets: List[str] = Field(default=[], sa_type=JSON)
    sales_constraints: List[str] = Field(default=[], sa_type=JSON)
    buying_signals: List[dict] = Field(default=[], sa_type=JSON)

class ProspectRecord(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    company_name: str
    website: str
    location: str
    industry: str
    company_size: str
    fit_score: int
    fit_breakdown: dict = Field(default={}, sa_type=JSON)
    why_this_prospect: str
    buying_signals: List[dict] = Field(default=[], sa_type=JSON)
    product_fit: List[dict] = Field(default=[], sa_type=JSON)
    recommended_approach: str
    outreach_draft: Optional[dict] = Field(default=None, sa_type=JSON)
    stage: str = "Qualified"
    discovered_at: str
    agent_timeline: List[dict] = Field(default=[], sa_type=JSON)

class AgentRunRecord(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    timestamp: str
    task: str
    duration_ms: int
    tools_used: List[str] = Field(default=[], sa_type=JSON)
    sources_count: int
    status: str
    decisions: List[dict] = Field(default=[], sa_type=JSON)
