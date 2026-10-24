import React, { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function StatusPage({ repoId, onBackToList }) {
  const [statusData, setStatusData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [retraining, setRetraining] = useState(false);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [simulatingNormal, setSimulatingNormal] = useState(false);
  const [simulatingDrift, setSimulatingDrift] = useState(false);
  const [simResult, setSimResult] = useState(null);
  const [activeReportTab, setActiveReportTab] = useState('summary'); // 'summary' | 'comparison' | 'drift'

  const fetchStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API_BASE}/status/${repoId}`);
      if (!res.ok) {
        throw new Error(`Failed to load repository status (HTTP ${res.status})`);
      }
      const data = await res.json();
      setStatusData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000); // 10s auto-refresh
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
      alert(result.triggered ? '🔄 Retraining pipeline dispatched!' : `Circuit Breaker: ${result.reason}`);
      fetchStatus();
    } catch (err) {
      alert(`Error triggering retrain: ${err.message}`);
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
      alert(result.status === 'queued'
        ? '▶️ Pipeline started! Training will begin in seconds. Status will auto-refresh.'
        : `Pipeline status: ${result.message}`);
      fetchStatus();
    } catch (err) {
      alert(`Error starting pipeline: ${err.message}`);
    } finally {
      setPipelineRunning(false);
    }
  };

  const handleSimulateTraffic = async (mode) => {
    const setter = mode === 'drifted' ? setSimulatingDrift : setSimulatingNormal;
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
      setTimeout(() => setSimResult(null), 6000); // auto-clear after 6s
      fetchStatus();
    } catch (err) {
      alert(`Traffic simulation error: ${err.message}`);
    } finally {
      setter(false);
    }
  };

  if (loading && !statusData) {
    return (
      <div style={{ textAlign: 'center', padding: '4rem' }}>
        <div className="loading-spinner" style={{ margin: '0 auto 1rem' }} />
        <div style={{ color: 'var(--accent-cyan)', fontSize: '1.2rem', marginBottom: '0.5rem' }}>
          Loading AutoMLOps Status Engine...
        </div>
        <p style={{ color: 'var(--text-secondary)' }}>Polling health metrics and deployment metadata</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card" style={{ maxWidth: '600px', margin: '2rem auto', textAlign: 'center' }}>
        <h3 style={{ color: '#f87171', marginBottom: '1rem' }}>Connection Error</h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>{error}</p>
        <button className="btn btn-secondary" onClick={fetchStatus}>Retry</button>
      </div>
    );
  }

  const { latest_run, deployment, monitoring, reports } = statusData;
  const metrics = latest_run?.metrics || {};

  return (
    <div>
      {/* Circuit Breaker Trip Banner */}
      {monitoring?.circuit_breaker_active && (
        <div className="circuit-breaker-banner">
          <div>
            <h3 style={{ color: '#fecaca', fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.2rem' }}>
              🚨 Retraining Circuit Breaker Engaged!
            </h3>
            <p style={{ color: '#fca5a5', fontSize: '0.85rem' }}>
              Automated retraining halted. {monitoring.retrain_count_24h}/{monitoring.max_retrains_limit} auto-retrains triggered in the last 24h.
              Potential fundamental data drift detected.
            </p>
          </div>
          <button
            className="btn btn-danger"
            style={{ whiteSpace: 'nowrap' }}
            onClick={handleManualRetrain}
            disabled={retraining}
          >
            {retraining ? 'Dispatching...' : 'Override & Force Retrain'}
          </button>
        </div>
      )}

      {/* Traffic Simulation Result Banner */}
      {simResult && (
        <div style={{
          background: simResult.mode === 'drifted'
            ? 'linear-gradient(135deg, rgba(239,68,68,0.12), rgba(185,28,28,0.15))'
            : 'linear-gradient(135deg, rgba(16,185,129,0.12), rgba(5,150,105,0.15))',
          border: `1px solid ${simResult.mode === 'drifted' ? 'rgba(239,68,68,0.35)' : 'rgba(16,185,129,0.35)'}`,
          borderRadius: 'var(--radius-lg)',
          padding: '1rem 1.5rem',
          marginBottom: '1.25rem',
          display: 'flex',
          alignItems: 'center',
          gap: '1rem'
        }}>
          <span style={{ fontSize: '1.5rem' }}>{simResult.mode === 'drifted' ? '⚠️' : '✅'}</span>
          <div>
            <div style={{ fontWeight: 600, color: '#f8fafc', marginBottom: '0.1rem' }}>
              {simResult.message}
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Total traffic logged: {simResult.total_traffic_logged} requests
            </div>
          </div>
        </div>
      )}

      {/* Top Header Card */}
      <div className="card" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.4rem' }}>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 800 }}>{statusData.repo_name}</h1>
            <span className={`badge badge-${latest_run?.status || 'pending'}`}>
              Pipeline: {latest_run?.status || 'idle'}
            </span>
            <span className={`badge badge-${deployment?.status || 'inactive'}`}>
              Deploy: {deployment?.status || 'inactive'}
            </span>
          </div>
          <div style={{ display: 'flex', gap: '1rem', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            <span>ID: <code>{statusData.repo_id}</code></span>
            <span>Port: <code>{deployment?.port || 'N/A'}</code></span>
            <a href={statusData.github_url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-cyan)' }}>
              View on GitHub ↗
            </a>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button className="btn btn-secondary" onClick={fetchStatus}>↻ Refresh</button>
          <button
            className="btn btn-secondary"
            style={{ borderColor: 'rgba(56,189,248,0.4)', color: 'var(--accent-cyan)' }}
            onClick={handleRunPipeline}
            disabled={pipelineRunning}
          >
            {pipelineRunning ? '⏳ Starting...' : '▶ Run Pipeline'}
          </button>
          <button
            className="btn btn-primary"
            onClick={handleManualRetrain}
            disabled={retraining}
          >
            {retraining ? 'Retraining...' : '🔄 Trigger Retrain'}
          </button>
        </div>
      </div>

      {/* Deployment & Live Gateway Banner */}
      {deployment?.url && (
        <div className="card" style={{
          background: 'linear-gradient(135deg, rgba(56, 189, 248, 0.08), rgba(59, 130, 246, 0.05))',
          borderColor: 'var(--border-highlight)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem'
        }}>
          <div>
            <div style={{ fontSize: '0.8rem', color: 'var(--accent-cyan)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '0.3rem' }}>
              🌐 Active Serving Endpoint
            </div>
            <div style={{ fontSize: '1.05rem', fontWeight: 600, fontFamily: 'JetBrains Mono', color: '#f8fafc' }}>
              {deployment.url}
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
              Inference: <code>{deployment.url}/predict</code> • Commit: <code>{deployment.deployed_commit_sha?.substring(0, 7) || 'N/A'}</code>
            </div>
          </div>
          <a
            href={`${deployment.url}/health`}
            target="_blank"
            rel="noreferrer"
            className="btn btn-secondary"
            style={{ fontSize: '0.8rem' }}
          >
            Check Health ↗
          </a>
        </div>
      )}

      {/* Grid: Metrics, Monitoring, Quality Gate */}
      <div className="grid-3" style={{ marginBottom: '1.5rem' }}>
        {/* Model Metrics */}
        <div className="metric-box">
          <div className="metric-label">Model Accuracy / R²</div>
          <div className="metric-value" style={{ color: 'var(--accent-cyan)' }}>
            {metrics.accuracy !== undefined
              ? `${(metrics.accuracy * 100).toFixed(1)}%`
              : (metrics.r_squared !== undefined ? metrics.r_squared : 'N/A')}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
            F1: {metrics.f1 !== undefined ? metrics.f1 : 'N/A'} • Loss: {metrics.loss !== undefined ? metrics.loss : 'N/A'}
          </div>
        </div>

        {/* Data Drift Indicator */}
        <div className="metric-box">
          <div className="metric-label">Production Feature Drift</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.2rem' }}>
            <span className={`badge ${monitoring?.drift_detected ? 'badge-failed' : 'badge-healthy'}`} style={{ fontSize: '0.85rem' }}>
              {monitoring?.drift_detected ? '⚠️ DRIFT DETECTED' : '✅ STABLE'}
            </span>
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.6rem' }}>
            Drifted: {monitoring?.drifted_columns?.length > 0 ? monitoring.drifted_columns.join(', ') : 'None'}
          </div>
        </div>

        {/* Isolation Forest Anomaly Rate */}
        <div className="metric-box">
          <div className="metric-label">Isolation Forest Anomaly Rate</div>
          <div className="metric-value" style={{ color: (monitoring?.anomaly_rate > 0.15) ? 'var(--accent-red)' : 'var(--accent-green)' }}>
            {monitoring?.anomaly_rate !== undefined ? `${(monitoring.anomaly_rate * 100).toFixed(1)}%` : '0.0%'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
            Threshold: {(monitoring?.anomaly_threshold * 100 || 15)}% • Retrains 24h: {monitoring?.retrain_count_24h || 0}
          </div>
        </div>
      </div>

      {/* Traffic Simulation Controls */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, marginBottom: '0.25rem' }}>
              🧪 Traffic Simulation
            </h3>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Log synthetic prediction requests to test drift detection and monitoring cycles.
            </p>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
          <button
            className="btn btn-secondary"
            style={{ borderColor: 'rgba(16,185,129,0.4)', color: '#34d399', gap: '0.5rem' }}
            onClick={() => handleSimulateTraffic('normal')}
            disabled={simulatingNormal || simulatingDrift}
          >
            {simulatingNormal ? '⏳ Simulating...' : '🟢 Simulate Normal Traffic (150 samples)'}
          </button>
          <button
            className="btn btn-secondary"
            style={{ borderColor: 'rgba(239,68,68,0.4)', color: '#f87171', gap: '0.5rem' }}
            onClick={() => handleSimulateTraffic('drifted')}
            disabled={simulatingNormal || simulatingDrift}
          >
            {simulatingDrift ? '⏳ Simulating...' : '🔴 Simulate Drifted Traffic (150 samples)'}
          </button>
        </div>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.75rem' }}>
          Drifted mode shifts <code>petal_length</code> to N(12.0, 1.5) — 3× off normal — to immediately trigger Evidently drift detection.
        </div>
      </div>

      {/* Change Explainer Report */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ fontSize: '1.15rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span>🔍</span> Change Explainer & AST Diff Report
          </h3>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Deterministic AST Parser + Metric Deltas</span>
        </div>

        <div style={{
          background: 'rgba(15, 23, 42, 0.7)',
          borderRadius: 'var(--radius-md)',
          padding: '1rem 1.25rem',
          borderLeft: '4px solid var(--accent-cyan)',
          marginBottom: '1rem'
        }}>
          <p style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.95rem' }}>
            {reports?.change_explainer?.summary || 'Initial model version active.'}
          </p>
        </div>

        {reports?.change_explainer?.details && (
          <ul style={{ paddingLeft: '1.25rem', color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
            {reports.change_explainer.details.map((item, idx) => (
              <li key={idx} style={{ marginBottom: '0.4rem' }}>{item}</li>
            ))}
          </ul>
        )}
      </div>

      {/* Evidently Reports Tab Section */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '0.75rem' }}>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button
              className={`btn ${activeReportTab === 'summary' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setActiveReportTab('summary')}
            >
              Pipeline Summary
            </button>
            {reports?.version_comparison_html && (
              <button
                className={`btn ${activeReportTab === 'comparison' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setActiveReportTab('comparison')}
              >
                Evidently Version Comparison
              </button>
            )}
            {reports?.production_drift_html && (
              <button
                className={`btn ${activeReportTab === 'drift' ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setActiveReportTab('drift')}
              >
                Production Drift Report
              </button>
            )}
          </div>
        </div>

        {activeReportTab === 'summary' && (
          <div>
            <h4 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.75rem' }}>Live Inference Sample Tester</h4>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>
              Send a test vector through the deployed serving model to verify predictions and logging:
            </p>
            <pre style={{ background: '#090d16', padding: '1rem', borderRadius: 'var(--radius-md)', fontSize: '0.82rem', overflowX: 'auto' }}>
{`curl -X POST ${deployment?.url || 'http://localhost:8001'}/predict \\
  -H "Content-Type: application/json" \\
  -d '{"features": {"sepal_length": 5.1, "sepal_width": 3.5, "petal_length": 1.4, "petal_width": 0.2}}'`}
            </pre>

            <div style={{ marginTop: '1.25rem' }}>
              <h4 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '0.6rem', color: 'var(--text-secondary)' }}>
                Pipeline Metrics Summary
              </h4>
              <div className="grid-4">
                {['accuracy', 'precision', 'recall', 'f1'].map(m => (
                  metrics[m] !== undefined && (
                    <div key={m} style={{ background: 'rgba(15,23,42,0.6)', borderRadius: 'var(--radius-md)', padding: '0.85rem', border: '1px solid var(--border-color)', textAlign: 'center' }}>
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.4rem' }}>{m}</div>
                      <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--accent-cyan)', fontFamily: 'JetBrains Mono' }}>
                        {(metrics[m] * 100).toFixed(1)}%
                      </div>
                    </div>
                  )
                ))}
              </div>
            </div>
          </div>
        )}

        {activeReportTab === 'comparison' && reports?.version_comparison_html && (
          <div style={{ height: '550px' }}>
            <iframe
              src={`${API_BASE}/${reports.version_comparison_html}`}
              title="Evidently Version Comparison"
              style={{ width: '100%', height: '100%', border: 'none', borderRadius: 'var(--radius-md)' }}
            />
          </div>
        )}

        {activeReportTab === 'drift' && reports?.production_drift_html && (
          <div style={{ height: '550px' }}>
            <iframe
              src={`${API_BASE}/${reports.production_drift_html}`}
              title="Evidently Production Drift"
              style={{ width: '100%', height: '100%', border: 'none', borderRadius: 'var(--radius-md)' }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
