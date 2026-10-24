import React, { useState, useEffect } from 'react';
import { useToast, ToastStack } from './Toast.jsx';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/* ── Inline SVG icons ────────────────────────────────────────────────────── */
const IconRefresh = ({ spin }) => (
  <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor" style={spin ? { animation:'spin 0.85s linear infinite' } : {}}>
    <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd"/>
  </svg>
);

const IconPlay = () => (
  <svg width="13" height="13" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd"/>
  </svg>
);

const IconMonitor = () => (
  <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
    <path d="M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z"/>
    <path d="M12 2.252A8.014 8.014 0 0117.748 8H12V2.252z"/>
  </svg>
);

const IconRetrain = () => (
  <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
    <path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14c.015-.998.233-1.983.645-2.897A8.003 8.003 0 0010 4a8 8 0 00-3.62 15.146.997.997 0 00.645-1.892A6 6 0 0110 6a6.001 6.001 0 012.133 11.607c.243.632.802 1.108 1.485 1.269A8.003 8.003 0 0012 14z"/>
  </svg>
);

const IconExternal = () => (
  <svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor">
    <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"/>
    <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z"/>
  </svg>
);

export default function StatusPage({ repoId, onBackToList }) {
  const { toasts, push, dismiss } = useToast();

  const [statusData,     setStatusData]     = useState(null);
  const [loading,        setLoading]        = useState(true);
  const [error,          setError]          = useState(null);
  const [retraining,     setRetraining]     = useState(false);
  const [pipelineRunning,setPipelineRunning]= useState(false);
  const [simulatingNormal,setSimNormal]     = useState(false);
  const [simulatingDrift, setSimDrift]      = useState(false);
  const [simResult,      setSimResult]      = useState(null);
  const [runningMonitor, setRunningMonitor] = useState(false);
  const [activeReportTab,setActiveReportTab]= useState('summary');

  const fetchStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API_BASE}/status/${repoId}`);
      if (!res.ok) throw new Error(`Failed to load repository status (HTTP ${res.status})`);
      setStatusData(await res.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [repoId]);

  const handleManualRetrain = async () => {
    setRetraining(true);
    try {
      const res = await fetch(`${API_BASE}/repos/${repoId}/retrain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: 'Dashboard manual operator trigger' })
      });
      const result = await res.json();
      push(
        result.triggered
          ? 'Retraining pipeline dispatched successfully.'
          : `Circuit breaker: ${result.reason}`,
        result.triggered ? 'success' : 'warning'
      );
      fetchStatus();
    } catch (err) {
      push(`Error triggering retrain: ${err.message}`, 'error');
    } finally {
      setRetraining(false);
    }
  };

  const handleRunPipeline = async () => {
    setPipelineRunning(true);
    try {
      const res = await fetch(`${API_BASE}/repos/${repoId}/run-pipeline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      const result = await res.json();
      push(
        result.status === 'queued'
          ? 'Pipeline started — training will begin shortly. Status auto-refreshes.'
          : `Pipeline: ${result.message}`,
        result.status === 'queued' ? 'success' : 'info'
      );
      fetchStatus();
    } catch (err) {
      push(`Error starting pipeline: ${err.message}`, 'error');
    } finally {
      setPipelineRunning(false);
    }
  };

  const handleRunMonitoring = async () => {
    setRunningMonitor(true);
    try {
      const res = await fetch(`${API_BASE}/status/${repoId}/run-monitoring`, { method: 'POST' });
      const result = await res.json();
      push(result.message || 'Monitoring cycle started.', 'info');
      setTimeout(fetchStatus, 3000);
    } catch (err) {
      push(`Monitoring error: ${err.message}`, 'error');
    } finally {
      setRunningMonitor(false);
    }
  };

  const handleSimulateTraffic = async (mode) => {
    const setter = mode === 'drifted' ? setSimDrift : setSimNormal;
    setter(true);
    setSimResult(null);
    try {
      const res = await fetch(`${API_BASE}/repos/${repoId}/simulate-traffic`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, n_samples: 150 })
      });
      const result = await res.json();
      setSimResult(result);
      setTimeout(() => setSimResult(null), 6000);
      fetchStatus();
    } catch (err) {
      push(`Traffic simulation error: ${err.message}`, 'error');
    } finally {
      setter(false);
    }
  };

  /* ── Loading / error states ─────────────────────────────────────────────── */
  if (loading && !statusData) {
    return (
      <div className="loading-state">
        <div className="loading-spinner" />
        <div className="loading-state-title">Loading repository status</div>
        <div className="loading-state-sub">Polling health metrics and deployment metadata</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card" style={{ maxWidth:600, margin:'2rem auto', textAlign:'center' }}>
        <h3 style={{ color:'var(--red)', marginBottom:'1rem' }}>Connection Error</h3>
        <p style={{ color:'var(--text-2)', marginBottom:'1.5rem' }}>{error}</p>
        <button className="btn btn-secondary" onClick={fetchStatus}>Retry</button>
      </div>
    );
  }

  const { latest_run, deployment, monitoring, reports } = statusData;
  const metrics = latest_run?.metrics || {};

  return (
    <div>
      {/* ── Circuit breaker banner ─────────────────────────────────────────── */}
      {monitoring?.circuit_breaker_active && (
        <div className="banner banner-error">
          <svg viewBox="0 0 20 20" fill="currentColor" className="banner-icon">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd"/>
          </svg>
          <div className="banner-body">
            <div className="banner-title">Retraining circuit breaker engaged</div>
            <div className="banner-desc">
              Auto-retraining halted. {monitoring.retrain_count_24h}/{monitoring.max_retrains_limit} retrains in the last 24 h — possible fundamental data drift.
            </div>
          </div>
          <button className="btn btn-danger btn-sm" onClick={handleManualRetrain} disabled={retraining}>
            {retraining ? 'Dispatching…' : 'Force Retrain'}
          </button>
        </div>
      )}

      {/* ── Simulation result banner ───────────────────────────────────────── */}
      {simResult && (
        <div className={`banner ${simResult.mode === 'drifted' ? 'banner-warning' : 'banner-success'}`}>
          <svg viewBox="0 0 20 20" fill="currentColor" className="banner-icon">
            {simResult.mode === 'drifted'
              ? <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd"/>
              : <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/>
            }
          </svg>
          <div className="banner-body">
            <div className="banner-title">{simResult.message}</div>
            <div className="banner-desc">Total traffic logged: {simResult.total_traffic_logged} requests</div>
          </div>
        </div>
      )}

      {/* ── Repo header card ───────────────────────────────────────────────── */}
      <div className="card">
        <div className="repo-header">
          <div>
            <div className="repo-title-row">
              <h1 className="repo-title">{statusData.repo_name}</h1>
              <span className={`badge badge-${latest_run?.status || 'pending'}`}>
                Pipeline: {latest_run?.status || 'idle'}
              </span>
              <span className={`badge badge-${deployment?.status || 'inactive'}`}>
                Deploy: {deployment?.status || 'inactive'}
              </span>
            </div>
            <div className="repo-meta">
              <span>ID: <code style={{ fontFamily:'JetBrains Mono', fontSize:'0.8rem' }}>{statusData.repo_id}</code></span>
              <span>Port: <code style={{ fontFamily:'JetBrains Mono', fontSize:'0.8rem' }}>{deployment?.port || 'N/A'}</code></span>
              <a href={statusData.github_url} target="_blank" rel="noreferrer">
                View on GitHub <IconExternal />
              </a>
            </div>
          </div>

          <div className="action-group">
            <button className="btn btn-secondary btn-sm" onClick={fetchStatus} title="Refresh">
              <IconRefresh spin={loading} />
              Refresh
            </button>
            <button
              className="btn btn-secondary btn-sm"
              style={{ borderColor:'rgba(56,189,248,0.35)', color:'var(--cyan)' }}
              onClick={handleRunPipeline}
              disabled={pipelineRunning}
            >
              <IconPlay />
              {pipelineRunning ? 'Starting…' : 'Run Pipeline'}
            </button>
            <button
              className="btn btn-secondary btn-sm"
              style={{ borderColor:'rgba(16,185,129,0.35)', color:'var(--green)' }}
              onClick={handleRunMonitoring}
              disabled={runningMonitor}
            >
              <IconMonitor />
              {runningMonitor ? 'Checking…' : 'Run Monitoring'}
            </button>
            <button className="btn btn-primary btn-sm" onClick={handleManualRetrain} disabled={retraining}>
              <IconRetrain />
              {retraining ? 'Retraining…' : 'Retrain'}
            </button>
          </div>
        </div>
      </div>

      {/* ── Active endpoint banner ─────────────────────────────────────────── */}
      {deployment?.url && (
        <div className="card endpoint-banner">
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', gap:'1rem', flexWrap:'wrap' }}>
            <div>
              <div className="endpoint-label">Active Serving Endpoint</div>
              <div className="endpoint-url">{deployment.url}</div>
              <div className="endpoint-meta">
                Inference: <code>{deployment.url}/predict</code> · Commit: <code>{deployment.deployed_commit_sha?.substring(0,7) || 'N/A'}</code>
              </div>
            </div>
            <a href={`${deployment.url}/health`} target="_blank" rel="noreferrer" className="btn btn-secondary btn-sm">
              Check Health <IconExternal />
            </a>
          </div>
        </div>
      )}

      {/* ── Metric summary row ─────────────────────────────────────────────── */}
      <div className="grid-3" style={{ marginBottom:'1.25rem' }}>
        <div className="metric-box">
          <div className="metric-label">Model Accuracy / R²</div>
          <div className="metric-value" style={{ color:'var(--cyan)' }}>
            {metrics.accuracy !== undefined
              ? `${(metrics.accuracy * 100).toFixed(1)}%`
              : (metrics.r_squared !== undefined ? metrics.r_squared : 'N/A')}
          </div>
          <div className="metric-sub">
            F1: {metrics.f1 !== undefined ? metrics.f1 : 'N/A'} · Loss: {metrics.loss !== undefined ? metrics.loss : 'N/A'}
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">Production Feature Drift</div>
          <div style={{ marginTop:'0.25rem' }}>
            <span className={`badge ${monitoring?.drift_detected ? 'badge-failed' : 'badge-healthy'}`}
              style={{ fontSize:'0.8rem' }}>
              {monitoring?.drift_detected ? 'Drift Detected' : 'Stable'}
            </span>
          </div>
          <div className="metric-sub">
            Affected: {monitoring?.drifted_columns?.length > 0 ? monitoring.drifted_columns.join(', ') : 'None'}
          </div>
        </div>

        <div className="metric-box">
          <div className="metric-label">Anomaly Rate (Isolation Forest)</div>
          <div className="metric-value"
            style={{ color:(monitoring?.anomaly_rate > 0.15) ? 'var(--red)' : 'var(--green)' }}>
            {monitoring?.anomaly_rate !== undefined ? `${(monitoring.anomaly_rate * 100).toFixed(1)}%` : '0.0%'}
          </div>
          <div className="metric-sub">
            Threshold: {(monitoring?.anomaly_threshold * 100 || 15)}% · Retrains 24 h: {monitoring?.retrain_count_24h || 0}
          </div>
        </div>
      </div>

      {/* ── Traffic simulation ─────────────────────────────────────────────── */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="section-title">Traffic Simulation</div>
            <div className="section-sub">Log synthetic prediction requests to test drift detection and monitoring cycles.</div>
          </div>
        </div>
        <div className="action-group">
          <button
            className="btn btn-success btn-sm"
            onClick={() => handleSimulateTraffic('normal')}
            disabled={simulatingNormal || simulatingDrift}
          >
            <svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="currentColor"/></svg>
            {simulatingNormal ? 'Simulating…' : 'Normal Traffic (150 samples)'}
          </button>
          <button
            className="btn btn-danger btn-sm"
            onClick={() => handleSimulateTraffic('drifted')}
            disabled={simulatingNormal || simulatingDrift}
          >
            <svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" fill="currentColor"/></svg>
            {simulatingDrift ? 'Simulating…' : 'Drifted Traffic (150 samples)'}
          </button>
        </div>
        <p style={{ fontSize:'0.77rem', color:'var(--text-3)', marginTop:'0.75rem' }}>
          Drifted mode shifts <code>petal_length</code> to N(12.0, 1.5) — 3× off-distribution — to immediately trigger Evidently drift detection.
        </p>
      </div>

      {/* ── Change explainer ───────────────────────────────────────────────── */}
      <div className="card">
        <div className="card-header">
          <div>
            <div className="section-title">Change Explainer</div>
            <div className="section-sub">Deterministic AST parser + metric deltas</div>
          </div>
        </div>
        <div className="report-summary">
          {reports?.change_explainer?.summary || 'Initial model version active.'}
        </div>
        {reports?.change_explainer?.details && (
          <ul className="report-details">
            {reports.change_explainer.details.map((item, idx) => (
              <li key={idx}>{item}</li>
            ))}
          </ul>
        )}
      </div>

      {/* ── Evidently reports (tabbed) ─────────────────────────────────────── */}
      <div className="card">
        <div className="tab-bar">
          <button
            className={`tab-btn ${activeReportTab === 'summary' ? 'active' : ''}`}
            onClick={() => setActiveReportTab('summary')}
          >
            Pipeline Summary
          </button>
          {reports?.version_comparison_html && (
            <button
              className={`tab-btn ${activeReportTab === 'comparison' ? 'active' : ''}`}
              onClick={() => setActiveReportTab('comparison')}
            >
              Version Comparison
            </button>
          )}
          {reports?.production_drift_html && (
            <button
              className={`tab-btn ${activeReportTab === 'drift' ? 'active' : ''}`}
              onClick={() => setActiveReportTab('drift')}
            >
              Production Drift
            </button>
          )}
        </div>

        {activeReportTab === 'summary' && (
          <div>
            <p style={{ fontSize:'0.855rem', color:'var(--text-2)', marginBottom:'1rem' }}>
              Send a test vector through the deployed serving model to verify predictions and logging:
            </p>
            <pre>
{`curl -X POST ${deployment?.url || 'http://localhost:8001'}/predict \\
  -H "Content-Type: application/json" \\
  -d '{"features": {"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2}}'`}
            </pre>

            {Object.keys(metrics).some(k => ['accuracy','precision','recall','f1'].includes(k) && metrics[k] !== undefined) && (
              <div style={{ marginTop:'1.25rem' }}>
                <div style={{ fontSize:'0.8rem', color:'var(--text-2)', fontWeight:600, textTransform:'uppercase', letterSpacing:'0.05em', marginBottom:'0.75rem' }}>
                  Metrics Summary
                </div>
                <div className="grid-4">
                  {['accuracy','precision','recall','f1'].map(m =>
                    metrics[m] !== undefined && (
                      <div key={m} className="metric-tile">
                        <div className="metric-tile-label">{m}</div>
                        <div className="metric-tile-value">{(metrics[m] * 100).toFixed(1)}%</div>
                      </div>
                    )
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {activeReportTab === 'comparison' && reports?.version_comparison_html && (
          <div style={{ height:550 }}>
            <iframe
              src={`${API_BASE}/${reports.version_comparison_html}`}
              title="Evidently Version Comparison"
              style={{ width:'100%', height:'100%', border:'none', borderRadius:'var(--r-md)' }}
            />
          </div>
        )}

        {activeReportTab === 'drift' && reports?.production_drift_html && (
          <div style={{ height:550 }}>
            <iframe
              src={`${API_BASE}/${reports.production_drift_html}`}
              title="Evidently Production Drift"
              style={{ width:'100%', height:'100%', border:'none', borderRadius:'var(--r-md)' }}
            />
          </div>
        )}
      </div>

      <ToastStack toasts={toasts} dismiss={dismiss} />
    </div>
  );
}
