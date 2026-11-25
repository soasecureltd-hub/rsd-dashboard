import React, { useState } from 'react';
import '../styles/KeyFindings.css';

const SEVERITY = {
  urgent: { label: 'Urgent', icon: '!' },
  attention: { label: 'Needs attention', icon: '•' },
};
const COLLAPSED_COUNT = 5;

const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : null;

/** One plain sentence summarising the page. */
function summaryText(concerns) {
  const urgent = concerns.filter((c) => c.severity === 'urgent').length;
  if (concerns.length === 0) return 'Nothing needs attention right now.';
  const areas = `${concerns.length} area${concerns.length === 1 ? '' : 's'} need${concerns.length === 1 ? 's' : ''} attention`;
  return urgent ? `${areas}, ${urgent} of them urgent.` : `${areas}.`;
}

function ChangeSinceLast({ velocity, facility }) {
  if (!velocity) {
    return (
      <p className="kf-change kf-change--none">
        This is the first assessment{facility ? ` of ${facility}` : ''}, so there's nothing to compare with yet.
      </p>
    );
  }
  const delta = velocity.overall_delta;
  const when = fmtDate(velocity.previous_created_at);
  const changes = Object.entries(velocity.category_changes || {});
  const steady = Math.abs(delta) < 0.5 && changes.length === 0;
  return (
    <div className="kf-change">
      <p>
        {steady ? (
          <>Overall risk is <strong>about the same</strong> as</>
        ) : (
          <>
            Overall risk is <strong>{delta > 0 ? 'up' : 'down'} {Math.abs(delta).toFixed(1)} points</strong>{' '}
            ({delta > 0 ? 'worse' : 'better'}) since
          </>
        )}{' '}
        the previous assessment{facility ? ` of ${facility}` : ''}{when ? ` on ${when}` : ''}.
      </p>
      {changes.length > 0 && (
        <ul>
          {changes.map(([category, c]) => (
            <li key={category}>
              <strong>{category}</strong> {c.direction === 'worsened' ? 'got worse' : 'improved'}:{' '}
              {c.previous} → {c.current}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Concern({ finding }) {
  const sev = SEVERITY[finding.severity];
  return (
    <li className={`kf-concern kf-concern--${finding.severity}`}>
      <div className="kf-concern-head">
        <span className={`kf-badge kf-badge--${finding.severity}`}>
          <span aria-hidden="true">{sev.icon}</span> {sev.label}
        </span>
        <span className="kf-category">{finding.category}</span>
      </div>
      <h4>{finding.headline}</h4>
      <p><span className="kf-term">Why it matters:</span> {finding.why}</p>
      <p><span className="kf-term">What to do:</span> {finding.action}</p>
    </li>
  );
}

export default function KeyFindings({ findings, facility }) {
  const [showAll, setShowAll] = useState(false);

  if (!findings) {
    return (
      <div className="kf-container">
        <h2>Key findings</h2>
        <p className="kf-muted">Findings appear here once the assessment has been analysed.</p>
      </div>
    );
  }

  const { concerns = [], strengths = [], risk_velocity: velocity, unusual_combination: combo } = findings;
  const visible = showAll ? concerns : concerns.slice(0, COLLAPSED_COUNT);

  return (
    <div className="kf-container">
      <h2>Key findings</h2>
      <p className="kf-summary">{summaryText(concerns)}</p>

      <section className="kf-section">
        <h3>Change since last time</h3>
        <ChangeSinceLast velocity={velocity} facility={facility} />
      </section>

      <section className="kf-section">
        <h3>What needs attention</h3>
        {concerns.length === 0 ? (
          <p className="kf-all-clear">
            <span aria-hidden="true">✓</span> No answers are in the high or critical risk range.
          </p>
        ) : (
          <>
            <ul className="kf-concerns">
              {visible.map((f) => <Concern key={f.field} finding={f} />)}
            </ul>
            {concerns.length > COLLAPSED_COUNT && (
              <button className="btn-link kf-more" onClick={() => setShowAll((v) => !v)}>
                {showAll ? 'Show fewer' : `Show all ${concerns.length}`}
              </button>
            )}
          </>
        )}
      </section>

      {strengths.length > 0 && (
        <section className="kf-section">
          <h3>Strengths</h3>
          <ul className="kf-strengths">
            {strengths.map((s) => (
              <li key={s.field}>
                <span aria-hidden="true">✓</span> {s.label}: <strong>{s.answer}</strong>
              </li>
            ))}
          </ul>
        </section>
      )}

      <details className="kf-details">
        <summary>How this was calculated</summary>
        <p>
          Each answer is placed on the same 0–100 risk scale as the overall score (higher means riskier;
          for coverage, guard and response-time numbers a higher answer means lower risk).
          <strong> Urgent</strong> means "Poor" or a score of 80 or more; <strong>Needs attention</strong> means
          "Fair" or 60–79. <strong>Strengths</strong> are "Excellent" answers or a risk of 15 or less.
        </p>
        {combo && (
          <p>
            <strong>Overall pattern:</strong>{' '}
            {combo.unusual
              ? 'this mix of category scores is unusual'
              : 'this mix of category scores looks typical'}{' '}
            compared with{' '}
            {combo.compared_with === 'own_history'
              ? 'earlier assessments of this facility'
              : 'typical facility profiles built into the tool (there are fewer than five earlier assessments to compare with)'}.
            {' '}It's a statistical check (isolation forest; unusualness {Math.round(combo.score * 100)}/100) and
            a hint to look closer, not a problem on its own.
          </p>
        )}
      </details>
    </div>
  );
}
