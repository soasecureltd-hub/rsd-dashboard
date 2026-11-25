"""Risk assessment routes"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app import schemas, crud
from app.db import get_db
from app.dependencies import get_current_user
from app.services.risk_service import compute_scores, risk_level, compute_risk_velocity
from app.services.findings_service import build_findings, unusual_combination
from app.services.ml_service import predict as ml_predict
from app.services.report_service import generate_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/risk", tags=["risk"])

# Scoring category -> key of that section in RiskAssessmentInput / input_data.
CATEGORY_SECTIONS = {
    "Physical Security": "physical_security",
    "Access Control": "access_control",
    "Personnel": "personnel",
    "Incident History": "incident_history",
    "Emergency Preparedness": "emergency_preparedness",
}


def _category_data(sections: dict) -> dict:
    """RiskAssessmentInput-shaped dict -> {category: answers} for compute_scores."""
    return {cat: sections.get(key) or {} for cat, key in CATEGORY_SECTIONS.items()}


def _to_response(a) -> schemas.RiskAssessmentResponse:
    return schemas.RiskAssessmentResponse(
        id=a.id,
        facility_name=a.facility_name,
        created_at=a.created_at,
        category_scores=a.category_scores or {},
        contributions=a.contributions or {},
        overall_score=a.overall_score or 0,
        risk_level=a.risk_level or "Unknown",
        input_data=a.input_data,
    )


def _score_scenario(sections: dict) -> schemas.ScenarioOutcome:
    """Score a set of answers and estimate threats, without saving anything."""
    category_scores, _, overall = compute_scores(_category_data(sections))
    _, level, _ = risk_level(overall)
    threats = ml_predict({"overall_score": overall, "category_scores": category_scores})
    return schemas.ScenarioOutcome(
        overall_score=overall,
        risk_level=level,
        category_scores=category_scores,
        threats=schemas.AIPredictionResponse(**threats),
    )


@router.post("/assess", response_model=schemas.RiskAssessmentResponse)
def create_assessment(
    assessment: schemas.RiskAssessmentInput,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        category_scores, contributions, overall_score = compute_scores(
            _category_data(assessment.model_dump())
        )
        badge, risk_level_name, color = risk_level(overall_score)
        db_assessment = crud.create_assessment(db, assessment, user_id=current_user.id)
        db_assessment = crud.update_assessment_results(
            db, db_assessment.id, category_scores, contributions, overall_score, risk_level_name
        )
        return _to_response(db_assessment)
    except Exception:
        logger.exception("Failed to create risk assessment")
        raise HTTPException(status_code=400, detail="Could not process assessment")


@router.get("/assess/{assessment_id}", response_model=schemas.RiskAssessmentResponse)
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    db_assessment = crud.get_assessment(db, assessment_id, user_id=current_user.id)
    if not db_assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    return _to_response(db_assessment)


@router.get("/assessments", response_model=list[schemas.RiskAssessmentResponse])
def list_assessments(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    assessments = crud.get_all_assessments(db, user_id=current_user.id, skip=skip, limit=limit)
    return [_to_response(a) for a in assessments]


@router.post("/assess/{assessment_id}/simulate", response_model=schemas.SimulationResponse)
def simulate_scenario(
    assessment_id: int,
    scenario: schemas.RiskAssessmentInput,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """What-If: score an edited copy of this assessment's answers.

    Both the saved answers (baseline) and the scenario are scored right now with
    the same scoring rules and model, so the difference reflects only the edits.
    Nothing is saved.
    """
    db_assessment = crud.get_assessment(db, assessment_id, user_id=current_user.id)
    if not db_assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    try:
        return schemas.SimulationResponse(
            baseline=_score_scenario(db_assessment.input_data or {}),
            scenario=_score_scenario(scenario.model_dump()),
        )
    except Exception:
        logger.exception("Simulation failed for assessment %s", assessment_id)
        raise HTTPException(status_code=500, detail="Could not run the scenario")


@router.get("/assess/{assessment_id}/findings", response_model=schemas.FindingsResponse)
def get_findings(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Key findings: answers that need attention, strengths, change since the
    previous assessment of the same facility, and an unusual-combination check."""
    db_assessment = crud.get_assessment(db, assessment_id, user_id=current_user.id)
    if not db_assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    try:
        # Earlier assessments of the SAME facility only, made before this one,
        # so reopening an old assessment gives the answer it had at the time.
        earlier = [
            a for a in crud.get_assessments_before(
                db, user_id=current_user.id, before_id=assessment_id, limit=50,
                facility_name=db_assessment.facility_name,
            )
            if a.category_scores
        ]

        velocity = None
        if earlier and db_assessment.category_scores:
            prior = earlier[0]
            velocity = compute_risk_velocity(
                current_scores=db_assessment.category_scores,
                current_overall=db_assessment.overall_score or 0.0,
                previous_scores=prior.category_scores,
                previous_overall=prior.overall_score or 0.0,
            )
            velocity["previous_assessment_id"] = prior.id
            velocity["previous_created_at"] = prior.created_at.isoformat() if prior.created_at else None

        findings = build_findings(db_assessment.input_data or {})
        combination = unusual_combination(
            db_assessment.category_scores or {}, [a.category_scores for a in earlier]
        )
        return schemas.FindingsResponse(
            concerns=findings["concerns"],
            strengths=findings["strengths"],
            risk_velocity=velocity,
            unusual_combination=combination,
        )
    except Exception:
        logger.exception("Findings failed for assessment %s", assessment_id)
        raise HTTPException(status_code=500, detail="Could not build the findings")


@router.get("/assess/{assessment_id}/report")
def download_report(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Download a PDF report for a completed assessment.

    Auth via the standard Authorization: Bearer header. The token is
    deliberately NOT accepted as a query param: URLs end up in browser
    history and server/proxy logs.
    """
    db_assessment = crud.get_assessment(db, assessment_id, user_id=current_user.id)
    if not db_assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if not db_assessment.category_scores:
        raise HTTPException(status_code=400, detail="Assessment has no computed scores yet")

    ai_pred = crud.get_ai_prediction(db, assessment_id)

    try:
        pdf_bytes = generate_pdf(db_assessment, ai_pred)
    except Exception:
        logger.exception("PDF generation failed for assessment %s", assessment_id)
        raise HTTPException(status_code=500, detail="Could not generate report")

    safe_name = (db_assessment.facility_name or "Assessment").replace(" ", "_")
    filename = f"RSD_Report_{safe_name}_{assessment_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/predict/{assessment_id}", response_model=schemas.AIPredictionResponse)
def get_latest_prediction(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return the most recent stored prediction without running the model.

    Lets the history view reopen an assessment without creating a new
    prediction row on every visit. 404 when none has been run yet.
    """
    if not crud.get_assessment(db, assessment_id, user_id=current_user.id):
        raise HTTPException(status_code=404, detail="Assessment not found")
    pred = crud.get_ai_prediction(db, assessment_id)
    if not pred:
        raise HTTPException(status_code=404, detail="No prediction for this assessment yet")
    return schemas.AIPredictionResponse(
        unauthorized_access=pred.unauthorized_access_prob or 0.0,
        insider_threat=pred.insider_threat_prob or 0.0,
        emergency_failure=pred.emergency_failure_prob or 0.0,
        perimeter_breach=pred.perimeter_breach_prob or 0.0,
    )


@router.post("/predict/{assessment_id}", response_model=schemas.AIPredictionResponse)
def predict_risk(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Estimate threat likelihoods for a completed assessment (stores the result)."""
    db_assessment = crud.get_assessment(db, assessment_id, user_id=current_user.id)
    if not db_assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    if not db_assessment.category_scores:
        raise HTTPException(status_code=400, detail="Assessment has no computed scores")

    try:
        assessment_data = {
            "overall_score": db_assessment.overall_score or 0.0,
            "category_scores": db_assessment.category_scores,
        }
        predictions = ml_predict(assessment_data)

        # Persist prediction
        crud.create_ai_prediction(
            db,
            assessment_id=assessment_id,
            input_features=assessment_data,
            predictions=predictions,
        )

        return schemas.AIPredictionResponse(
            unauthorized_access=predictions["unauthorized_access"],
            insider_threat=predictions["insider_threat"],
            emergency_failure=predictions["emergency_failure"],
            perimeter_breach=predictions["perimeter_breach"],
        )
    except Exception:
        logger.exception("ML prediction failed for assessment %s", assessment_id)
        raise HTTPException(status_code=500, detail="Prediction failed")
