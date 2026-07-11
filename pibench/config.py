"""All world parameters in one place. Values follow SPEC.md; the spec is normative."""
from __future__ import annotations

from dataclasses import dataclass, field


TOPICS = [
    "sparse_models", "ai4science", "embodied", "reasoning",
    "alignment", "data_systems", "theory", "neuro_ai",
]

# venue: kind, deadline months (mod 12; None = rolling), decision delay, accept bar,
# visibility, publication lag after decision
VENUES = {
    "NAIC":   dict(kind="conf",     deadlines=[3, 9],  delay=3, theta=6.3, vis=3.0, pub_lag=2),
    "CLAR":   dict(kind="conf",     deadlines=[0, 6],  delay=3, theta=4.6, vis=1.2, pub_lag=2),
    "W-SHOP": dict(kind="workshop", deadlines=None,    delay=1, theta=2.6, vis=0.4, pub_lag=0),
    "JMR":    dict(kind="journal",  deadlines=None,    delay=7, theta=5.6, vis=2.0, pub_lag=0),
}

# agency: schedule (explicit months or "rolling"), award $, duration months, accept bar,
# decision delay months
AGENCIES = {
    "BSF": dict(schedule=list(range(2, 61, 6)), award=360_000, duration=36, theta=1.15, delay=5, max_concurrent=2),
    "AMP": dict(schedule=[5, 14, 26, 38, 50],   award=850_000, duration=24, theta=1.45, delay=6, max_concurrent=1),
    "TIF": dict(schedule="rolling",             award=90_000,  duration=12, theta=0.92, delay=2, max_concurrent=2),
    "FEL": dict(schedule=[9, 21, 33],           award=150_000, duration=24, theta=1.35, delay=4, max_concurrent=1, once=True),
}

# applicant pools: mean/sd of ability, transcript noise, letter bias, letter noise,
# base accept prob, rep sensitivity of accept prob, mean season volume
POOLS = {
    "elite":          dict(mu=0.68, sd=0.10, t_noise=0.05, l_bias=0.02,  l_noise=0.08, acc=0.35, acc_rep=0.05, vol=2.0),
    "international":  dict(mu=0.62, sd=0.14, t_noise=0.10, l_bias=0.12,  l_noise=0.15, acc=0.60, acc_rep=0.03, vol=3.5),
    "nontraditional": dict(mu=0.55, sd=0.20, t_noise=0.18, l_bias=-0.05, l_noise=0.12, acc=0.75, acc_rep=0.02, vol=2.5),
    "local":          dict(mu=0.50, sd=0.10, t_noise=0.06, l_bias=0.00,  l_noise=0.06, acc=0.85, acc_rep=0.01, vol=2.0),
}


@dataclass
class WorldConfig:
    months: int = 60
    start_budget: float = 600_000.0

    # money
    phd_stipend: float = 3_200.0
    postdoc_salary: float = 6_500.0
    grant_overhead_monthly: float = 600.0
    proposal_admin_cost: float = 500.0
    travel_cost_talk: float = 1_500.0
    conference_attend_cost: float = 2_500.0
    compute_unit_cost: float = 1.0        # $ per unit of monthly project compute

    # attention
    attention_budget: float = 100.0
    service_tax_hours: float = 12.0       # months t % 12 == 7
    # management overhead: every researcher costs the PI unavoidable oversight hours
    # off the top, so attention binds for EVERY viable lab size (not just overreach).
    # A lab manager buys this back (money -> attention). This is the distinctive
    # dual-resource lever PIBench adds over single-currency simulators.
    oversight_per_researcher: float = 4.0
    oversight_per_ra: float = 1.5
    oversight_min_per_researcher: float = 1.0
    manager_oversight_relief: float = 2.0   # per manager, subtracted from per-researcher
    attention_floor: float = 30.0           # pool never drops below this
    interview_hours: float = 3.0
    review_hours: float = 6.0
    talk_hours: float = 8.0
    crisis_hours: float = 10.0
    conference_hours: float = 15.0
    collab_hours_monthly: float = 6.0

    # field dynamics
    hot_init: dict = field(default_factory=lambda: dict(
        sparse_models=1.6, ai4science=1.2, embodied=0.8, reasoning=2.2,
        alignment=1.0, data_systems=0.7, theory=0.5, neuro_ai=0.9))
    hot_ou_theta: float = 0.06            # mean reversion in log space
    hot_ou_sigma: float = 0.10
    hot_clip: tuple = (0.25, 6.0)
    p_boom: float = 0.02
    p_bust: float = 0.015
    crowd_eta: float = 0.12
    news_rate_per_hot: float = 1.2
    preprint_rate_per_crowd: float = 6.0

    # students
    phd_arrival_traits: dict = field(default_factory=dict)  # unused placeholder
    skill_init_base: float = 0.35
    skill_init_ability: float = 0.30
    skill_growth: float = 0.012
    skill_cap: float = 1.2
    morale_lambda: float = 0.75
    quit_scale: float = 0.5
    quit_mid: float = 0.35
    quit_temp: float = 0.07
    quit_cap: float = 0.25
    grad_min_months: int = 48
    grad_min_papers: int = 2
    postdoc_ability_shift: float = 0.12
    postdoc_contract_months: int = 24
    alumni_cite_spillover: float = 0.005      # per alum, added to citation rate
    alumni_quality_lift: float = 0.012        # per alum, applicant ability mean shift
    alumni_quality_lift_cap: float = 0.06
    # staff roles (liquid labor)
    ra_salary: float = 1_800.0
    ra_skill: float = 0.5                     # fixed; RAs do not grow
    manager_salary: float = 4_500.0
    max_managers: int = 2

    # projects
    tier_work: dict = field(default_factory=lambda: {1: 6.0, 2: 14.0, 3: 28.0})
    tier_infeasible: dict = field(default_factory=lambda: {1: 0.03, 2: 0.10, 3: 0.28})
    tier_q0: dict = field(default_factory=lambda: {1: 1.2, 2: 2.6, 3: 3.6})
    progress_coef: float = 0.9
    progress_noise: float = 0.22
    compute_c0: float = 800.0
    compute_coef: float = 0.30
    deadend_reveal_frac: float = 0.6
    salvage_prob: float = 0.5
    scoop_base: float = 0.010
    scoop_novelty_mult: float = 0.45
    novelty_crowd_penalty: float = 0.06
    novelty_bleed: float = 0.015
    breakthrough_prob: float = 0.18
    breakthrough_gain: float = 1.5
    quality_skill_coef: float = 1.8
    quality_novelty_coef: float = 0.9
    quality_compute_coef: float = 0.35
    quality_polish_coef: float = 0.5
    quality_noise: float = 0.45

    # review & citations
    review_hot_coef: float = 0.35
    review_rep_coef: float = 0.15
    review_noise: float = 0.5
    revise_gain: float = 0.35
    revise_decay: float = 0.8
    cite_g_coef: float = 0.42
    cite_ramp_months: int = 6
    cite_halflife: float = 30.0
    cite_halflife_journal: float = 40.0
    cite_rep_coef: float = 0.08
    collab_credit: float = 0.5

    # grants
    prop_hours_coef: float = 0.42
    prop_hours_norm: float = 25.0
    prop_hours_pow: float = 0.7
    prop_prelim_coef: float = 0.55
    prop_prelim_norm: float = 6.0
    prop_rep_coef: float = 0.06
    prop_rep_cap: float = 0.35
    prop_overcommit_penalty: float = 0.10
    prop_climate_coef: float = 0.25
    prop_noise: float = 0.28
    tif_hot_coef: float = 0.20
    amp_tier3_bonus: float = 0.15
    agency_pref_range: float = 0.6
    amp_pref_lead: int = 6
    climate_cycle: float = 30.0
    climate_amp: float = 0.18
    climate_sigma: float = 0.05
    climate_clip: tuple = (0.6, 1.4)
    tif_cooldown: int = 3
    max_active_tif: int = 2

    # reputation
    rep_init: float = 2.0
    rep_decay: float = 0.01
    rep_pub: dict = field(default_factory=lambda: dict(NAIC=0.5, JMR=0.35, CLAR=0.15, **{"W-SHOP": 0.03}))
    rep_grant: dict = field(default_factory=lambda: dict(BSF=0.25, AMP=0.4, FEL=0.5, TIF=0.05))
    rep_talk: float = 0.12
    rep_review: float = 0.02
    rep_review_decline: float = -0.03
    rep_grad: float = 0.25

    # events
    talk_rate_per_rep: float = 0.08       # monthly Poisson rate = this * max(R - 2, 0)
    review_req_rate: float = 0.6
    crisis_rate: float = 0.02             # per student per month
    collab_rate_per_rep: float = 0.05
    collab_months: int = 3
    collab_min_students: int = 1          # need a group to take on a collaboration
    event_expiry: int = 2                 # months before auto-decline
    conf_attend_cooldown: int = 5         # months between conference trips
    conf_rep_gain: float = 0.06

    # score
    projection_months: int = 36

    # misc
    max_students: int = 12
    max_active_projects: int = 10
