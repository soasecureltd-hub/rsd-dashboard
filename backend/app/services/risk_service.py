"""
Risk assessment and scoring business logic.
"""
from typing import Dict, Optional, Tuple


QUAL_MAPPING = {
    "Poor": 90,
    "Fair": 60,
    "Good": 30,
    "Excellent": 10,
}

_CATEGORY_KEYS = [
    "Physical Security",
    "Access Control",
    "Personnel",
    "Incident History",
    "Emergency Preparedness",
]

# ── Scoring ───────────────────────────────────────────────────────────────────

# Numeric inputs where a HIGHER value means BETTER security (e.g. 90% CCTV
# coverage). Every score in this system is risk-oriented (higher = worse), so
# these are inverted (100 - value) before averaging.
POSITIVE_NUMERIC_FIELDS = {
    "cctv_coverage",
    "cctv_functionality",
    "guard_count_ratio",
    "response_time_score",  # "Response Time Quality": 100 = fastest response
}


def map_score(value, field: Optional[str] = None) -> float:
    """Convert an input value to a 0–100 risk score (higher = riskier)."""
    if isinstance(value, str):
        return float(QUAL_MAPPING.get(value, 50))
    score = float(value)
    if field in POSITIVE_NUMERIC_FIELDS:
        return 100.0 - min(max(score, 0.0), 100.0)
    return score


def compute_scores(data: Dict) -> Tuple[Dict, Dict, float]:
    weights = {
        "Physical Security":      0.25,
        "Access Control":         0.30,
        "Personnel":              0.15,
        "Incident History":       0.20,
        "Emergency Preparedness": 0.10,
    }
    assert abs(sum(weights.values()) - 1.0) < 1e-9

    category_scores: Dict[str, float] = {}
    contributions:   Dict[str, float] = {}

    for cat, items in data.items():
        item_scores = [map_score(v, k) for k, v in items.items()] if isinstance(items, dict) else [map_score(items)]
        avg = sum(item_scores) / len(item_scores) if item_scores else 0
        category_scores[cat] = round(avg, 2)
        contributions[cat]   = round(avg * weights.get(cat, 0), 2)

    overall_score = round(sum(contributions.values()), 2)
    return category_scores, contributions, overall_score


def risk_level(score: float) -> Tuple[str, str, str]:
    if score <= 40:
        return ("🟢 LOW RISK",      "Low",      "#28a745")
    elif score <= 60:
        return ("🟡 MODERATE RISK", "Moderate", "#ffc107")
    elif score <= 80:
        return ("🟠 HIGH RISK",     "High",     "#fd7e14")
    else:
        return ("🔴 CRITICAL RISK", "Critical", "#dc3545")


# ── Risk velocity ─────────────────────────────────────────────────────────────

def compute_risk_velocity(
    current_scores:  Dict,
    current_overall: float,
    previous_scores: Dict,
    previous_overall: float,
) -> Dict:
    """
    Compute rate of change between two consecutive assessments.
    Flags categories that shifted ≥10 points and overall movement direction.
    """
    category_changes: Dict = {}
    for cat in _CATEGORY_KEYS:
        curr = current_scores.get(cat)
        prev = previous_scores.get(cat)
        if curr is None or prev is None:
            continue
        delta = curr - prev
        if abs(delta) >= 10:
            category_changes[cat] = {
                "delta":     round(delta, 1),
                "direction": "worsened" if delta > 0 else "improved",
                "previous":  round(prev, 1),
                "current":   round(curr, 1),
            }

    overall_delta = current_overall - previous_overall
    return {
        "overall_delta":     round(overall_delta, 2),
        "direction":         "worsening" if overall_delta > 0 else "improving",
        "category_changes":  category_changes,
        "significant":       abs(overall_delta) >= 10 or bool(category_changes),
    }
