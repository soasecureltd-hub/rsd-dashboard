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

// ── Answer bands ─────────────────────────────────────────────────────────────
// Mirror backend/app/services/findings_service.py (URGENT_AT = 80,
// ATTENTION_AT = 60, STRENGTH_AT = 15) and risk_service.map_score, so the hint
// under each input matches what Key findings will say about it.
export const URGENT_AT = 80;
export const ATTENTION_AT = 60;
export const STRENGTH_AT = 15;

export const QUALITY_RISK = { Poor: 90, Fair: 60, Good: 30, Excellent: 10 };

const clamp = (v) => Math.min(Math.max(v, 0), 100);

/**
 * Risk (0-100, higher = riskier) of one answer.
 * kind: 'quality' (Poor..Excellent), 'better' (higher number = better,
 * e.g. CCTV coverage) or 'worse' (higher number = worse, e.g. incident severity).
 */
export function answerRisk(kind, value) {
  if (kind === 'quality') return QUALITY_RISK[value] ?? 50;
  if (value === '' || value == null || Number.isNaN(Number(value))) return null;
  return kind === 'better' ? 100 - clamp(Number(value)) : clamp(Number(value));
}

/** 'urgent' | 'attention' | 'ok' | 'strength' (same rules as Key findings). */
export function answerLevel(risk) {
  if (risk == null) return null;
  if (risk >= URGENT_AT) return 'urgent';
  if (risk >= ATTENTION_AT) return 'attention';
  if (risk <= STRENGTH_AT) return 'strength';
  return 'ok';
}

/** Ranges shown under numeric inputs, lowest number first. */
export const NUMBER_BANDS = {
  better: [
    { range: '0–20', label: 'Poor', level: 'urgent' },
    { range: '21–40', label: 'Fair', level: 'attention' },
    { range: '41–84', label: 'Good', level: 'ok' },
    { range: '85–100', label: 'Excellent', level: 'strength' },
  ],
  worse: [
    { range: '0–15', label: 'Very low', level: 'strength' },
    { range: '16–59', label: 'Moderate', level: 'ok' },
    { range: '60–79', label: 'High', level: 'attention' },
    { range: '80–100', label: 'Critical', level: 'urgent' },
  ],
};

/** The band a numeric answer falls in (null while the box is empty). */
export function numberBand(kind, value) {
  const level = answerLevel(answerRisk(kind, value));
  return level ? NUMBER_BANDS[kind].find((b) => b.level === level) : null;
}
