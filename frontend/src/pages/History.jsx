import React, { useEffect, useMemo, useState } from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
  LabelList,
} from 'recharts';
import { riskAPI, errorMessage } from '../api/apiClient';
import { useAssessment } from '../context/AssessmentContext';
import { RISK_THRESHOLDS, riskColor, riskName } from '../utils/risk';
import '../styles/History.css';

const ALL = '__all__';
const UNNAMED = 'Unnamed facility';
// Categorical slots in fixed order (dataviz reference palette, validated on white).
// Slots 3-5 are under 3:1 contrast, so lines also get a legend, end labels and the table.
const SERIES_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948'];
const MAX_SERIES = SERIES_COLORS.length;
const GRID_COLOR = '#e5e7eb';   // --border
const MUTED_TEXT = '#6b7280';

const facilityOf = (a) => a.facility_name || UNNAMED;
const fmtDate = (iso) =>
  new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
const DAY_MS = 24 * 60 * 60 * 1000;
const fmtTick = (t, spanMs) =>
  spanMs < 2 * DAY_MS
    ? new Date(t).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    : new Date(t).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
const fmtDateTime = (iso) =>
  new Date(iso).toLocaleString(undefined, {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });

function RiskBadge({ score }) {
  // Identity is never colour alone: the dot carries colour, the text says the level.
  return (
    <span className="risk-badge">
      <span className="risk-dot" style={{ background: riskColor(score) }} aria-hidden="true" />
      {riskName(score)}
    </span>
  );
}

function TrendTooltip({ active, payload }) {
  const point = payload?.find((entry) => entry.value != null);
  if (!active || !point) return null;
  const p = point.payload;
  return (
    <div className="trend-tooltip">
      <div className="trend-tooltip-when">{p.when}</div>
      <div className="trend-tooltip-facility">{p.facility}</div>
      <div className="trend-tooltip-score">
        <strong>{p.score.toFixed(1)}</strong> / 100 · <RiskBadge score={p.score} />
      </div>
    </div>
  );
}

function StatTile({ label, value, sub }) {
  return (
    <div className="stat-tile">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      {sub && <div className="stat-sub">{sub}</div>}
    </div>
  );
}

export default function History({ onOpen, onStart }) {
  const { dispatch } = useAssessment();
  const [items, setItems] = useState(null); // newest first, from the API
  const [error, setError] = useState(null);
  const [facility, setFacility] = useState(ALL);

  useEffect(() => {
    let cancelled = false;
    riskAPI.listAssessments(0, 100)
      .then((res) => { if (!cancelled) setItems(res.data); })
      .catch((err) => { if (!cancelled) setError(errorMessage(err, 'Could not load your assessments')); });
    return () => { cancelled = true; };
  }, []);

  const facilities = useMemo(
    () => [...new Set((items || []).map(facilityOf))].sort((a, b) => a.localeCompare(b)),
    [items],
  );

  const visible = useMemo(
    () => (items || []).filter((a) => facility === ALL || facilityOf(a) === facility),
    [items, facility],
  );

  // Colour follows the facility (alphabetical slot), never its rank in the
  // current filter, so a facility keeps its colour when you filter.
  const colorOf = useMemo(() => {
    const map = new Map(facilities.map((f, i) => [f, SERIES_COLORS[i % SERIES_COLORS.length]]));
    return (f) => map.get(f);
  }, [facilities]);

  // One line per facility: joining different sites into one line would
  // invent a trend that isn't there. Max 8 lines (most recently assessed).
  const chartFacilities = useMemo(() => {
    const seen = [];
    visible.forEach((a) => { const f = facilityOf(a); if (!seen.includes(f)) seen.push(f); });
    return seen.slice(0, MAX_SERIES);
  }, [visible]);

  const chartData = useMemo(
    () => [...visible].reverse()
      .filter((a) => chartFacilities.includes(facilityOf(a)))
      .map((a) => ({
        t: new Date(a.created_at).getTime(),
        when: fmtDateTime(a.created_at),
        facility: facilityOf(a),
        score: a.overall_score,
        [`s${chartFacilities.indexOf(facilityOf(a))}`]: a.overall_score,
      })),
    [visible, chartFacilities],
  );

  const openAssessment = async (a) => {
    // Load into the dashboard (SET_ASSESSMENT also switches to the Results tab),
    // then fill in key findings and the stored prediction. GET /predict never runs
    // the model, so revisiting doesn't create new prediction records.
    dispatch({ type: 'SET_ASSESSMENT', payload: a });
    onOpen();
    const [findingsRes, predRes] = await Promise.allSettled([
      riskAPI.getFindings(a.id),
      riskAPI.getPrediction(a.id),
    ]);
    if (findingsRes.status === 'fulfilled') {
      dispatch({ type: 'SET_FINDINGS', payload: findingsRes.value.data });
    }
    if (predRes.status === 'fulfilled') {
      dispatch({ type: 'SET_PREDICTIONS', payload: predRes.value.data });
    }
  };

  if (error) {
    return <div className="history"><div className="error-message">{error}</div></div>;
  }
  if (items === null) {
    return <div className="history"><p className="history-muted">Loading your assessments…</p></div>;
  }
  if (items.length === 0) {
    return (
      <div className="history history-empty">
        <h2>No assessments yet</h2>
        <p className="history-muted">Your completed assessments and risk trend will appear here.</p>
        <button className="btn-primary" onClick={onStart}>Start an assessment</button>
      </div>
    );
  }

  const latest = visible[0];
  // Compare like with like: the previous assessment of the SAME facility.
  const previous = visible.slice(1).find((a) => facilityOf(a) === facilityOf(latest));
  const spanMs = chartData.length > 1 ? chartData[chartData.length - 1].t - chartData[0].t : 0;
  const lastIndexOf = (f) => chartData.map((d) => d.facility).lastIndexOf(f);
  const delta = latest && previous ? latest.overall_score - previous.overall_score : null;
  const deltaText = delta === null
    ? 'No earlier assessment for this facility'
    : Math.abs(delta) < 0.05
      ? 'No change'
      : `${delta > 0 ? '▲' : '▼'} ${Math.abs(delta).toFixed(1)} pts · ${delta > 0 ? 'higher risk' : 'lower risk'}`;

  return (
    <div className="history">
      <div className="history-header">
        <div>
          <h2>Assessment history</h2>
          <p className="history-muted">Higher score means higher risk.</p>
        </div>
        {facilities.length > 1 && (
          <label className="history-filter">
            Facility
            <select value={facility} onChange={(e) => setFacility(e.target.value)}>
              <option value={ALL}>All facilities</option>
              {facilities.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
        )}
      </div>

      <div className="stat-row">
        <StatTile
          label="Latest score"
          value={latest.overall_score.toFixed(1)}
          sub={<RiskBadge score={latest.overall_score} />}
        />
        <StatTile label={`Change since previous · ${facilityOf(latest)}`} value={delta === null ? '—' : `${delta > 0 ? '+' : ''}${delta.toFixed(1)}`} sub={deltaText} />
        <StatTile label="Assessments" value={visible.length} sub={facility === ALL ? 'All facilities' : facility} />
      </div>

      <section className="trend-card">
        <h3>Overall risk score over time</h3>
        {chartData.length < 2 ? (
          <p className="history-muted">Complete another assessment to see your trend.</p>
        ) : (
          <div className="trend-chart">
            {chartFacilities.length > 1 && (
              <ul className="trend-legend" aria-label="Facilities">
                {chartFacilities.map((f) => (
                  <li key={f}>
                    <span className="trend-legend-key" style={{ background: colorOf(f) }} aria-hidden="true" />
                    {f}
                  </li>
                ))}
              </ul>
            )}
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={chartData} margin={{ top: 12, right: 104, bottom: 4, left: 0 }}>
                <CartesianGrid vertical={false} stroke={GRID_COLOR} />
                <XAxis
                  dataKey="t"
                  type="number"
                  scale="time"
                  domain={['dataMin', 'dataMax']}
                  tickFormatter={(t) => fmtTick(t, spanMs)}
                  tick={{ fill: MUTED_TEXT, fontSize: 12 }}
                  tickLine={false}
                  axisLine={{ stroke: GRID_COLOR }}
                  minTickGap={32}
                  padding={{ left: 12, right: 12 }}
                />
                <YAxis
                  domain={[0, 100]}
                  ticks={[0, 20, 40, 60, 80, 100]}
                  tick={{ fill: MUTED_TEXT, fontSize: 12 }}
                  tickLine={false}
                  axisLine={false}
                  width={36}
                />
                {RISK_THRESHOLDS.slice(0, 3).map((t) => (
                  <ReferenceLine
                    key={t.name}
                    y={t.max}
                    stroke="#d1d5db"
                    label={{ value: `${t.name} ≤${t.max}`, position: 'right', fill: MUTED_TEXT, fontSize: 11 }}
                  />
                ))}
                <Tooltip content={<TrendTooltip />} cursor={{ stroke: '#9ca3af', strokeWidth: 1 }} />
                {chartFacilities.map((f, i) => (
                  <Line
                    key={f}
                    type="linear"
                    dataKey={`s${i}`}
                    name={f}
                    connectNulls
                    stroke={colorOf(f)}
                    strokeWidth={2}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    dot={{ r: 4, fill: colorOf(f), stroke: '#fff', strokeWidth: 2 }}
                    activeDot={{ r: 6, fill: colorOf(f), stroke: '#fff', strokeWidth: 2 }}
                    isAnimationActive={false}
                  >
                    {chartFacilities.length > 1 && chartFacilities.length <= 4 && (
                      <LabelList
                        dataKey={`s${i}`}
                        content={({ x, y, index }) => (index === lastIndexOf(f) ? (
                          <text x={x + 10} y={y} dy={4} fontSize={12} fill="#374151">{f}</text>
                        ) : null)}
                      />
                    )}
                  </Line>
                ))}
              </LineChart>
            </ResponsiveContainer>
            {visible.some((a) => !chartFacilities.includes(facilityOf(a))) && (
              <p className="history-muted history-note">
                Chart shows the {MAX_SERIES} most recently assessed facilities. Use the filter to see the others.
              </p>
            )}
          </div>
        )}
      </section>

      <section>
        <table className="history-table">
          <caption className="visually-hidden">All assessments, newest first</caption>
          <thead>
            <tr>
              <th scope="col">Date</th>
              <th scope="col">Facility</th>
              <th scope="col" className="num">Score</th>
              <th scope="col">Risk level</th>
              <th scope="col"><span className="visually-hidden">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((a) => (
              <tr key={a.id}>
                <td>{fmtDateTime(a.created_at)}</td>
                <td>{facilityOf(a)}</td>
                <td className="num">{a.overall_score.toFixed(1)}</td>
                <td><RiskBadge score={a.overall_score} /></td>
                <td className="actions">
                  <button className="btn-link" onClick={() => openAssessment(a)}>
                    Open<span className="visually-hidden"> assessment from {fmtDate(a.created_at)}</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
