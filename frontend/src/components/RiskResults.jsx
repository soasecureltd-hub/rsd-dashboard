import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { riskAPI } from '../api/apiClient';
import '../styles/RiskResults.css';

const TOKEN_KEY = 'rsd_token';

const RISK_COLOR = (score) => {
  if (score <= 40) return '#28a745';
  if (score <= 60) return '#ffc107';
  if (score <= 80) return '#fd7e14';
  return '#dc3545';
};

const RISK_LABEL = (score) => {
  if (score <= 40) return 'LOW RISK';
  if (score <= 60) return 'MODERATE RISK';
  if (score <= 80) return 'HIGH RISK';
  return 'CRITICAL RISK';
};

const RECOMMENDATIONS = {
  'Physical Security':      'Improve perimeter integrity, upgrade lighting, and increase CCTV coverage.',
  'Access Control':         'Strengthen identity verification and restrict unauthorised area access.',
  'Personnel':              'Increase guard training frequency and ensure complete shift coverage.',
  'Incident History':       'Reduce incident frequency, improve response time, and maintain documentation.',
  'Emergency Preparedness': 'Conduct regular drills and upgrade communication and evacuation systems.',
};

function MiniGauge({ score }) {
  const color = RISK_COLOR(score);
  return (
    <div className="mini-gauge">
      <div className="mini-gauge-track">
        <div className="mini-gauge-fill" style={{ width: `${score}%`, background: color }} />
      </div>
      <span className="mini-gauge-label" style={{ color }}>{score.toFixed(1)}</span>
    </div>
  );
}

function filenameFromHeader(disposition, fallback) {
  const match = /filename="?([^";]+)"?/i.exec(disposition || '');
  return match ? match[1] : fallback;
}

export default function RiskResults({ assessment, anomalyResult, predictions }) {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(null);

  if (!assessment) return null;

  const token = localStorage.getItem(TOKEN_KEY);

  const chartData = Object.entries(assessment.category_scores || {}).map(([name, value]) => ({
    name: name.replace(' ', '\n'),
    score: value,
    fill: RISK_COLOR(value),
  }));

  // Highest score = highest risk = biggest weakness (fix: sort descending)
  const sortedWeaknesses = Object.entries(assessment.category_scores || {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 3);

  const handleDownloadReport = async () => {
    if (!token || downloading) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const res = await riskAPI.downloadReport(assessment.id);
      const filename = filenameFromHeader(
        res.headers['content-disposition'],
        `RSD_Report_${assessment.id}.pdf`,
      );
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      setDownloadError('Could not download the report. Please try again.');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="results-container">

      {/* Overall score */}
      <div className="overall-score" style={{ borderColor: RISK_COLOR(assessment.overall_score) }}>
        <div className="score-display">
          <h1 style={{ color: RISK_COLOR(assessment.overall_score) }}>
            {assessment.overall_score}/100
          </h1>
          <p className="risk-level" style={{ color: RISK_COLOR(assessment.overall_score) }}>
            {RISK_LABEL(assessment.overall_score)}
          </p>
          {assessment.facility_name && (
            <p className="facility-name">{assessment.facility_name}</p>
          )}
        </div>
      </div>

      {/* Inline AI + anomaly summary strip */}
      {(predictions || anomalyResult) && (
        <div className="insight-strip">
          {predictions && (
            <div className="insight-item">
              <span className="insight-label">Model Confidence</span>
              <span className="insight-value" style={{ color: RISK_COLOR(100 - predictions.confidence * 100) }}>
                {Math.round((predictions.confidence || 0) * 100)}%
              </span>
            </div>
          )}
          {anomalyResult && (
            <div className="insight-item">
              <span className="insight-label">Anomalies Found</span>
              <span className="insight-value" style={{ color: anomalyResult.total_anomalies > 0 ? '#ef4444' : '#10b981' }}>
                {anomalyResult.total_anomalies}
              </span>
            </div>
          )}
          {anomalyResult && (
            <div className="insight-item">
              <span className="insight-label">Anomaly Score</span>
              <span className="insight-value" style={{ color: RISK_COLOR(anomalyResult.anomaly_score * 100) }}>
                {(anomalyResult.anomaly_score * 100).toFixed(0)}/100
              </span>
            </div>
          )}
          {anomalyResult?.multivariate_anomaly && (
            <div className="insight-item insight-item--alert">
              <span className="insight-label">Global Pattern</span>
              <span className="insight-value">Anomalous</span>
            </div>
          )}
          {anomalyResult?.risk_velocity?.significant && (
            <div className={`insight-item ${anomalyResult.risk_velocity.direction === 'worsening' ? 'insight-item--alert' : 'insight-item--good'}`}>
              <span className="insight-label">Trend vs Last</span>
              <span className="insight-value">
                {anomalyResult.risk_velocity.direction === 'worsening' ? '▲' : '▼'}{' '}
                {Math.abs(anomalyResult.risk_velocity.overall_delta).toFixed(1)} pts
              </span>
            </div>
          )}
        </div>
      )}

      <div className="results-grid">
        <div className="chart-container">
          <h3>Category Scores</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={chartData} margin={{ bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" angle={-35} textAnchor="end" interval={0} tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 100]} />
              <Tooltip formatter={(v) => [`${v}`, 'Score']} />
              <Bar dataKey="score" fill="#3b82f6" radius={[4, 4, 0, 0]}
                label={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="weaknesses-container">
          <h3>Top Risk Areas</h3>
          <div className="weakness-list">
            {sortedWeaknesses.map(([area, score], idx) => (
              <div key={area} className="weakness-item" style={{ borderLeftColor: RISK_COLOR(score) }}>
                <span className="weakness-rank" style={{ color: RISK_COLOR(score) }}>#{idx + 1}</span>
                <div className="weakness-info">
                  <p className="weakness-area">{area}</p>
                  <MiniGauge score={score} />
                  <p className="weakness-level" style={{ color: RISK_COLOR(score) }}>
                    {RISK_LABEL(score)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="recommendations-section">
        <h3>Priority Recommendations</h3>
        <div className="recommendations-list">
          {sortedWeaknesses.map(([area, score]) => (
            <div key={area} className="recommendation-item" style={{ borderLeftColor: RISK_COLOR(score) }}>
              <h4>{area}</h4>
              <p>{RECOMMENDATIONS[area]}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="action-buttons">
        <button onClick={handleDownloadReport} className="btn-primary" disabled={!token || downloading}>
          {downloading ? 'Preparing PDF…' : 'Download PDF Report'}
        </button>
        {downloadError && <p className="error-message">{downloadError}</p>}
      </div>
    </div>
  );
}
