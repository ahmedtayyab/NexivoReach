from typing import Optional, List
from sqlmodel import SQLModel, Field, JSON


class Business(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    user_id: Optional[str] = Field(default=None, index=True)
    name: str = ""
    website: str = ""
    description: str = ""
    target_markets: List[str] = Field(default=[], sa_type=JSON)
    primary_categories: List[str] = Field(default=[], sa_type=JSON)
    extracted_by_ai: bool = True
    updated_at: str = ""
    # Per-company Google Sheet (not shared across users/businesses)
    sheets_spreadsheet_id: Optional[str] = Field(default=None)
    sheets_spreadsheet_title: Optional[str] = Field(default=None)


class ProductItem(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    name: str
    category: str
    description: str
    price: Optional[str] = None
    moq: Optional[str] = None
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    source_url: Optional[str] = None
    in_stock: Optional[bool] = None
    user_id: Optional[str] = Field(default=None, index=True)
    business_id: Optional[str] = Field(default=None, index=True)


class ICPConfig(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)  # same as business_id
    business_id: Optional[str] = Field(default=None, index=True)
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
    user_id: Optional[str] = Field(default=None, index=True)
    business_id: Optional[str] = Field(default=None, index=True)
    source: Optional[str] = None
    phone: Optional[str] = None
    why_now: Optional[str] = None
    email: Optional[str] = None
    contacts: List[dict] = Field(default=[], sa_type=JSON)
    contact_again: bool = True
    last_reply_at: Optional[str] = None
    reply_summary: Optional[str] = None


class AgentRunRecord(SQLModel, table=True):
    id: Optional[str] = Field(default=None, primary_key=True)
    timestamp: str
    task: str
    duration_ms: int
    tools_used: List[str] = Field(default=[], sa_type=JSON)
    sources_count: int
    status: str
    decisions: List[dict] = Field(default=[], sa_type=JSON)
    user_id: Optional[str] = Field(default=None, index=True)
    business_id: Optional[str] = Field(default=None, index=True)


class User(SQLModel, table=True):
    # Explicit name avoids Postgres treating bare "user" as a reserved keyword.
    __tablename__ = "nr_user"

    id: Optional[str] = Field(default=None, primary_key=True)
    google_id: str = Field(index=True, unique=True)
    email: str
    name: str = ""
    picture: str = ""
    created_at: str = ""
    active_business_id: Optional[str] = Field(default=None, index=True)
    # Access control / SaaS scaffolding
    is_admin: bool = False
    is_suspended: bool = False
    plan: str = "pilot"  # free | pilot | pro | growth
    # When true, daily hunt/extract/prepare/send caps are not enforced (still counted).
    usage_unlimited: bool = False
    daily_hunt_limit: Optional[int] = Field(default=None)
    daily_extract_limit: Optional[int] = Field(default=None)
    daily_prepare_limit: Optional[int] = Field(default=None)
    daily_send_limit: Optional[int] = Field(default=None)
    # User Gmail OAuth (separate from login session)
    gmail_refresh_token: Optional[str] = Field(default=None)
    gmail_access_token: Optional[str] = Field(default=None)
    gmail_token_expiry: Optional[str] = Field(default=None)  # ISO UTC
    gmail_email: Optional[str] = Field(default=None)
    gmail_connected_at: Optional[str] = Field(default=None)
    # User Google Sheets / Drive OAuth (writes to their Drive, not a shared SA)
    sheets_refresh_token: Optional[str] = Field(default=None)
    sheets_access_token: Optional[str] = Field(default=None)
    sheets_token_expiry: Optional[str] = Field(default=None)
    sheets_email: Optional[str] = Field(default=None)
    sheets_connected_at: Optional[str] = Field(default=None)
    # Stripe billing (optional — set via Checkout / webhooks)
    stripe_customer_id: Optional[str] = Field(default=None, index=True)
    stripe_subscription_id: Optional[str] = Field(default=None)
    plan_status: str = "none"  # none | active | past_due | canceled


class DiscoveryJob(SQLModel, table=True):
    """Durable hunt job with pollable progress (survives client disconnect)."""

    __tablename__ = "discovery_job"

    id: Optional[str] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    business_id: str = Field(index=True)
    status: str = "queued"  # queued | running | completed | failed
    phase: str = "queued"
    progress: int = 0  # 0–100
    found_count: int = 0
    skipped_existing: int = 0
    error: str = ""
    user_prompt: str = ""
    request_payload: dict = Field(default={}, sa_type=JSON)
    result_prospect_ids: List[str] = Field(default=[], sa_type=JSON)
    agent_log_id: Optional[str] = Field(default=None)
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None


class BusinessMember(SQLModel, table=True):
    """Team seat on a company workspace (owner is Business.user_id)."""

    __tablename__ = "business_member"

    id: Optional[str] = Field(default=None, primary_key=True)
    business_id: str = Field(index=True)
    user_id: Optional[str] = Field(default=None, index=True)  # set when invite accepted
    email: str = Field(index=True)
    role: str = "member"  # member | admin
    status: str = "pending"  # pending | active
    invited_by: str = ""
    created_at: str = ""
    accepted_at: Optional[str] = None


class InviteAllowlist(SQLModel, table=True):
    """Emails allowed to create an account when INVITE_ONLY is on."""

    __tablename__ = "invite_allowlist"

    email: str = Field(primary_key=True)
    note: str = ""
    created_at: str = ""
    created_by: str = ""


class UsageDaily(SQLModel, table=True):
    """UTC-day counters for pooled API cost control."""

    __tablename__ = "usage_daily"

    id: Optional[str] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    day: str = Field(index=True)  # YYYY-MM-DD UTC
    hunts: int = 0
    extracts: int = 0
    prepares: int = 0
    sends: int = 0


class Notification(SQLModel, table=True):
    """In-app notification for a single user."""

    __tablename__ = "notification"

    id: Optional[str] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    kind: str = "info"  # info | warn | usage | system | ticket
    title: str = ""
    body: str = ""
    href: Optional[str] = None
    read_at: Optional[str] = None
    created_at: str = ""
    meta: dict = Field(default={}, sa_type=JSON)


class SupportTicket(SQLModel, table=True):
    """Customer support ticket (simple: one body + admin reply)."""

    __tablename__ = "support_ticket"

    id: Optional[str] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    subject: str = ""
    body: str = ""
    status: str = "open"  # open | in_progress | resolved | closed
    priority: str = "normal"  # low | normal | high
    category: str = "general"  # general | billing | limits | bug
    admin_reply: str = ""
    attachments: list = Field(default=[], sa_type=JSON)  # [{id, name, mime, size}]
    created_at: str = ""
    updated_at: str = ""
    resolved_at: Optional[str] = None
