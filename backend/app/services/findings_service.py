"""
Key findings: which answers in an assessment need attention, in plain language.

Every answer is put on the same 0-100 risk scale the scoring uses
(risk_service.map_score: higher = riskier; coverage-style percentages are
inverted). Then:

    risk >= 80  (Poor, or a number in the Critical band)  -> "urgent"
    risk >= 60  (Fair, or a number in the High band)      -> "attention"
    risk <= 15  (Excellent, or a very strong number)      -> strength

Only risk-raising answers are ever reported as problems; unusually good
answers are strengths, never alarms. Every finding carries a plain headline,
why it matters and what to do, written here once so the API, UI and any
future report say the same thing.
"""
from typing import Dict, List, Optional

import numpy as np

from app.services.risk_service import POSITIVE_NUMERIC_FIELDS, map_score

URGENT_AT = 80.0
ATTENTION_AT = 60.0
STRENGTH_AT = 15.0

# Section key in the input -> category name used everywhere else.
SECTIONS = {
    "physical_security": "Physical Security",
    "access_control": "Access Control",
    "personnel": "Personnel",
    "incident_history": "Incident History",
    "emergency_preparedness": "Emergency Preparedness",
}

# Category weights from compute_scores: used to order findings of equal urgency.
_CATEGORY_WEIGHT = {
    "Access Control": 0.30, "Physical Security": 0.25, "Incident History": 0.20,
    "Personnel": 0.15, "Emergency Preparedness": 0.10,
}

# field -> (label, why it matters, what to do)
FIELD_COPY = {
    # Physical security
    "perimeter_condition": (
        "Perimeter condition",
        "Fences, walls and gates are the first barrier; gaps let intruders in unseen.",
        "Repair damaged sections and inspect the perimeter on a fixed schedule.",
    ),
    "cctv_coverage": (
        "CCTV coverage",
        "Areas without cameras can't be watched live or investigated afterwards.",
        "Add cameras over entrances, car parks and known blind spots.",
    ),
    "cctv_functionality": (
        "Working cameras",
        "Cameras that are offline or degraded give a false sense of coverage.",
        "Repair or replace faulty cameras and check them every week.",
    ),
    "lighting_quality": (
        "Lighting",
        "Poor lighting helps intruders avoid notice and weakens CCTV footage.",
        "Improve lighting at entrances, walkways and parking areas.",
    ),
    "entry_exit_control": (
        "Entry and exit control",
        "Uncontrolled doors let people in without being checked.",
        "Reduce the number of entry points and keep each one secured or staffed.",
    ),
    # Access control
    "visitor_management": (
        "Visitor management",
        "Visitors who aren't recorded can't be traced if something goes wrong.",
        "Sign every visitor in and out, issue visible badges and escort them.",
    ),
    "id_verification": (
        "ID verification",
        "Weak ID checks let impostors pass as staff or contractors.",
        "Check photo ID at entry and use badges that can be verified.",
    ),
    "restricted_area_protection": (
        "Restricted area protection",
        "Sensitive rooms and stores are the most valuable targets on site.",
        "Lock restricted areas and limit access to named people only.",
    ),
    "after_hours_security": (
        "After-hours security",
        "Many incidents happen outside staffed hours, when fewer people would notice.",
        "Review night patrols, alarm coverage and lock-up procedures.",
    ),
    # Personnel
    "guard_count_ratio": (
        "Guard adequacy",
        "Too few guards leaves areas and shifts without cover.",
        "Review guard numbers against the size of the site and the shift pattern.",
    ),
    "training_frequency": (
        "Guard training",
        "Staff without regular training miss warning signs and respond poorly to incidents.",
        "Run regular refresher training, including incident drills.",
    ),
    "background_checks": (
        "Background checks",
        "Staff who haven't been vetted are a route for insider threats.",
        "Screen all staff and contractors before they start, and re-check periodically.",
    ),
    "shift_coverage": (
        "Shift coverage",
        "Gaps between shifts leave the site unguarded.",
        "Make sure every hour is covered and that handovers overlap.",
    ),
    # Incident history (numbers are risk scores: higher = worse)
    "incident_severity_score": (
        "Incident severity",
        "Serious past incidents point to weaknesses that may be exploited again.",
        "Review recent serious incidents and confirm their causes were fixed.",
    ),
    "incident_type_score": (
        "Incident type severity",
        "The kinds of incidents recorded show which threats are most active here.",
        "Focus controls on the incident types that occur most often.",
    ),
    "response_time_score": (
        "Response time quality",
        "Slow responses let incidents escalate before help arrives.",
        "Review alerting, staffing and escalation so responders arrive faster.",
    ),
    "documentation_quality": (
        "Incident records",
        "Without good records, patterns and repeat problems go unnoticed.",
        "Log every incident with its cause and the follow-up taken.",
    ),
    # Emergency preparedness
    "emergency_plan": (
        "Emergency plan",
        "Without a clear plan, people lose time deciding what to do in an emergency.",
        "Write or update the emergency plan and share it with all staff.",
    ),
    "drill_frequency": (
        "Emergency drills",
        "Plans that aren't practised often fail when they're needed.",
        "Run drills regularly and fix the problems they reveal.",
    ),
    "communication_system": (
        "Emergency communication",
        "If alerts can't reach everyone quickly, people act too late.",
        "Test alarms and communication channels on a regular schedule.",
    ),
    "staff_readiness": (
        "Staff readiness",
        "Staff who don't know their role slow the whole response down.",
        "Brief staff on their emergency roles and refresh it regularly.",
    ),
}


def _answer_text(field: str, value) -> str:
    if isinstance(value, str):
        return value
    if field in POSITIVE_NUMERIC_FIELDS:
        return f"{value:g}%" if field.startswith("cctv") else f"{value:g} / 100"
    return f"{value:g} / 100"


def _headline(field: str, label: str, value, risk: float) -> str:
    if isinstance(value, str):
        return f"{label} is rated {value}"
    answer = _answer_text(field, value)
    if field in POSITIVE_NUMERIC_FIELDS:
        return f"{label} is only {answer}" if risk >= ATTENTION_AT else f"{label} is {answer}"
    return f"{label} is high ({answer})" if risk >= ATTENTION_AT else f"{label} is low ({answer})"


def build_findings(input_data: Dict) -> Dict[str, List[Dict]]:
    """Concerns (most urgent first) and strengths for one assessment's answers."""
    concerns, strengths = [], []
    for section_key, category in SECTIONS.items():
        for field, value in (input_data.get(section_key) or {}).items():
            if field not in FIELD_COPY or value is None or value == "":
                continue
            label, why, action = FIELD_COPY[field]
            risk = map_score(value, field)
            base = {
                "category": category,
                "field": field,
                "label": label,
                "answer": _answer_text(field, value),
                "risk": round(risk, 1),
            }
            if risk >= ATTENTION_AT:
                concerns.append({
                    **base,
                    "severity": "urgent" if risk >= URGENT_AT else "attention",
                    "headline": _headline(field, label, value, risk),
                    "why": why,
                    "action": action,
                })
            elif risk <= STRENGTH_AT:
                strengths.append(base)

    concerns.sort(key=lambda c: (-c["risk"], -_CATEGORY_WEIGHT.get(c["category"], 0)))
    strengths.sort(key=lambda s: (s["risk"], -_CATEGORY_WEIGHT.get(s["category"], 0)))
    return {"concerns": concerns, "strengths": strengths}


# ── Unusual combination (statistical, shown as a detail only) ─────────────────

_CATEGORY_ORDER = list(SECTIONS.values())
_synthetic_profiles: Optional[np.ndarray] = None


def _vector(category_scores: Dict) -> np.ndarray:
    return np.array([category_scores.get(k, 50.0) for k in _CATEGORY_ORDER], dtype=np.float32)


def _typical_profiles(n: int = 300) -> np.ndarray:
    """Synthetic facility profiles used when there isn't enough real history."""
    global _synthetic_profiles
    if _synthetic_profiles is None:
        rng = np.random.default_rng(42)
        means = [(20, 15, 25, 20, 15), (45, 50, 40, 45, 40), (65, 70, 55, 60, 55), (80, 80, 75, 80, 80)]
        per = n // len(means)
        _synthetic_profiles = np.vstack([
            np.column_stack([rng.normal(m, max(m * 0.2, 5), per).clip(10, 90) for m in row])
            for row in means
        ]).astype(np.float32)
    return _synthetic_profiles


def unusual_combination(category_scores: Dict, history: List[Dict]) -> Dict:
    """Is this mix of category scores unusual? Compared with the facility's own
    earlier assessments when there are at least 5, otherwise with synthetic
    typical profiles. Returns {unusual, score (0-1), compared_with}."""
    from sklearn.ensemble import IsolationForest

    own = len(history) >= 5
    reference = np.array([_vector(s) for s in history]) if own else _typical_profiles()
    iso = IsolationForest(contamination=0.1, random_state=42, n_estimators=100).fit(reference)
    current = _vector(category_scores).reshape(1, -1)
    raw = float(-iso.score_samples(current)[0])  # typical range ~0.3-0.7
    return {
        "unusual": bool(iso.predict(current)[0] == -1),
        "score": round(min(max((raw - 0.3) / 0.4, 0.0), 1.0), 3),
        "compared_with": "own_history" if own else "typical_profiles",
    }
