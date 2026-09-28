"""ORM models for the whole Draken suite.

Grouped by domain:
  * Projects & settings
  * Keyword intelligence
  * SERP / rank tracking
  * Site audit (crawler)
  * Backlink index & link profile
  * Link opportunities, campaigns, placements
  * Submissions (automated acquisition) & business profile / NAP
  * Outreach (contacts, templates, sequences, messages)
  * AI visibility / GEO
  * Jobs & audit log
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from draken.core.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SearchIntent(str, enum.Enum):
    informational = "informational"
    navigational = "navigational"
    commercial = "commercial"
    transactional = "transactional"
    local = "local"


class LinkType(str, enum.Enum):
    dofollow = "dofollow"
    nofollow = "nofollow"
    ugc = "ugc"
    sponsored = "sponsored"
    unknown = "unknown"


class LinkStatus(str, enum.Enum):
    live = "live"
    lost = "lost"
    broken = "broken"
    redirected = "redirected"
    pending = "pending"


class OpportunityStatus(str, enum.Enum):
    new = "new"
    qualified = "qualified"
    queued = "queued"
    in_progress = "in_progress"
    submitted = "submitted"
    awaiting_review = "awaiting_review"
    won = "won"
    rejected = "rejected"
    skipped = "skipped"


class SourceCategory(str, enum.Enum):
    directory = "directory"
    local_citation = "local_citation"
    business_profile = "business_profile"
    social_profile = "social_profile"
    developer_profile = "developer_profile"
    qa_community = "qa_community"
    forum = "forum"
    blog_platform = "blog_platform"
    press_release = "press_release"
    product_listing = "product_listing"
    startup_listing = "startup_listing"
    resource_page = "resource_page"
    guest_post = "guest_post"
    podcast = "podcast"
    review_platform = "review_platform"
    wiki = "wiki"
    edu_gov = "edu_gov"
    aggregator = "aggregator"
    ai_dataset = "ai_dataset"
    other = "other"


class SubmissionState(str, enum.Enum):
    draft = "draft"
    awaiting_approval = "awaiting_approval"
    approved = "approved"
    executing = "executing"
    submitted = "submitted"
    verified = "verified"
    failed = "failed"
    rejected = "rejected"
    manual_required = "manual_required"


class JobState(str, enum.Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class IssueSeverity(str, enum.Enum):
    critical = "critical"
    error = "error"
    warning = "warning"
    notice = "notice"


class UserRole(str, enum.Enum):
    owner = "owner"        # everything, including users and settings
    editor = "editor"      # runs scans and works the pipeline
    viewer = "viewer"      # reads reports only


class ShareScope(str, enum.Enum):
    report = "report"      # the scan report for one project
    backlinks = "backlinks"
    full = "full"


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    country: Mapped[str] = mapped_column(String(8), default="US")
    language: Mapped[str] = mapped_column(String(8), default="en")
    industry: Mapped[str] = mapped_column(String(120), default="")
    competitors: Mapped[list] = mapped_column(JSON, default=list)
    brand_terms: Mapped[list] = mapped_column(JSON, default=list)
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    keywords: Mapped[list[Keyword]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    backlinks: Mapped[list[Backlink]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    opportunities: Mapped[list[LinkOpportunity]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    campaigns: Mapped[list[Campaign]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    audits: Mapped[list[SiteAudit]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    business_profile: Mapped[BusinessProfile | None] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )


# ---------------------------------------------------------------------------
# Keyword intelligence
# ---------------------------------------------------------------------------


class Keyword(Base, TimestampMixin):
    __tablename__ = "keywords"
    __table_args__ = (
        UniqueConstraint("project_id", "term", "country", name="uq_keyword_project_term"),
        Index("ix_keyword_project_volume", "project_id", "volume"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    term: Mapped[str] = mapped_column(String(400), nullable=False, index=True)
    country: Mapped[str] = mapped_column(String(8), default="US")
    language: Mapped[str] = mapped_column(String(8), default="en")

    volume: Mapped[int] = mapped_column(Integer, default=0)
    volume_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    opportunity_score: Mapped[float] = mapped_column(Float, default=0.0)
    cpc: Mapped[float] = mapped_column(Float, default=0.0)
    competition: Mapped[float] = mapped_column(Float, default=0.0)
    intent: Mapped[str] = mapped_column(String(20), default=SearchIntent.informational.value)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    is_question: Mapped[bool] = mapped_column(Boolean, default=False)
    is_branded: Mapped[bool] = mapped_column(Boolean, default=False)
    serp_features: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(60), default="manual")
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("keyword_clusters.id", ondelete="SET NULL"), nullable=True
    )
    parent_topic: Mapped[str] = mapped_column(String(400), default="")
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="keywords")
    cluster: Mapped[KeywordCluster | None] = relationship(back_populates="keywords")
    rankings: Mapped[list[RankSnapshot]] = relationship(
        back_populates="keyword", cascade="all, delete-orphan"
    )


class KeywordCluster(Base, TimestampMixin):
    __tablename__ = "keyword_clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(300), nullable=False)
    head_term: Mapped[str] = mapped_column(String(400), default="")
    total_volume: Mapped[int] = mapped_column(Integer, default=0)
    avg_difficulty: Mapped[float] = mapped_column(Float, default=0.0)
    dominant_intent: Mapped[str] = mapped_column(String(20), default="")
    keyword_count: Mapped[int] = mapped_column(Integer, default=0)
    recommended_page_type: Mapped[str] = mapped_column(String(60), default="")
    target_url: Mapped[str] = mapped_column(String(500), default="")

    keywords: Mapped[list[Keyword]] = relationship(back_populates="cluster")


# ---------------------------------------------------------------------------
# SERP & rank tracking
# ---------------------------------------------------------------------------


class RankSnapshot(Base):
    __tablename__ = "rank_snapshots"
    __table_args__ = (
        UniqueConstraint("keyword_id", "captured_on", "device", name="uq_rank_kw_day"),
        Index("ix_rank_keyword_date", "keyword_id", "captured_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id", ondelete="CASCADE"))
    captured_on: Mapped[datetime] = mapped_column(Date, default=lambda: utcnow().date())
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str] = mapped_column(String(800), default="")
    device: Mapped[str] = mapped_column(String(12), default="desktop")
    serp_features: Mapped[list] = mapped_column(JSON, default=list)
    estimated_traffic: Mapped[float] = mapped_column(Float, default=0.0)
    provider: Mapped[str] = mapped_column(String(40), default="internal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    keyword: Mapped[Keyword] = relationship(back_populates="rankings")


class SerpResult(Base):
    """A cached SERP listing used for difficulty scoring and gap analysis."""

    __tablename__ = "serp_results"
    __table_args__ = (Index("ix_serp_term_country", "term", "country"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(400), nullable=False)
    country: Mapped[str] = mapped_column(String(8), default="US")
    position: Mapped[int] = mapped_column(Integer)
    url: Mapped[str] = mapped_column(String(800), default="")
    domain: Mapped[str] = mapped_column(String(255), default="", index=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    snippet: Mapped[str] = mapped_column(Text, default="")
    result_type: Mapped[str] = mapped_column(String(40), default="organic")
    domain_authority: Mapped[float] = mapped_column(Float, default=0.0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    provider: Mapped[str] = mapped_column(String(40), default="internal")


# ---------------------------------------------------------------------------
# Site audit
# ---------------------------------------------------------------------------


class SiteAudit(Base, TimestampMixin):
    __tablename__ = "site_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(20), default=JobState.pending.value)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0)
    health_score: Mapped[float] = mapped_column(Float, default=0.0)
    issue_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")

    project: Mapped[Project] = relationship(back_populates="audits")
    pages: Mapped[list[CrawledPage]] = relationship(
        back_populates="audit", cascade="all, delete-orphan"
    )
    issues: Mapped[list[AuditIssue]] = relationship(
        back_populates="audit", cascade="all, delete-orphan"
    )


class CrawledPage(Base):
    __tablename__ = "crawled_pages"
    __table_args__ = (Index("ix_page_audit_url", "audit_id", "url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("site_audits.id", ondelete="CASCADE"))
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(String(600), default="")
    meta_description: Mapped[str] = mapped_column(Text, default="")
    h1: Mapped[str] = mapped_column(String(600), default="")
    h2_count: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    internal_links: Mapped[int] = mapped_column(Integer, default=0)
    external_links: Mapped[int] = mapped_column(Integer, default=0)
    inlinks: Mapped[int] = mapped_column(Integer, default=0)
    images_without_alt: Mapped[int] = mapped_column(Integer, default=0)
    canonical: Mapped[str] = mapped_column(String(1000), default="")
    robots_meta: Mapped[str] = mapped_column(String(200), default="")
    response_ms: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    depth: Mapped[int] = mapped_column(Integer, default=0)
    has_schema: Mapped[bool] = mapped_column(Boolean, default=False)
    schema_types: Mapped[list] = mapped_column(JSON, default=list)
    hreflang: Mapped[list] = mapped_column(JSON, default=list)
    outlinks: Mapped[list] = mapped_column(JSON, default=list)
    ai_readiness: Mapped[float] = mapped_column(Float, default=0.0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    audit: Mapped[SiteAudit] = relationship(back_populates="pages")


class AuditIssue(Base):
    __tablename__ = "audit_issues"
    __table_args__ = (Index("ix_issue_audit_code", "audit_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("site_audits.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default=IssueSeverity.warning.value)
    title: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    how_to_fix: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(1000), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    category: Mapped[str] = mapped_column(String(40), default="technical")

    audit: Mapped[SiteAudit] = relationship(back_populates="issues")


# ---------------------------------------------------------------------------
# Backlinks
# ---------------------------------------------------------------------------


class Backlink(Base, TimestampMixin):
    __tablename__ = "backlinks"
    __table_args__ = (
        UniqueConstraint("project_id", "source_url", "target_url", name="uq_backlink_pair"),
        Index("ix_backlink_project_domain", "project_id", "source_domain"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    target_url: Mapped[str] = mapped_column(String(1000), default="")
    anchor_text: Mapped[str] = mapped_column(String(600), default="")
    link_type: Mapped[str] = mapped_column(String(20), default=LinkType.unknown.value)
    status: Mapped[str] = mapped_column(String(20), default=LinkStatus.live.value)
    domain_authority: Mapped[float] = mapped_column(Float, default=0.0)
    page_authority: Mapped[float] = mapped_column(Float, default=0.0)
    spam_score: Mapped[float] = mapped_column(Float, default=0.0)
    toxicity_score: Mapped[float] = mapped_column(Float, default=0.0)
    toxicity_reasons: Mapped[list] = mapped_column(JSON, default=list)
    is_image_link: Mapped[bool] = mapped_column(Boolean, default=False)
    is_sitewide: Mapped[bool] = mapped_column(Boolean, default=False)
    source_category: Mapped[str] = mapped_column(String(40), default="")
    source_country: Mapped[str] = mapped_column(String(8), default="")
    source_language: Mapped[str] = mapped_column(String(8), default="")
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_via: Mapped[str] = mapped_column(String(60), default="manual")
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("link_opportunities.id", ondelete="SET NULL"), nullable=True
    )
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="backlinks")


class CompetitorBacklink(Base):
    """Competitor links, used for link-intersect prospecting."""

    __tablename__ = "competitor_backlinks"
    __table_args__ = (
        Index("ix_compbl_project_competitor", "project_id", "competitor_domain"),
        UniqueConstraint(
            "project_id", "competitor_domain", "source_url", name="uq_compbl_unique"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    competitor_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    anchor_text: Mapped[str] = mapped_column(String(600), default="")
    link_type: Mapped[str] = mapped_column(String(20), default=LinkType.unknown.value)
    domain_authority: Mapped[float] = mapped_column(Float, default=0.0)
    discovered_via: Mapped[str] = mapped_column(String(60), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------------------
# Link source catalog & opportunities
# ---------------------------------------------------------------------------


class LinkSource(Base, TimestampMixin):
    """A reusable, catalog-level place where a link/citation can be earned."""

    __tablename__ = "link_sources"
    __table_args__ = (Index("ix_source_category_authority", "category", "authority"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    submit_url: Mapped[str] = mapped_column(String(800), default="")
    category: Mapped[str] = mapped_column(String(40), default=SourceCategory.directory.value)
    authority: Mapped[float] = mapped_column(Float, default=0.0)
    link_type: Mapped[str] = mapped_column(String(20), default=LinkType.unknown.value)
    is_free: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_account: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_moderation: Mapped[bool] = mapped_column(Boolean, default=True)
    automatable: Mapped[bool] = mapped_column(Boolean, default=False)
    effort: Mapped[int] = mapped_column(Integer, default=3)  # 1 (trivial) .. 5 (heavy)
    countries: Mapped[list] = mapped_column(JSON, default=list)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    industries: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    required_fields: Mapped[list] = mapped_column(JSON, default=list)
    guidelines_url: Mapped[str] = mapped_column(String(800), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    ai_training_signal: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_citation_weight: Mapped[float] = mapped_column(Float, default=0.0)
    adapter: Mapped[str] = mapped_column(String(80), default="")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    health: Mapped[str] = mapped_column(String(20), default="unknown")


class LinkOpportunity(Base, TimestampMixin):
    """A project-specific instance of a link chance (from catalog or prospecting)."""

    __tablename__ = "link_opportunities"
    __table_args__ = (
        UniqueConstraint("project_id", "target_domain", "source_id", name="uq_opp_unique"),
        Index("ix_opp_project_score", "project_id", "score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("link_sources.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    target_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    target_url: Mapped[str] = mapped_column(String(1000), default="")
    landing_url: Mapped[str] = mapped_column(String(1000), default="")
    suggested_anchor: Mapped[str] = mapped_column(String(400), default="")
    tactic: Mapped[str] = mapped_column(String(60), default="directory")
    status: Mapped[str] = mapped_column(String(24), default=OpportunityStatus.new.value)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    authority: Mapped[float] = mapped_column(Float, default=0.0)
    relevance: Mapped[float] = mapped_column(Float, default=0.0)
    effort: Mapped[int] = mapped_column(Integer, default=3)
    discovered_via: Mapped[str] = mapped_column(String(60), default="catalog")
    competitor_links: Mapped[int] = mapped_column(Integer, default=0)
    contact_email: Mapped[str] = mapped_column(String(320), default="")
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_form_url: Mapped[str] = mapped_column(String(800), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    won_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="opportunities")
    source: Mapped[LinkSource | None] = relationship()
    campaign: Mapped[Campaign | None] = relationship(back_populates="opportunities")
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="")
    tactics: Mapped[list] = mapped_column(JSON, default=list)
    target_keywords: Mapped[list] = mapped_column(JSON, default=list)
    landing_urls: Mapped[list] = mapped_column(JSON, default=list)
    anchor_plan: Mapped[dict] = mapped_column(JSON, default=dict)
    monthly_link_target: Mapped[int] = mapped_column(Integer, default=10)
    state: Mapped[str] = mapped_column(String(20), default="active")
    starts_on: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    ends_on: Mapped[datetime | None] = mapped_column(Date, nullable=True)

    project: Mapped[Project] = relationship(back_populates="campaigns")
    opportunities: Mapped[list[LinkOpportunity]] = relationship(back_populates="campaign")


# ---------------------------------------------------------------------------
# Submissions & business profile (NAP)
# ---------------------------------------------------------------------------


class BusinessProfile(Base, TimestampMixin):
    """Canonical NAP + brand data reused by every submission and citation."""

    __tablename__ = "business_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    legal_name: Mapped[str] = mapped_column(String(300), default="")
    display_name: Mapped[str] = mapped_column(String(300), default="")
    tagline: Mapped[str] = mapped_column(String(300), default="")
    short_description: Mapped[str] = mapped_column(Text, default="")
    long_description: Mapped[str] = mapped_column(Text, default="")
    categories: Mapped[list] = mapped_column(JSON, default=list)
    email: Mapped[str] = mapped_column(String(320), default="")
    phone: Mapped[str] = mapped_column(String(60), default="")
    website: Mapped[str] = mapped_column(String(500), default="")
    street: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str] = mapped_column(String(160), default="")
    region: Mapped[str] = mapped_column(String(160), default="")
    postal_code: Mapped[str] = mapped_column(String(40), default="")
    country: Mapped[str] = mapped_column(String(8), default="US")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_count: Mapped[str] = mapped_column(String(40), default="")
    logo_url: Mapped[str] = mapped_column(String(800), default="")
    social_profiles: Mapped[dict] = mapped_column(JSON, default=dict)
    opening_hours: Mapped[list] = mapped_column(JSON, default=list)
    payment_methods: Mapped[list] = mapped_column(JSON, default=list)
    service_areas: Mapped[list] = mapped_column(JSON, default=list)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    extra_fields: Mapped[dict] = mapped_column(JSON, default=dict)

    project: Mapped[Project] = relationship(back_populates="business_profile")


class Submission(Base, TimestampMixin):
    __tablename__ = "submissions"
    __table_args__ = (Index("ix_submission_state", "state", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("link_opportunities.id", ondelete="CASCADE")
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(24), default=SubmissionState.draft.value)
    method: Mapped[str] = mapped_column(String(24), default="manual")  # manual|http_form|browser|api
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    rendered_instructions: Mapped[str] = mapped_column(Text, default="")
    approved_by: Mapped[str] = mapped_column(String(120), default="")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_excerpt: Mapped[str] = mapped_column(Text, default="")
    live_url: Mapped[str] = mapped_column(String(1000), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)

    opportunity: Mapped[LinkOpportunity] = relationship(back_populates="submissions")


# ---------------------------------------------------------------------------
# Outreach
# ---------------------------------------------------------------------------


class OutreachTemplate(Base, TimestampMixin):
    __tablename__ = "outreach_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    tactic: Mapped[str] = mapped_column(String(60), default="generic")
    subject: Mapped[str] = mapped_column(String(400), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    step_number: Mapped[int] = mapped_column(Integer, default=1)
    delay_days: Mapped[int] = mapped_column(Integer, default=0)
    language: Mapped[str] = mapped_column(String(8), default="en")
    variables: Mapped[list] = mapped_column(JSON, default=list)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)


class OutreachMessage(Base, TimestampMixin):
    __tablename__ = "outreach_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("link_opportunities.id", ondelete="SET NULL"), nullable=True
    )
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("outreach_templates.id", ondelete="SET NULL"), nullable=True
    )
    to_email: Mapped[str] = mapped_column(String(320), default="")
    to_name: Mapped[str] = mapped_column(String(200), default="")
    subject: Mapped[str] = mapped_column(String(400), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(20), default="draft")
    step_number: Mapped[int] = mapped_column(Integer, default=1)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")


# ---------------------------------------------------------------------------
# AI visibility (GEO)
# ---------------------------------------------------------------------------


class AIPrompt(Base, TimestampMixin):
    """A question we want LLM assistants to answer in our favour."""

    __tablename__ = "ai_prompts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="discovery")
    intent: Mapped[str] = mapped_column(String(20), default=SearchIntent.commercial.value)
    language: Mapped[str] = mapped_column(String(8), default="en")
    keyword_id: Mapped[int | None] = mapped_column(
        ForeignKey("keywords.id", ondelete="SET NULL"), nullable=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    runs: Mapped[list[AIVisibilityRun]] = relationship(
        back_populates="prompt", cascade="all, delete-orphan"
    )


class AIVisibilityRun(Base):
    __tablename__ = "ai_visibility_runs"
    __table_args__ = (Index("ix_aivis_prompt_engine", "prompt_id", "engine", "captured_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    prompt_id: Mapped[int] = mapped_column(ForeignKey("ai_prompts.id", ondelete="CASCADE"))
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    engine: Mapped[str] = mapped_column(String(40), default="anthropic")
    model: Mapped[str] = mapped_column(String(80), default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    brand_mentioned: Mapped[bool] = mapped_column(Boolean, default=False)
    brand_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    domain_cited: Mapped[bool] = mapped_column(Boolean, default=False)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    competitors_mentioned: Mapped[list] = mapped_column(JSON, default=list)
    sentiment: Mapped[str] = mapped_column(String(20), default="neutral")
    visibility_score: Mapped[float] = mapped_column(Float, default=0.0)
    share_of_voice: Mapped[float] = mapped_column(Float, default=0.0)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    error: Mapped[str] = mapped_column(Text, default="")

    prompt: Mapped[AIPrompt] = relationship(back_populates="runs")


# ---------------------------------------------------------------------------
# Jobs & audit log
# ---------------------------------------------------------------------------


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_job_state_kind", "state", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    state: Mapped[str] = mapped_column(String(20), default=JobState.pending.value)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(String(500), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schedule_cron: Mapped[str] = mapped_column(String(80), default="")


class User(Base, TimestampMixin):
    """A person who can sign in. Small on purpose: this is an internal team tool."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), default="")
    display_name: Mapped[str] = mapped_column(String(200), default="")
    password_hash: Mapped[str] = mapped_column(String(300), default="")
    role: Mapped[str] = mapped_column(String(20), default=UserRole.editor.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Per-user AI key, so a colleague can use their own assistant rather than yours.
    ai_engine: Mapped[str] = mapped_column(String(40), default="")
    ai_api_key: Mapped[str] = mapped_column(String(300), default="")
    invite_token: Mapped[str] = mapped_column(String(80), default="", index=True)
    invite_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    settings_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ProjectMember(Base, TimestampMixin):
    """Which users can see which projects. Absent rows mean owner-only."""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_member_unique"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20), default=UserRole.editor.value)


class ShareLink(Base, TimestampMixin):
    """A read-only link to a report, for someone without an account."""

    __tablename__ = "share_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    scope: Mapped[str] = mapped_column(String(20), default=ShareScope.report.value)
    created_by: Mapped[str] = mapped_column(String(120), default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # A shared report can carry the AI brief so the recipient can use their own assistant.
    allow_ai_brief: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def is_valid(self) -> bool:
        if self.revoked:
            return False
        if self.expires_at is None:
            return True
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return expires > datetime.now(UTC)


class ActivityLog(Base):
    """Append-only trail for anything that touches the outside world."""

    __tablename__ = "activity_log"
    __table_args__ = (Index("ix_activity_created", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
