import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useAssessment } from '../context/AssessmentContext';
import { riskAPI, errorMessage } from '../api/apiClient';
import WhatIfSimulator from './WhatIfSimulator';
import '../styles/AIPredictions.css';

const THREATS = [
  { key: 'unauthorized_access', label: 'Unauthorized Access' },
  { key: 'insider_threat', label: 'Insider Threat' },
  { key: 'emergency_failure', label: 'Emergency Failure' },
  { key: 'perimeter_breach', label: 'Perimeter Breach' },
];

export default function AIPredictions({ assessmentId }) {
  const { state, dispatch } = useAssessment();
  const { predictions, assessment } = state;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleRunPredictions = async () => {
    if (!assessmentId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await riskAPI.predict(assessmentId);
      dispatch({ type: 'SET_PREDICTIONS', payload: response.data });
    } catch (err) {
      setError(errorMessage(err, 'Error running predictions'));
    } finally {
      setLoading(false);
    }
  };

  if (!assessmentId) {
    return (
      <div className="ai-predictions">
        <p style={{ textAlign: 'center', color: '#999' }}>👈 Please complete a risk assessment first</p>
      </div>
    );
  }

  const chartData = predictions
    ? THREATS.map(({ key, label }) => ({ name: label, prediction: (predictions[key] * 100).toFixed(1) }))
    : [];

  return (
    <div className="ai-predictions">
      <div className="predictions-title-row">
        <h2>Estimated Threat Likelihood</h2>
        <span className="confidence-badge">Estimate</span>
      </div>
      <p className="subtitle">
        From a model trained on synthetic facilities labelled with expert rules, not on real
        incident records. Use these to compare threats and track change, not as measured
        probabilities.
      </p>

      {error && <div className="error-message">{error}</div>}

      {!predictions ? (
        <div className="predictions-cta">
          <button onClick={handleRunPredictions} disabled={loading} className="btn-primary">
            {loading ? 'Analyzing...' : '🚀 Run AI Predictions'}
          </button>
        </div>
      ) : (
        <>
          <div className="predictions-cards">
            {THREATS.map(({ key, label }) => (
              <div key={key} className="prediction-card">
                <h4>{label}</h4>
                <div className="risk-bar">
                  <div className="risk-fill" style={{ width: `${predictions[key] * 100}%` }} />
                </div>
                <p className="percentage">{(predictions[key] * 100).toFixed(1)}%</p>
              </div>
            ))}
          </div>

          <div className="chart-section">
            <h3>Prediction Overview</h3>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" angle={-45} textAnchor="end" height={100} />
                <YAxis domain={[0, 100]} label={{ value: 'Risk %', angle: -90, position: 'insideLeft' }} />
                <Tooltip formatter={(value) => `${value}%`} />
                <Bar dataKey="prediction" fill="#ef4444" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <WhatIfSimulator assessment={assessment} />

          <div className="action-buttons">
            <button onClick={handleRunPredictions} disabled={loading} className="btn-primary">
              🔄 Refresh Predictions
            </button>
          </div>
        </>
      )}
    </div>
  );
}
