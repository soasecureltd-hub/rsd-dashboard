"""
Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints
from typing import Annotated, Dict, List, Literal, Optional
from datetime import datetime


# ============ Risk Assessment Schemas ============

# Qualitative rating; must match QUAL_MAPPING in services/risk_service.py.
# Anything else is rejected (previously a typo silently scored as 50).
Quality = Literal["Poor", "Fair", "Good", "Excellent"]

# Numeric inputs are 0-100 scores/percentages.
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]


class PhysicalSecurityInput(BaseModel):
    perimeter_condition: Quality
    cctv_coverage: Percent
    cctv_functionality: Percent
    lighting_quality: Quality
    entry_exit_control: Quality


class AccessControlInput(BaseModel):
    visitor_management: Quality
    id_verification: Quality
    restricted_area_protection: Quality
    after_hours_security: Quality


class PersonnelInput(BaseModel):
    guard_count_ratio: Percent
    training_frequency: Quality
    background_checks: Quality
    shift_coverage: Quality


class IncidentHistoryInput(BaseModel):
    incident_severity_score: Percent
    incident_type_score: Percent
    response_time_score: Percent
    documentation_quality: Quality


class EmergencyPreparednessInput(BaseModel):
    emergency_plan: Quality
    drill_frequency: Quality
    communication_system: Quality
    staff_readiness: Quality


class RiskAssessmentInput(BaseModel):
    facility_name: Optional[
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
    ] = None
    physical_security: PhysicalSecurityInput
    access_control: AccessControlInput
    personnel: PersonnelInput
    incident_history: IncidentHistoryInput
    emergency_preparedness: EmergencyPreparednessInput


class RiskAssessmentResponse(BaseModel):
    id: int
    facility_name: Optional[str]
    created_at: datetime
    category_scores: Dict[str, float]
    contributions: Dict[str, float]
    overall_score: float
    risk_level: str
    # The answers the assessment was scored from (lets the UI pre-fill the
    # What-If simulator). Same shape as RiskAssessmentInput.
    input_data: Optional[Dict] = None

    model_config = ConfigDict(from_attributes=True)


# ============ Auth Schemas ============

class UserCreate(BaseModel):
    email: EmailStr
    # max_length guards against DoS from hashing very large inputs.
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: Optional[str] = None


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============ AI Prediction Schemas ============

class AIPredictionResponse(BaseModel):
    """Estimated threat likelihoods in [0, 1].

    These come from a model trained on synthetic, rule-labelled data (see
    services/ml_service.py) - relative indicators, not measured probabilities.
    """
    unauthorized_access: float
    insider_threat: float
    emergency_failure: float
    perimeter_breach: float
    risk_labels: List[str] = Field(default=[
        "Unauthorized Access",
        "Insider Threat",
        "Emergency Failure",
        "Perimeter Breach"
    ])


# ============ Anomaly Detection Schemas ============

class AnomalyAlert(BaseModel):
    feature: str
    severity: str  # HIGH, MEDIUM
    z_score: float
    value: float
    message: str
    direction: Optional[str] = None           # "above" or "below" baseline
    baseline_mean: Optional[float] = None
    percent_deviation: Optional[float] = None


class AnomalyDetectionResponse(BaseModel):
    total_anomalies: int
    anomalies: List[AnomalyAlert]
    status: str
    multivariate_anomaly: bool = False        # IsolationForest global flag
    anomaly_score: float = 0.0               # 0–1, higher = more anomalous
    risk_velocity: Optional[Dict] = None     # rate of change vs previous assessment



# ============ What-If Simulation Schemas ============

class ScenarioOutcome(BaseModel):
    """Scores and estimated threats for one set of inputs (nothing is saved)."""
    overall_score: float
    risk_level: str
    category_scores: Dict[str, float]
    threats: AIPredictionResponse


class SimulationResponse(BaseModel):
    """The assessment as saved vs. an edited scenario, scored the same way."""
    baseline: ScenarioOutcome
    scenario: ScenarioOutcome
