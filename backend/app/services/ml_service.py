"""
Threat likelihood estimates (scikit-learn RandomForest).

IMPORTANT — what this model is and is not
-----------------------------------------
There is no real incident data yet. The model is trained on synthetic
facilities whose labels come from expert-written rules (THREAT_DRIVERS below):
each threat has a risk index over the category scores, and a logistic curve
turns that index into a probability. Training labels are *sampled* from that
probability, so the model learns graded likelihoods rather than a yes/no
cliff.

The outputs are therefore a smoothed encoding of those rules — useful as
relative indicators ("this facility's insider-threat exposure is higher than
its perimeter exposure"), not as measured real-world probabilities. The API
and UI present them as estimates for that reason.
"""
import logging
from pathlib import Path
from typing import Dict

import joblib
import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

# Bump whenever the training data, labels or model change, so a cached model
# file from an older version is retrained instead of silently reused.
MODEL_VERSION = 2

FEATURE_NAMES = [
    "overall_score",
    "physical_security_score",
    "access_control_score",
    "personnel_score",
    "incident_history_score",
    "emergency_preparedness_score",
    "access_x_incident",       # interaction: poor access control + high incidents
    "physical_x_personnel",    # interaction: poor physical security + understaffing
]

TARGET_NAMES = [
    "unauthorized_access",
    "insider_threat",
    "emergency_failure",
    "perimeter_breach",
]

# Column positions in the raw (n, 6) score array.
_COL = {"overall": 0, "physical": 1, "access": 2, "personnel": 3, "incident": 4, "emergency": 5}

# Expert rules: which category scores drive each threat, and how much.
# Weights per threat sum to 1, so each index is on the same 0-100 risk scale.
THREAT_DRIVERS = {
    "unauthorized_access": {"access": 0.6, "incident": 0.4},
    "insider_threat":      {"personnel": 0.6, "access": 0.4},
    "emergency_failure":   {"emergency": 0.7, "overall": 0.3},
    "perimeter_breach":    {"physical": 0.6, "incident": 0.4},
}

# Logistic curve from risk index to probability:
#   index 30 (well secured) ≈ 4%,  45 ≈ 22%,  55 = 50%,  65 ≈ 78%,  80 ≈ 96%
RISK_MIDPOINT = 55.0
RISK_SPREAD = 8.0

_model = None


def threat_probabilities(raw: np.ndarray) -> np.ndarray:
    """The rule-based target probabilities for a (n, 6) raw score array → (n, 4)."""
    columns = []
    for target in TARGET_NAMES:
        index = sum(w * raw[:, _COL[name]] for name, w in THREAT_DRIVERS[target].items())
        columns.append(1.0 / (1.0 + np.exp(-(index - RISK_MIDPOINT) / RISK_SPREAD)))
    return np.column_stack(columns)


def _engineer_features(raw: np.ndarray) -> np.ndarray:
    """
    Add pairwise interaction features to a (n, 6) input array.

    Columns: overall, physical, access, personnel, incident, emergency
    """
    physical  = raw[:, 1]
    access    = raw[:, 2]
    personnel = raw[:, 3]
    incident  = raw[:, 4]

    # Normalise to [0,1] then scale back so magnitudes stay comparable
    access_x_incident    = (access / 90.0) * (incident / 90.0) * 90.0
    physical_x_personnel = (physical / 90.0) * (personnel / 90.0) * 90.0

    return np.column_stack([raw, access_x_incident, physical_x_personnel])


def _sample_raw_scores(rng: np.random.Generator, n: int) -> np.ndarray:
    """Synthetic facilities as (n, 6) raw scores: overall + five categories.

    Half come from realistic archetypes (categories move together), half are
    uniform over the whole 10-90 range so every combination is covered.
    """
    archetypes = [
        (20, 15, 25, 20, 15),  # well secured
        (40, 50, 35, 45, 40),  # moderate
        (65, 70, 55, 60, 55),  # high risk, ageing infrastructure
        (25, 75, 65, 70, 30),  # access / incident failure
        (72, 38, 72, 48, 78),  # personnel + emergency weak
        (80, 82, 78, 80, 82),  # critical
    ]
    n_arch = n // 2
    per = n_arch // len(archetypes)
    segments = [
        np.column_stack([rng.normal(m, max(m * 0.2, 5), per) for m in means])
        for means in archetypes
    ]
    segments.append(rng.uniform(10, 90, (n - per * len(archetypes), 5)))
    categories = np.vstack(segments).clip(10, 90)

    # Weighted average mirrors compute_scores weights
    weights = np.array([0.25, 0.30, 0.15, 0.20, 0.10])
    overall = (categories * weights).sum(axis=1, keepdims=True)
    return np.hstack([overall, categories]).astype(np.float32)


def _generate_training_data(n: int = 6000, seed: int = 42):
    """Synthetic features and labels; labels are Bernoulli draws from
    threat_probabilities(), so the classifier learns graded likelihoods."""
    rng = np.random.default_rng(seed)
    raw = _sample_raw_scores(rng, n)
    y = (rng.random((n, len(TARGET_NAMES))) < threat_probabilities(raw)).astype(int)
    return _engineer_features(raw).astype(np.float32), y


def _train_and_save() -> object:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.multioutput import MultiOutputClassifier

    X, y = _generate_training_data()
    # No class_weight="balanced": reweighting classes distorts predicted
    # probabilities, and probabilities are the whole output here.
    # Large leaves average many sampled labels → smooth probability estimates.
    model = MultiOutputClassifier(
        RandomForestClassifier(
            n_estimators=200,
            min_samples_leaf=30,
            random_state=42,
            n_jobs=-1,
        )
    )
    model.fit(X, y)

    joblib.dump({"version": MODEL_VERSION, "model": model}, Path(settings.MODEL_PATH))
    logger.info("[ml_service] model v%s trained and saved → %s", MODEL_VERSION, settings.MODEL_PATH)
    return model


def _get_model():
    global _model
    if _model is not None:
        return _model
    model_path = Path(settings.MODEL_PATH)
    if model_path.exists():
        try:
            bundle = joblib.load(model_path)
            if not isinstance(bundle, dict) or bundle.get("version") != MODEL_VERSION:
                raise ValueError("outdated model version")
            bundle["model"].predict(np.zeros((1, len(FEATURE_NAMES)), dtype=np.float32))
            _model = bundle["model"]
            logger.info("[ml_service] model v%s loaded from %s", MODEL_VERSION, model_path)
        except Exception as exc:
            logger.warning("[ml_service] cached model unusable (%s), retraining…", exc)
            _model = _train_and_save()
    else:
        _model = _train_and_save()
    return _model


def predict(assessment_data: Dict) -> Dict:
    """
    Estimate threat likelihoods from assessment scores.

    Args:
        assessment_data:
            overall_score (float) and category_scores (dict of category → float)

    Returns:
        Dict with keys unauthorized_access, insider_threat, emergency_failure,
        perimeter_breach — each an estimated likelihood in [0, 1].
    """
    model = _get_model()
    cat = assessment_data.get("category_scores", {})

    raw = np.array([[
        assessment_data.get("overall_score", 50.0),
        cat.get("Physical Security", 50.0),
        cat.get("Access Control", 50.0),
        cat.get("Personnel", 50.0),
        cat.get("Incident History", 50.0),
        cat.get("Emergency Preparedness", 50.0),
    ]], dtype=np.float32)

    # MultiOutputClassifier.predict_proba returns list of (n_samples, n_classes) arrays
    probas = model.predict_proba(_engineer_features(raw))
    return {
        TARGET_NAMES[i]: round(float(probas[i][0][1]), 3)
        for i in range(len(TARGET_NAMES))
    }
