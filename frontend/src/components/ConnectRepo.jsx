import React, { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const DEFAULT_SAMPLE_YAML = `project_name: "iris-classifier-demo"
framework: "sklearn"
task_type: "classification"
entry_point: "ml/train.py"
predict_module: "ml/predict.py"
target_column: "species"
numerical_features:
  - "sepal_length"
  - "sepal_width"
  - "petal_length"
  - "petal_width"
categorical_features: []
metrics_threshold:
  accuracy: 0.85
  precision: 0.80
dependencies: "requirements.txt"
dataset_path: "data/iris.csv"`;

export default function ConnectRepo({ onRepoConnected, onCancel }) {
  const [repoUrl, setRepoUrl] = useState('https://github.com/joel-95/iris-classifier-demo');
  const [yamlContent, setYamlContent] = useState(DEFAULT_SAMPLE_YAML);
  const [loading, setLoading] = useState(false);
  const [validationErrors, setValidationErrors] = useState([]);
  const [successInfo, setSuccessInfo] = useState(null);

  const handleConnect = async (e) => {
    e.preventDefault();
    setLoading(true);
    setValidationErrors([]);
    setSuccessInfo(null);

    try {
      const res = await fetch(`${API_BASE}/repos/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          github_url: repoUrl,
          yaml_content: yamlContent,
          repo_file_list: [
            'ml/train.py',
            'ml/predict.py',
            'requirements.txt',
            'data/iris.csv'
          ]
        })
      });

      const data = await res.json();

      if (res.status === 422) {
        // Validation failure from validator.py
        const errs = data.detail?.errors || [data.detail?.message || 'Validation error'];
        setValidationErrors(errs);
      } else if (!res.ok) {
        setValidationErrors([data.detail || `Server error: HTTP ${res.status}`]);
      } else {
        setSuccessInfo(data);
        if (onRepoConnected) {
          setTimeout(() => onRepoConnected(data.repo_id), 1200);
        }
      }
    } catch (err) {
      setValidationErrors([`Network connection failure: ${err.message}`]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: '780px', margin: '0 auto' }}>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 700 }}>Connect GitHub Repository</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
              AutoMLOps will validate your manifest and configure self-hosted GPU CI/CD.
            </p>
          </div>
          {onCancel && (
            <button className="btn btn-secondary" onClick={onCancel}>Back</button>
          )}
        </div>

        {validationErrors.length > 0 && (
          <div style={{
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            borderRadius: 'var(--radius-md)',
            padding: '1rem',
            marginBottom: '1.5rem'
          }}>
            <h4 style={{ color: '#f87171', fontSize: '0.9rem', marginBottom: '0.5rem', fontWeight: 600 }}>
              ❌ Manifest / Repository Validation Errors:
            </h4>
            <ul style={{ paddingLeft: '1.25rem', color: '#fca5a5', fontSize: '0.85rem' }}>
              {validationErrors.map((err, idx) => (
                <li key={idx} style={{ marginBottom: '0.25rem' }}>{err}</li>
              ))}
            </ul>
          </div>
        )}

        {successInfo && (
          <div style={{
            background: 'rgba(16, 185, 129, 0.15)',
            border: '1px solid rgba(16, 185, 129, 0.4)',
            borderRadius: 'var(--radius-md)',
            padding: '1rem',
            marginBottom: '1.5rem',
            color: '#34d399'
          }}>
            ✅ <strong>{successInfo.message}!</strong> Assigned deterministic port: <code>{successInfo.assigned_port}</code>.
          </div>
        )}

        <form onSubmit={handleConnect}>
          <div style={{ marginBottom: '1.25rem' }}>
            <label htmlFor="repo-url">Repository GitHub URL</label>
            <input
              id="repo-url"
              type="url"
              required
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/organization/repo-name"
            />
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
              <label htmlFor="mlops-yaml">Manifest (<code>mlops.yaml</code> Schema)</label>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Task-Type &amp; Metrics Contract</span>
            </div>
            <textarea
              id="mlops-yaml"
              rows={12}
              style={{ fontFamily: 'JetBrains Mono', fontSize: '0.85rem' }}
              value={yamlContent}
              onChange={(e) => setYamlContent(e.target.value)}
            />
          </div>

          <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
            {onCancel && (
              <button type="button" className="btn btn-secondary" onClick={onCancel}>
                Cancel
              </button>
            )}
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? 'Validating & Connecting...' : 'Validate & Connect Repo'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
