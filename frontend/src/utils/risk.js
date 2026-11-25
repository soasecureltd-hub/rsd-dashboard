// Risk thresholds — keep in sync with risk_level() in backend/app/services/risk_service.py.
// Higher score = higher risk.

export const RISK_THRESHOLDS = [
  { max: 40, name: 'Low', color: '#28a745' },
  { max: 60, name: 'Moderate', color: '#ffc107' },
  { max: 80, name: 'High', color: '#fd7e14' },
  { max: Infinity, name: 'Critical', color: '#dc3545' },
];

const bandFor = (score) => RISK_THRESHOLDS.find((t) => score <= t.max);

export const riskColor = (score) => bandFor(score).color;
export const riskName = (score) => bandFor(score).name;
export const riskLabel = (score) => `${riskName(score).toUpperCase()} RISK`;
