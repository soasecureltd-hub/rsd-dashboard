import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { riskAPI } from '../api/apiClient';
import { riskColor, riskLabel } from '../utils/risk';
import '../styles/RiskResults.css';

const TOKEN_KEY = 'rsd_token';

const RISK_COLOR = riskColor;
const RISK_LABEL = riskLabel;

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

export default function RiskResults({ assessment, findings, predictions }) {
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(null);

  if (!assessment) return null;

  const token = localStorage.getItem(TOKEN_KEY);

  const THREAT_LABELS = {
    unauthorized_access: 'Unauthorized access',
    insider_threat: 'Insider threat',
    emergency_failure: 'Emergency failure',
    perimeter_breach: 'Perimeter breach',
  };
  const topThreat = predictions
    ? Object.entries(THREAT_LABELS)
      .map(([key, label]) => ({ label, value: Number(predictions[key]) || 0 }))
      .sort((a, b) => b.value - a.value)[0]
    : null;

  const urgentCount = findings ? findings.concerns.filter((c) => c.severity === 'urgent').length : 0;

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

      {/* Summary strip: top threat estimate, findings, change since last time */}
      {(predictions || findings) && (
        <div className="insight-strip">
          {predictions && (
            <div className="insight-item">
              <span className="insight-label">Highest Estimated Threat</span>
              <span className="insight-value">
                {topThreat.label} · {Math.round(topThreat.value * 100)}%
              </span>
            </div>
          )}
          {findings && (
            <div className={`insight-item ${urgentCount ? 'insight-item--alert' : ''}`}>
              <span className="insight-label">Needs Attention</span>
              <span className="insight-value">
                {findings.concerns.length === 0
                  ? 'Nothing'
                  : `${findings.concerns.length} area${findings.concerns.length === 1 ? '' : 's'}${urgentCount ? ` · ${urgentCount} urgent` : ''}`}
              </span>
            </div>
          )}
          {findings?.risk_velocity && (
            <div className={`insight-item ${findings.risk_velocity.overall_delta > 0.5 ? 'insight-item--alert' : findings.risk_velocity.overall_delta < -0.5 ? 'insight-item--good' : ''}`}>
              <span className="insight-label">Since Last Assessment</span>
              <span className="insight-value">
                {Math.abs(findings.risk_velocity.overall_delta) < 0.5
                  ? 'About the same'
                  : `${findings.risk_velocity.overall_delta > 0 ? '▲' : '▼'} ${Math.abs(findings.risk_velocity.overall_delta).toFixed(1)} pts ${findings.risk_velocity.overall_delta > 0 ? 'worse' : 'better'}`}
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
