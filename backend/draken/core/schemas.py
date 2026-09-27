"""Pydantic request/response schemas for the REST API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- projects --------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str
    domain: str
    base_url: str = ""
    description: str = ""
    country: str = "US"
    language: str = "en"
    industry: str = ""
    competitors: list[str] = Field(default_factory=list)
    brand_terms: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    description: str | None = None
    country: str | None = None
    language: str | None = None
    industry: str | None = None
    competitors: list[str] | None = None
    brand_terms: list[str] | None = None
    is_active: bool | None = None


class ProjectOut(ORMModel):
    id: int
    name: str
    domain: str
    base_url: str
    description: str
    country: str
    language: str
    industry: str
    competitors: list[str]
    brand_terms: list[str]
    is_active: bool
    created_at: datetime


# --- keywords --------------------------------------------------------------


class KeywordOut(ORMModel):
    id: int
    term: str
    country: str
    volume: int
    difficulty: float
    opportunity_score: float
    cpc: float
    competition: float
    intent: str
    word_count: int
    is_question: bool
    is_branded: bool
    cluster_id: int | None
    parent_topic: str
    is_tracked: bool
    source: str
    serp_features: list[Any]


class KeywordResearchRequest(BaseModel):
    seeds: list[str] = Field(..., min_length=1, description="Seed terms to expand from")
    country: str = "US"
    language: str = "en"
    include_questions: bool = True
    include_modifiers: bool = True
    include_alphabet_soup: bool = False
    max_results: int = Field(400, ge=1, le=5000)
    persist: bool = True
    use_live_suggest: bool = True


class KeywordManualAdd(BaseModel):
    terms: list[str] = Field(..., min_length=1)
    country: str = "US"
    track: bool = False


class KeywordClusterOut(ORMModel):
    id: int
    label: str
    head_term: str
    total_volume: int
    avg_difficulty: float
    dominant_intent: str
    keyword_count: int
    recommended_page_type: str
    target_url: str


class KeywordGapRequest(BaseModel):
    competitors: list[str] = Field(default_factory=list)
    country: str = "US"
    limit: int = 200


# --- rank tracking ---------------------------------------------------------


class RankSnapshotOut(ORMModel):
    id: int
    keyword_id: int
    captured_on: date
    position: int | None
    previous_position: int | None
    url: str
    device: str
    estimated_traffic: float


class TrackRequest(BaseModel):
    keyword_ids: list[int] = Field(default_factory=list)
    device: str = "desktop"


# --- site audit ------------------------------------------------------------


class AuditRequest(BaseModel):
    max_pages: int = Field(100, ge=1, le=5000)
    max_depth: int = Field(4, ge=1, le=10)
    include_external_check: bool = False


class AuditIssueOut(ORMModel):
    id: int
    code: str
    severity: str
    title: str
    description: str
    how_to_fix: str
    url: str
    category: str
    detail: dict


class SiteAuditOut(ORMModel):
    id: int
    project_id: int
    state: str
    pages_crawled: int
    health_score: float
    issue_counts: dict
    summary: dict
    started_at: datetime | None
    finished_at: datetime | None
    error: str


# --- backlinks -------------------------------------------------------------


class BacklinkOut(ORMModel):
    id: int
    source_url: str
    source_domain: str
    target_url: str
    anchor_text: str
    link_type: str
    status: str
    domain_authority: float
    spam_score: float
    toxicity_score: float
    toxicity_reasons: list[Any]
    source_category: str
    first_seen: datetime
    last_checked: datetime | None
    discovered_via: str


class BacklinkImport(BaseModel):
    """Accepts a CSV paste or explicit rows from any external tool export."""

    rows: list[dict] = Field(default_factory=list)
    csv_text: str = ""
    discovered_via: str = "import"


class BacklinkProfileOut(BaseModel):
    total_links: int
    referring_domains: int
    dofollow_links: int
    nofollow_links: int
    live_links: int
    lost_links: int
    avg_domain_authority: float
    authority_score: float
    anchor_distribution: list[dict]
    anchor_health: dict
    top_domains: list[dict]
    category_mix: list[dict]
    toxic_links: int
    velocity: list[dict]
    recommendations: list[str]


# --- opportunities / campaigns --------------------------------------------


class OpportunityOut(ORMModel):
    id: int
    project_id: int
    source_id: int | None
    campaign_id: int | None
    target_domain: str
    target_url: str
    landing_url: str
    suggested_anchor: str
    tactic: str
    status: str
    score: float
    score_breakdown: dict
    authority: float
    relevance: float
    effort: int
    discovered_via: str
    competitor_links: int
    contact_email: str
    contact_form_url: str
    notes: str


class GenerateOpportunitiesRequest(BaseModel):
    categories: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    max_effort: int = Field(5, ge=1, le=5)
    only_free: bool = True
    only_dofollow: bool = False
    include_ai_sources: bool = True
    limit: int = Field(200, ge=1, le=2000)
    campaign_id: int | None = None


class OpportunityStatusUpdate(BaseModel):
    status: str
    notes: str | None = None
    landing_url: str | None = None
    suggested_anchor: str | None = None
    campaign_id: int | None = None


class CampaignCreate(BaseModel):
    name: str
    goal: str = ""
    tactics: list[str] = Field(default_factory=list)
    target_keywords: list[str] = Field(default_factory=list)
    landing_urls: list[str] = Field(default_factory=list)
    monthly_link_target: int = 10
    starts_on: date | None = None
    ends_on: date | None = None


class CampaignOut(ORMModel):
    id: int
    name: str
    goal: str
    tactics: list[Any]
    target_keywords: list[Any]
    landing_urls: list[Any]
    anchor_plan: dict
    monthly_link_target: int
    state: str
    starts_on: date | None
    ends_on: date | None


# --- link sources ----------------------------------------------------------


class LinkSourceOut(ORMModel):
    id: int
    slug: str
    name: str
    domain: str
    submit_url: str
    category: str
    authority: float
    link_type: str
    is_free: bool
    requires_account: bool
    automatable: bool
    effort: int
    countries: list[Any]
    industries: list[Any]
    tags: list[Any]
    required_fields: list[Any]
    guidelines_url: str
    notes: str
    ai_training_signal: bool
    llm_citation_weight: float
    is_enabled: bool
    health: str


# --- business profile / submissions ---------------------------------------


class BusinessProfileIn(BaseModel):
    legal_name: str = ""
    display_name: str = ""
    tagline: str = ""
    short_description: str = ""
    long_description: str = ""
    categories: list[str] = Field(default_factory=list)
    email: str = ""
    phone: str = ""
    website: str = ""
    street: str = ""
    city: str = ""
    region: str = ""
    postal_code: str = ""
    country: str = "US"
    latitude: float | None = None
    longitude: float | None = None
    founded_year: int | None = None
    employee_count: str = ""
    logo_url: str = ""
    social_profiles: dict = Field(default_factory=dict)
    opening_hours: list[Any] = Field(default_factory=list)
    payment_methods: list[str] = Field(default_factory=list)
    service_areas: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    extra_fields: dict = Field(default_factory=dict)


class BusinessProfileOut(BusinessProfileIn, ORMModel):
    id: int
    project_id: int


class SubmissionOut(ORMModel):
    id: int
    opportunity_id: int
    project_id: int
    state: str
    method: str
    payload: dict
    rendered_instructions: str
    live_url: str
    response_status: int | None
    response_excerpt: str
    attempts: int
    error: str
    dry_run: bool
    approved_at: datetime | None
    executed_at: datetime | None
    verified_at: datetime | None
    created_at: datetime


class PrepareSubmissionsRequest(BaseModel):
    opportunity_ids: list[int] = Field(default_factory=list)
    limit: int = Field(25, ge=1, le=500)
    auto_approve: bool = False


class ApproveSubmissionsRequest(BaseModel):
    submission_ids: list[int] = Field(..., min_length=1)
    approved_by: str = "operator"


class RunSubmissionsRequest(BaseModel):
    submission_ids: list[int] = Field(default_factory=list)
    limit: int = Field(10, ge=1, le=200)
    dry_run: bool | None = None


# --- outreach --------------------------------------------------------------


class OutreachTemplateIn(BaseModel):
    name: str
    tactic: str = "generic"
    subject: str
    body: str
    step_number: int = 1
    delay_days: int = 0
    language: str = "en"


class OutreachTemplateOut(ORMModel):
    id: int
    project_id: int | None
    name: str
    tactic: str
    subject: str
    body: str
    step_number: int
    delay_days: int
    language: str
    variables: list[Any]
    is_builtin: bool


class DraftOutreachRequest(BaseModel):
    opportunity_ids: list[int] = Field(..., min_length=1)
    template_id: int | None = None
    tactic: str = "generic"
    sender_name: str = ""
    sender_role: str = ""


class OutreachMessageOut(ORMModel):
    id: int
    project_id: int
    opportunity_id: int | None
    to_email: str
    to_name: str
    subject: str
    body: str
    state: str
    step_number: int
    scheduled_for: datetime | None
    sent_at: datetime | None
    error: str


# --- AI visibility ---------------------------------------------------------


class AIPromptIn(BaseModel):
    prompt: str
    category: str = "discovery"
    intent: str = "commercial"
    language: str = "en"
    priority: int = 3


class AIPromptOut(ORMModel):
    id: int
    prompt: str
    category: str
    intent: str
    language: str
    priority: int
    is_active: bool


class GeneratePromptsRequest(BaseModel):
    from_keywords: bool = True
    limit: int = Field(40, ge=1, le=500)
    extra_topics: list[str] = Field(default_factory=list)


class AIVisibilityRunOut(ORMModel):
    id: int
    prompt_id: int
    engine: str
    model: str
    answer: str
    brand_mentioned: bool
    brand_position: int | None
    domain_cited: bool
    citations: list[Any]
    competitors_mentioned: list[Any]
    sentiment: str
    visibility_score: float
    share_of_voice: float
    captured_at: datetime
    error: str


class RunAIVisibilityRequest(BaseModel):
    engines: list[str] = Field(default_factory=list)
    prompt_ids: list[int] = Field(default_factory=list)
    limit: int = Field(20, ge=1, le=200)


class AIVisibilitySummary(BaseModel):
    prompts_tracked: int
    runs: int
    mention_rate: float
    citation_rate: float
    avg_visibility_score: float
    share_of_voice: float
    by_engine: list[dict]
    competitor_share: list[dict]
    uncovered_prompts: list[dict]
    recommendations: list[str]
    engines_configured: dict


# --- on-page ---------------------------------------------------------------


class OnPageRequest(BaseModel):
    url: str
    target_keyword: str = ""
    secondary_keywords: list[str] = Field(default_factory=list)


# --- jobs ------------------------------------------------------------------


class JobOut(ORMModel):
    id: int
    kind: str
    project_id: int | None
    state: str
    params: dict
    result: dict
    progress: float
    message: str
    error: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


# --- auth ------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    token: str
    username: str
    expires_in_hours: int
