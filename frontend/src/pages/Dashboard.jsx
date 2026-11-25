import React from 'react';
import RiskForm from '../components/RiskForm';
import RiskResults from '../components/RiskResults';
import KeyFindings from '../components/KeyFindings';
import AIPredictions from '../components/AIPredictions';
import { useAssessment } from '../context/AssessmentContext';
import { riskAPI, errorMessage } from '../api/apiClient';
import '../styles/Dashboard.css';

export default function Dashboard() {
  const { state, dispatch } = useAssessment();
  const { assessment, findings, predictions, loading, error, activeTab } = state;

  const handleAssessmentSubmit = async (formData) => {
    dispatch({ type: 'SET_LOADING', payload: true });
    dispatch({ type: 'SET_ERROR', payload: null });
    try {
      const response = await riskAPI.createAssessment(formData);
      const newAssessment = response.data;
      dispatch({ type: 'SET_ASSESSMENT', payload: newAssessment });

      // Fetch key findings and threat estimates in parallel
      const [findingsRes, predRes] = await Promise.allSettled([
        riskAPI.getFindings(newAssessment.id),
        riskAPI.predict(newAssessment.id),
      ]);

      if (findingsRes.status === 'fulfilled') {
        dispatch({ type: 'SET_FINDINGS', payload: findingsRes.value.data });
      }
      if (predRes.status === 'fulfilled') {
        dispatch({ type: 'SET_PREDICTIONS', payload: predRes.value.data });
      }
    } catch (err) {
      dispatch({ type: 'SET_ERROR', payload: errorMessage(err, 'Error creating assessment') });
    } finally {
      dispatch({ type: 'SET_LOADING', payload: false });
    }
  };

  return (
    <div className="dashboard">
      <div className="tabs">
        <button
          className={`tab ${activeTab === 'input' ? 'active' : ''}`}
          onClick={() => dispatch({ type: 'SET_TAB', payload: 'input' })}
        >
          Risk Assessment
        </button>
        {assessment && (
          <>
            <button
              className={`tab ${activeTab === 'results' ? 'active' : ''}`}
              onClick={() => dispatch({ type: 'SET_TAB', payload: 'results' })}
            >
              Results
            </button>
            <button
              className={`tab ${activeTab === 'predictions' ? 'active' : ''}`}
              onClick={() => dispatch({ type: 'SET_TAB', payload: 'predictions' })}
            >
              AI Predictions
            </button>
            <button
              className={`tab ${activeTab === 'findings' ? 'active' : ''}`}
              onClick={() => dispatch({ type: 'SET_TAB', payload: 'findings' })}
            >
              Key findings
              {findings?.concerns?.length > 0 && (
                <span
                  className="tab-badge tab-badge--danger"
                  aria-label={`${findings.concerns.length} areas need attention`}
                >
                  {findings.concerns.length}
                </span>
              )}
            </button>
          </>
        )}
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="tab-content">
        {activeTab === 'input' && (
          <RiskForm onSubmit={handleAssessmentSubmit} loading={loading} />
        )}
        {activeTab === 'results' && assessment && (
          <RiskResults
            assessment={assessment}
            findings={findings}
            predictions={predictions}
          />
        )}
        {activeTab === 'predictions' && assessment && (
          <AIPredictions assessmentId={assessment.id} />
        )}
        {activeTab === 'findings' && (
          <KeyFindings findings={findings} facility={assessment?.facility_name} />
        )}
      </div>
    </div>
  );
}
