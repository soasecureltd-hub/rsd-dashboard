import React, { useMemo, useRef, useState } from 'react';
import RiskForm from './RiskForm';
import { riskAPI, errorMessage } from '../api/apiClient';
import '../styles/WhatIfSimulator.css';

const THREATS = [
  { key: 'unauthorized_access', label: 'Unauthorized access' },
  { key: 'insider_threat', label: 'Insider threat' },
  { key: 'emergency_failure', label: 'Emergency failure' },
  { key: 'perimeter_breach', label: 'Perimeter breach' },
];

const SECTIONS = {
  physical_security: 'Physical Security',
  access_control: 'Access Control',
  personnel: 'Personnel',
  incident_history: 'Incident History',
  emergency_preparedness: 'Emergency Preparedness',
};

const humanize = (field) => field.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

/** Which answers differ between the saved assessment and the scenario. */
function changedAnswers(original, scenario) {
  const changes = [];
  Object.entries(SECTIONS).forEach(([section, sectionLabel]) => {
    const before = original?.[section] || {};
    const after = scenario?.[section] || {};
    Object.keys(after).forEach((field) => {
      if (String(before[field]) !== String(after[field])) {
        changes.push({ section: sectionLabel, field: humanize(field), from: before[field], to: after[field] });
      }
    });
  });
  return changes;
}

/** Higher = riskier everywhere, so a negative change is an improvement. */
function Change({ delta, unit }) {
  if (Math.abs(delta) < 0.05) return <span className="whatif-delta">No change</span>;
  const better = delta < 0;
  return (
    <span className={`whatif-delta ${better ? 'whatif-delta--better' : 'whatif-delta--worse'}`}>
      {better ? '▼' : '▲'} {Math.abs(delta).toFixed(1)}{unit} {better ? 'lower risk' : 'higher risk'}
    </span>
  );
}

export default function WhatIfSimulator({ assessment }) {
  const original = assessment?.input_data;
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(null);       // last submitted scenario inputs
  const [formKey, setFormKey] = useState(0);      // bump to reset the form
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const resultRef = useRef(null);

  const changes = useMemo(() => (draft ? changedAnswers(original, draft) : []), [original, draft]);

  if (!original) {
    return (
      <div className="what-if-section">
        <h3>What-If Scenario</h3>
        <p>The original answers for this assessment aren't available, so scenarios can't be run.</p>
      </div>
    );
  }

  const runScenario = async (formData) => {
    setDraft(formData);
    setLoading(true);
    setError(null);
    try {
      const res = await riskAPI.simulate(assessment.id, formData);
      setResult(res.data);
      requestAnimationFrame(() => resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    } catch (err) {
      setError(errorMessage(err, 'Could not run the scenario'));
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setDraft(null);
    setResult(null);
    setError(null);
    setFormKey((k) => k + 1);
  };

  return (
    <div className="what-if-section">
      <h3>What-If Scenario</h3>
      <p>
        Change any answer and run the scenario. The overall score and threat estimates are
        recalculated with the same scoring rules and model as the assessment.{' '}
        <strong>Nothing is saved.</strong>
      </p>

      {!open ? (
        <button className="btn-secondary" onClick={() => setOpen(true)}>Try a scenario</button>
      ) : (
        <>
          {error && <div className="error-message">{error}</div>}

          {result && (
            <div className="whatif-result" ref={resultRef} aria-live="polite">
              <h4>Scenario result</h4>
              <table className="whatif-table">
                <thead>
                  <tr>
                    <th scope="col">Measure</th>
                    <th scope="col" className="num">Current</th>
                    <th scope="col" className="num">Scenario</th>
                    <th scope="col">Change</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className="whatif-row--overall">
                    <th scope="row">Overall risk score</th>
                    <td className="num" data-label="Current">{result.baseline.overall_score.toFixed(1)} <span className="whatif-level">{result.baseline.risk_level}</span></td>
                    <td className="num" data-label="Scenario">{result.scenario.overall_score.toFixed(1)} <span className="whatif-level">{result.scenario.risk_level}</span></td>
                    <td data-label="Change"><Change delta={result.scenario.overall_score - result.baseline.overall_score} unit=" pts" /></td>
                  </tr>
                  {THREATS.map(({ key, label }) => {
                    const before = result.baseline.threats[key] * 100;
                    const after = result.scenario.threats[key] * 100;
                    return (
                      <tr key={key}>
                        <th scope="row">{label}</th>
                        <td className="num" data-label="Current">{before.toFixed(1)}%</td>
                        <td className="num" data-label="Scenario">{after.toFixed(1)}%</td>
                        <td data-label="Change"><Change delta={after - before} unit=" pts" /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              <div className="whatif-changes">
                <h5>What you changed</h5>
                {changes.length === 0 ? (
                  <p>Nothing yet — this scenario uses the assessment's current answers.</p>
                ) : (
                  <ul>
                    {changes.map((c) => (
                      <li key={`${c.section}-${c.field}`}>
                        <span className="whatif-change-where">{c.section} · {c.field}:</span>{' '}
                        {String(c.from)} → <strong>{String(c.to)}</strong>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <p className="whatif-note">
                Threat figures are estimates from a model trained on synthetic, rule-labelled data.
                The current values are recalculated now, so they can differ slightly from a
                prediction saved earlier.
              </p>
            </div>
          )}

          <div className="whatif-form">
            <div className="whatif-form-actions">
              <button className="btn-link" onClick={reset} disabled={loading}>Reset to current answers</button>
              <button className="btn-link" onClick={() => setOpen(false)} disabled={loading}>Close</button>
            </div>
            <RiskForm
              key={formKey}
              initialData={draft || original}
              onSubmit={runScenario}
              loading={loading}
              submitLabel="Run scenario"
              loadingLabel="Calculating…"
              hideFacility
            />
          </div>
        </>
      )}
    </div>
  );
}
