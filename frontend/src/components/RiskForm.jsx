import React, { useId, useRef, useState } from 'react';
import { answerLevel, answerRisk, NUMBER_BANDS, numberBand } from '../utils/risk';
import '../styles/RiskForm.css';

const QUALITY_OPTIONS = ['Poor', 'Fair', 'Good', 'Excellent'];

/**
 * The questionnaire. kind: 'quality' (Poor..Excellent select),
 * 'better' (number, higher = better) or 'worse' (number, higher = worse).
 */
const SECTIONS = [
  {
    key: 'physical_security',
    title: 'Physical Security',
    fields: [
      { key: 'perimeter_condition', label: 'Perimeter condition', kind: 'quality' },
      { key: 'cctv_coverage', label: 'CCTV coverage', kind: 'better', unit: '%',
        help: 'Share of the site covered by cameras.' },
      { key: 'cctv_functionality', label: 'CCTV functionality', kind: 'better', unit: '%',
        help: 'Share of cameras that are currently working.' },
      { key: 'lighting_quality', label: 'Lighting quality', kind: 'quality' },
      { key: 'entry_exit_control', label: 'Entry and exit control', kind: 'quality' },
    ],
  },
  {
    key: 'access_control',
    title: 'Access Control',
    fields: [
      { key: 'visitor_management', label: 'Visitor management', kind: 'quality' },
      { key: 'id_verification', label: 'ID verification', kind: 'quality' },
      { key: 'restricted_area_protection', label: 'Restricted area protection', kind: 'quality' },
      { key: 'after_hours_security', label: 'After-hours security', kind: 'quality' },
    ],
  },
  {
    key: 'personnel',
    title: 'Security Personnel',
    fields: [
      { key: 'guard_count_ratio', label: 'Guard adequacy', kind: 'better', unit: '/ 100',
        help: "How well guard numbers match the site's needs." },
      { key: 'training_frequency', label: 'Training frequency', kind: 'quality' },
      { key: 'background_checks', label: 'Background checks', kind: 'quality' },
      { key: 'shift_coverage', label: 'Shift coverage', kind: 'quality' },
    ],
  },
  {
    key: 'incident_history',
    title: 'Incident History',
    fields: [
      { key: 'incident_severity_score', label: 'Incident severity', kind: 'worse', unit: '/ 100',
        help: 'How serious recent incidents have been (higher = more serious).' },
      { key: 'incident_type_score', label: 'Incident type severity', kind: 'worse', unit: '/ 100',
        help: 'How dangerous the kinds of incidents recorded are (higher = more dangerous).' },
      { key: 'response_time_score', label: 'Response time quality', kind: 'better', unit: '/ 100',
        help: 'How quickly incidents are responded to (higher = faster).' },
      { key: 'documentation_quality', label: 'Documentation quality', kind: 'quality' },
    ],
  },
  {
    key: 'emergency_preparedness',
    title: 'Emergency Preparedness',
    fields: [
      { key: 'emergency_plan', label: 'Emergency plan', kind: 'quality' },
      { key: 'drill_frequency', label: 'Drill frequency', kind: 'quality' },
      { key: 'communication_system', label: 'Communication system', kind: 'quality' },
      { key: 'staff_readiness', label: 'Staff readiness', kind: 'quality' },
    ],
  },
];

const DEFAULT_FORM = {
  facility_name: '',
  physical_security: {
    perimeter_condition: 'Good',
    cctv_coverage: 75,
    cctv_functionality: 85,
    lighting_quality: 'Good',
    entry_exit_control: 'Good',
  },
  access_control: {
    visitor_management: 'Good',
    id_verification: 'Good',
    restricted_area_protection: 'Good',
    after_hours_security: 'Good',
  },
  personnel: {
    guard_count_ratio: 70,
    training_frequency: 'Good',
    background_checks: 'Good',
    shift_coverage: 'Good',
  },
  incident_history: {
    incident_severity_score: 40,
    incident_type_score: 35,
    response_time_score: 60,
    documentation_quality: 'Good',
  },
  emergency_preparedness: {
    emergency_plan: 'Good',
    drill_frequency: 'Good',
    communication_system: 'Good',
    staff_readiness: 'Good',
  },
};

/** Defaults overlaid with any provided answers (section by section). */
function buildInitial(initialData) {
  if (!initialData) return DEFAULT_FORM;
  const merged = { ...DEFAULT_FORM, facility_name: initialData.facility_name || '' };
  Object.keys(DEFAULT_FORM).forEach((key) => {
    if (key !== 'facility_name') merged[key] = { ...DEFAULT_FORM[key], ...(initialData[key] || {}) };
  });
  return merged;
}

/** "2 urgent · 1 needs attention" for a section (same rules as Key findings). */
function sectionSummary(section, values) {
  let urgent = 0;
  let attention = 0;
  section.fields.forEach((f) => {
    const level = answerLevel(answerRisk(f.kind, values[f.key]));
    if (level === 'urgent') urgent += 1;
    if (level === 'attention') attention += 1;
  });
  if (!urgent && !attention) return { text: 'No issues', tone: 'ok' };
  const parts = [];
  if (urgent) parts.push(`${urgent} urgent`);
  if (attention) parts.push(`${attention} need${attention === 1 ? 's' : ''} attention`);
  return { text: parts.join(' · '), tone: urgent ? 'urgent' : 'attention' };
}

function NumberHint({ id, field, value }) {
  const current = numberBand(field.kind, value);
  return (
    <div id={id} className="field-hint">
      {field.help && <span className="field-help">{field.help} </span>}
      <span className="field-scale">
        {NUMBER_BANDS[field.kind].map((b, i) => (
          <span key={b.range} className={current === b ? 'scale-step scale-step--current' : 'scale-step'}>
            {i > 0 && <span aria-hidden="true"> · </span>}
            {b.range} {b.label}
          </span>
        ))}
      </span>
      {current && (
        <span className={`field-now field-now--${current.level}`}>
          Currently: <strong>{current.label}</strong>
        </span>
      )}
    </div>
  );
}

export default function RiskForm({
  onSubmit,
  loading = false,
  initialData = null,       // pre-fill (e.g. What-If simulator)
  submitLabel = 'Analyze Risk',
  loadingLabel = 'Analyzing...',
  hideFacility = false,
  requireReview = false,    // warn before submitting with sections never opened
}) {
  const uid = useId();
  const formRef = useRef(null);
  const [formData, setFormData] = useState(() => buildInitial(initialData));
  const [open, setOpen] = useState(() => new Set([SECTIONS[0].key]));
  const [reviewed, setReviewed] = useState(() => new Set([SECTIONS[0].key]));
  const [unreviewedPrompt, setUnreviewedPrompt] = useState(null);

  const handleInputChange = (section, field, value) => {
    setFormData((prev) => ({ ...prev, [section]: { ...prev[section], [field]: value } }));
  };

  const toggle = (key) => {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
    setReviewed((prev) => new Set(prev).add(key));
    setUnreviewedPrompt(null);
  };

  const allOpen = open.size === SECTIONS.length;
  const toggleAll = () => {
    if (allOpen) {
      setOpen(new Set());
    } else {
      const keys = SECTIONS.map((s) => s.key);
      setOpen(new Set(keys));
      setReviewed(new Set(keys));
      setUnreviewedPrompt(null);
    }
  };

  const openSections = (keys) => {
    setOpen((prev) => new Set([...prev, ...keys]));
    setReviewed((prev) => new Set([...prev, ...keys]));
  };

  // Validation is done here (form has noValidate): the browser can't show an
  // error on a field inside a collapsed section, so open that section first.
  const firstInvalid = () =>
    Array.from(formRef.current.elements).find((el) => el.willValidate && !el.checkValidity());

  const handleSubmit = (e, { skipReviewCheck = false } = {}) => {
    e?.preventDefault();
    const invalid = firstInvalid();
    if (invalid) {
      const section = invalid.dataset.section;
      if (section) openSections([section]);
      requestAnimationFrame(() => invalid.reportValidity());
      return;
    }
    if (requireReview && !skipReviewCheck) {
      const missing = SECTIONS.filter((s) => !reviewed.has(s.key));
      if (missing.length) {
        setUnreviewedPrompt(missing);
        return;
      }
    }
    setUnreviewedPrompt(null);
    onSubmit(formData);
  };

  return (
    <form className="risk-form" onSubmit={handleSubmit} noValidate ref={formRef}>
      {!hideFacility && (
        <div className="form-group facility-group">
          <label htmlFor={`${uid}-facility`}>Facility name (optional)</label>
          <input
            id={`${uid}-facility`}
            type="text"
            maxLength={200}
            value={formData.facility_name}
            onChange={(e) => setFormData({ ...formData, facility_name: e.target.value })}
            placeholder="e.g., Corporate Headquarters"
          />
        </div>
      )}

      <div className="sections-toolbar">
        <span className="sections-hint">Open each section to check its answers.</span>
        <button type="button" className="btn-link" onClick={toggleAll}>
          {allOpen ? 'Collapse all' : 'Expand all'}
        </button>
      </div>

      {SECTIONS.map((section) => {
        const isOpen = open.has(section.key);
        const values = formData[section.key];
        const summary = sectionSummary(section, values);
        const panelId = `${uid}-${section.key}`;
        return (
          <section key={section.key} className={`form-section ${isOpen ? 'form-section--open' : ''}`}>
            <h3 className="section-heading">
              <button
                type="button"
                className="section-toggle"
                aria-expanded={isOpen}
                aria-controls={panelId}
                onClick={() => toggle(section.key)}
              >
                <span className="section-chevron" aria-hidden="true">{isOpen ? '▾' : '▸'}</span>
                <span className="section-title">{section.title}</span>
                <span className={`section-summary section-summary--${summary.tone}`}>{summary.text}</span>
                {requireReview && (
                  <span className={`section-reviewed ${reviewed.has(section.key) ? 'is-done' : ''}`}>
                    {reviewed.has(section.key) ? '✓ Opened' : 'Not opened yet'}
                  </span>
                )}
              </button>
            </h3>

            <div id={panelId} className="section-body" hidden={!isOpen}>
              {section.fields.map((field) => {
                const inputId = `${uid}-${section.key}-${field.key}`;
                const hintId = `${inputId}-hint`;
                const value = values[field.key];
                return (
                  <div key={field.key} className="form-group">
                    <label htmlFor={inputId}>
                      {field.label}
                      {field.unit && <span className="field-unit"> ({field.unit === '%' ? '0–100 %' : '0–100'})</span>}
                    </label>
                    {field.kind === 'quality' ? (
                      <select
                        id={inputId}
                        data-section={section.key}
                        value={value}
                        onChange={(e) => handleInputChange(section.key, field.key, e.target.value)}
                      >
                        {QUALITY_OPTIONS.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                      </select>
                    ) : (
                      <>
                        <input
                          id={inputId}
                          data-section={section.key}
                          type="number"
                          inputMode="decimal"
                          required
                          min="0"
                          max="100"
                          step="any"
                          aria-describedby={hintId}
                          value={value}
                          onChange={(e) => handleInputChange(
                            section.key, field.key, e.target.value === '' ? '' : Number(e.target.value),
                          )}
                        />
                        <NumberHint id={hintId} field={field} value={value} />
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}

      {unreviewedPrompt && (
        <div className="review-prompt" role="alert">
          <p>
            You haven't opened{' '}
            <strong>{unreviewedPrompt.map((s) => s.title).join(', ')}</strong>.
            Their pre-filled answers will be used as they are.
          </p>
          <div className="review-prompt-actions">
            <button type="button" className="btn-secondary" onClick={() => {
              openSections(unreviewedPrompt.map((s) => s.key));
              setUnreviewedPrompt(null);
            }}>
              Review them
            </button>
            <button type="button" className="btn-link" onClick={() => handleSubmit(null, { skipReviewCheck: true })}>
              Submit anyway
            </button>
          </div>
        </div>
      )}

      <button type="submit" disabled={loading} className="submit-btn">
        {loading ? loadingLabel : submitLabel}
      </button>
    </form>
  );
}
