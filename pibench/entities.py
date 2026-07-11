"""Entity dataclasses. Fields prefixed with ``h_`` are hidden from the agent."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Applicant:
    id: str
    season_year: int          # 0-based academic year
    pool: str                 # hidden in DB exports
    name: str
    transcript: float         # observable signal
    letter: float             # observable signal
    interview: float | None = None   # observable after interviewing
    h_ability: float = 0.0
    h_speed: float = 1.0
    h_resilience: float = 0.7
    h_independence: float = 0.6
    h_growth: float = 1.0
    status: str = "pending"   # pending | offered | accepted | declined | expired
    interviewed: bool = False


@dataclass
class Student:
    id: str
    name: str
    role: str                 # phd | postdoc
    arrived_month: int
    stipend: float
    h_ability: float = 0.5
    h_speed: float = 1.0
    h_resilience: float = 0.7
    h_independence: float = 0.6
    h_growth: float = 1.0
    skill: float = 0.5
    h_morale: float = 0.75
    mentoring: float = 0.0    # hours/month currently allocated by the PI
    status: str = "active"    # active | quit | graduated | contract_ended
    left_month: int | None = None
    papers_accepted: int = 0
    first_author_accepted: int = 0
    contract_end: int | None = None   # postdocs only
    # monthly observable history: (month, report_quality, sentiment or None)
    reports: list = field(default_factory=list)


@dataclass
class Project:
    id: str
    topic: str
    tier: int
    members: list
    compute: float            # monthly compute units
    started_month: int
    work_required: float
    progress: float = 0.0
    novelty: float = 1.0
    h_feasible: bool = True
    status: str = "active"    # active | completed | deadend | killed
    ended_month: int | None = None
    scooped_times: int = 0
    pending_scoop_news: int | None = None   # month at which scoop news is published
    draft_id: str | None = None
    # accumulators so draft quality reflects the whole project life, not the last
    # tick (prevents one-month compute spikes / late-unassignment exploits)
    ticks: int = 0
    compute_accum: float = 0.0
    ka_accum: float = 0.0      # effort-weighted sum of mean(skill*ability)
    ka_weight: float = 0.0
    # hidden start context for skill-axis metrics (not exposed to the agent)
    h_hot_at_start: float = 1.0
    h_future_hot: float = 1.0  # mean hotness over the next 12 months at start
    h_runway_at_start: float = 0.0
    h_idle_at_start: int = 0


@dataclass
class Draft:
    id: str
    project_id: str | None
    topic: str
    tier: int
    authors: list             # student ids ([] for collab drafts)
    created_month: int
    q: float                  # latent quality (hidden); agent sees reviewer feedback only
    polish_hours: float = 0.0
    revisions: int = 0
    collab: bool = False
    status: str = "available" # available | under_review | accepted | published
    salvage: bool = False


@dataclass
class Submission:
    id: str
    draft_id: str
    venue: str
    submitted_month: int
    decision_month: int
    status: str = "under_review"   # under_review | accept | reject | withdrawn
    reviewer_scores: list | None = None


@dataclass
class Publication:
    id: str
    draft_id: str
    venue: str
    topic: str
    tier: int
    authors: list
    q: float
    published_month: int
    collab: bool = False
    citations: int = 0
    cite_history: list = field(default_factory=list)   # (month, count)


@dataclass
class GrantCall:
    id: str
    agency: str
    open_month: int
    close_month: int          # last month a proposal is accepted
    award: float
    duration: int


@dataclass
class Proposal:
    id: str
    call_id: str
    agency: str
    topic: str
    hours: float
    attached: list            # draft/publication ids
    submitted_month: int
    decision_month: int
    status: str = "pending"   # pending | funded | rejected
    h_quality: float = 0.0


@dataclass
class Award:
    id: str
    proposal_id: str
    agency: str
    total: float
    start_month: int
    end_month: int
    monthly: float


@dataclass
class EventItem:
    id: str
    kind: str                 # invited_talk | review_request | student_crisis | collab_offer | ...
    month: int
    expires: int
    payload: dict = field(default_factory=dict)
    status: str = "pending"   # pending | accepted | declined | expired | auto_ignored


@dataclass
class NewsItem:
    month: int
    kind: str                 # field | funding | compute | scoop | conference
    topic: str | None
    text: str
