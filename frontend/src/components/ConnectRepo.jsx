import React, { useState } from 'react';
import { useToast, ToastStack } from './Toast.jsx';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const DEFAULT_SAMPLE_YAML = `project_name: "iris-classifier-demo"
# framework options: "sklearn" (RandomForest) | "xgboost" (XGBoost + Optuna)
framework: "xgboost"
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
  f1: 0.80
dependencies: "requirements.txt"
dataset_path: "demo_repo/data/iris.csv"

# XGBoost-specific settings (only used when framework: xgboost)
xgboost:
  optuna_trials: 20`;

/* ── Inline SVG icons ─────────────────────────────────────────────────────── */
const IconSearch = () => (
  <svg width="13" height="13" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z" clipRule="evenodd"/>
  </svg>
);

const IconRefresh = () => (
  <svg width="13" height="13" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd"/>
  </svg>
);

const IconDownload = () => (
  <svg width="13" height="13" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd"/>
  </svg>
);

const IconClose = () => (
  <svg width="12" height="12" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd"/>
  </svg>
);

const IconLock = () => (
  <svg width="10" height="10" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z" clipRule="evenodd"/>
  </svg>
);

export default function ConnectRepo({ onRepoConnected, onCancel }) {
  const { toasts, push, dismiss } = useToast();

  const [repoUrl, setRepoUrl] = useState('https://github.com/joel-95/iris-classifier-demo');
  const [yamlContent, setYamlContent] = useState(DEFAULT_SAMPLE_YAML);
  const [loading, setLoading] = useState(false);
  const [validationErrors, setValidationErrors] = useState([]);
  const [successInfo, setSuccessInfo] = useState(null);

  const [showRepoPicker, setShowRepoPicker] = useState(false);
  const [gitHubRepos, setGitHubRepos] = useState([]);
  const [loadingGitHubRepos, setLoadingGitHubRepos] = useState(false);
  const [gitHubRepoError, setGitHubRepoError] = useState(null);
  const [repoSearch, setRepoSearch] = useState('');

  const [fetchingTree, setFetchingTree] = useState(false);
  const [treeInfo, setTreeInfo] = useState(null);
  const [detectedFiles, setDetectedFiles] = useState([
    'ml/train.py',
    'ml/predict.py',
    'requirements.txt',
    'data/iris.csv'
  ]);

  const getAuthHeader = () => {
    try {
      const userStr = localStorage.getItem('automlops_user');
      if (userStr) {
        const u = JSON.parse(userStr);
        const token = u.token || u.access_token || u.github_token;
        if (token) return { Authorization: `Bearer ${token}` };
      }
    } catch (e) { /* ignore */ }
    return {};
  };

  const fetchUserRepos = async () => {
    setLoadingGitHubRepos(true);
    setGitHubRepoError(null);
    try {
      const res = await fetch(`${API_BASE}/repos/github/user-repos`, {
        headers: { 'Content-Type': 'application/json', ...getAuthHeader() }
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `GitHub API error (HTTP ${res.status})`);
      }
      setGitHubRepos(await res.json());
    } catch (err) {
      setGitHubRepoError(err.message);
    } finally {
      setLoadingGitHubRepos(false);
    }
  };

  const handleToggleRepoPicker = () => {
    const next = !showRepoPicker;
    setShowRepoPicker(next);
    if (next && gitHubRepos.length === 0) fetchUserRepos();
  };

  const parseOwnerRepo = (url) => {
    try {
      const clean = url.trim().replace(/\.git$/, '').replace(/\/$/, '');
      const parts = clean.split('/');
      if (parts.length >= 2) {
        return { owner: parts[parts.length - 2], repo: parts[parts.length - 1] };
      }
    } catch (e) { /* ignore */ }
    return null;
  };

  const fetchRepoManifest = async (urlToFetch) => {
    const targetUrl = urlToFetch || repoUrl;
    const parsed = parseOwnerRepo(targetUrl);
    if (!parsed) {
      push('Please enter a valid GitHub repository URL first (e.g. https://github.com/owner/repo)', 'warning');
      return;
    }

    setFetchingTree(true);
    setTreeInfo(null);
    try {
      const res = await fetch(
        `${API_BASE}/repos/github/repo-tree?owner=${encodeURIComponent(parsed.owner)}&repo=${encodeURIComponent(parsed.repo)}`,
        { headers: { 'Content-Type': 'application/json', ...getAuthHeader() } }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Failed to fetch repo tree (HTTP ${res.status})`);
      }

      const data = await res.json();
      setTreeInfo(data);

      if (data.file_list?.length > 0) setDetectedFiles(data.file_list);
      if (data.mlops_yaml_found && data.mlops_yaml_content) {
        setYamlContent(data.mlops_yaml_content);
        push('mlops.yaml loaded from repository.', 'success');
      } else {
        push('No mlops.yaml found — starter template loaded. Edit before connecting.', 'info');
      }
    } catch (err) {
      push(`Could not fetch repo tree: ${err.message}`, 'error');
    } finally {
      setFetchingTree(false);
    }
  };

  const handleSelectRepo = (r) => {
    setRepoUrl(r.html_url);
    setShowRepoPicker(false);
    fetchRepoManifest(r.html_url);
  };

  const handleConnect = async (e) => {
    e.preventDefault();
    setLoading(true);
    setValidationErrors([]);
    setSuccessInfo(null);

    const parsed = parseOwnerRepo(repoUrl);
    try {
      const res = await fetch(`${API_BASE}/repos/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          github_url: repoUrl,
          owner: parsed?.owner,
          yaml_content: yamlContent,
          repo_file_list: detectedFiles
        })
      });

      const data = await res.json();

      if (res.status === 422) {
        const errs = data.detail?.errors || [data.detail?.message || 'Validation error'];
        setValidationErrors(errs);
      } else if (!res.ok) {
        setValidationErrors([data.detail || `Server error: HTTP ${res.status}`]);
      } else {
        setSuccessInfo(data);
        if (onRepoConnected) setTimeout(() => onRepoConnected(data.repo_id), 1200);
      }
    } catch (err) {
      setValidationErrors([`Network connection failure: ${err.message}`]);
    } finally {
      setLoading(false);
    }
  };

  const filteredRepos = gitHubRepos.filter((r) =>
    (r.full_name || r.name || '').toLowerCase().includes(repoSearch.toLowerCase())
  );

  return (
    <div style={{ maxWidth: '820px', margin: '0 auto' }}>
      <div className="card">
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div className="card-header">
          <div>
            <div className="section-title">Connect GitHub Repository</div>
            <div className="section-sub">AutoMLOps validates your manifest and configures self-hosted CI/CD pipelines.</div>
          </div>
          <div className="action-group">
            <button
              type="button"
              className={`btn btn-sm ${showRepoPicker ? 'btn-primary' : 'btn-secondary'}`}
              onClick={handleToggleRepoPicker}
            >
              <IconSearch />
              {showRepoPicker ? 'Close Browser' : 'Browse Repos'}
            </button>
            {onCancel && (
              <button className="btn btn-secondary btn-sm" onClick={onCancel}>Back</button>
            )}
          </div>
        </div>

        {/* ── Repo Picker ──────────────────────────────────────────────────── */}
        {showRepoPicker && (
          <div className="repo-picker">
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'0.75rem' }}>
              <div style={{ fontSize:'0.85rem', fontWeight:600, color:'var(--cyan)' }}>
                Your GitHub Repositories
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={fetchUserRepos}
                disabled={loadingGitHubRepos}
              >
                <IconRefresh />
                {loadingGitHubRepos ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>

            <input
              type="text"
              placeholder="Search repositories…"
              value={repoSearch}
              onChange={(e) => setRepoSearch(e.target.value)}
              style={{ marginBottom:'0.75rem', fontSize:'0.85rem' }}
            />

            {loadingGitHubRepos ? (
              <div style={{ textAlign:'center', padding:'1.5rem', color:'var(--text-2)', fontSize:'0.85rem' }}>
                Fetching repositories from GitHub API…
              </div>
            ) : gitHubRepoError ? (
              <div className="banner banner-error" style={{ marginBottom:0 }}>
                <svg viewBox="0 0 20 20" fill="currentColor" className="banner-icon">
                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd"/>
                </svg>
                <div className="banner-body">
                  <div className="banner-desc">{gitHubRepoError}. Ensure a GitHub token is configured or sign in via GitHub App.</div>
                </div>
              </div>
            ) : filteredRepos.length === 0 ? (
              <div style={{ textAlign:'center', padding:'1rem', color:'var(--text-3)', fontSize:'0.85rem' }}>
                No repositories matched your filter.
              </div>
            ) : (
              <div className="repo-picker-list">
                {filteredRepos.map((r) => (
                  <div key={r.full_name} className="repo-picker-item" onClick={() => handleSelectRepo(r)}>
                    <div>
                      <div style={{ fontWeight:600, fontSize:'0.85rem', display:'flex', alignItems:'center', gap:'0.4rem' }}>
                        {r.full_name}
                        {r.private && (
                          <span style={{ fontSize:'0.7rem', color:'var(--yellow)', display:'flex', alignItems:'center', gap:'0.2rem' }}>
                            <IconLock /> private
                          </span>
                        )}
                      </div>
                      {r.description && (
                        <div style={{ fontSize:'0.75rem', color:'var(--text-2)', marginTop:'0.15rem' }}>{r.description}</div>
                      )}
                    </div>
                    {r.language && (
                      <span className="badge badge-info" style={{ whiteSpace:'nowrap' }}>{r.language}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Validation errors ────────────────────────────────────────────── */}
        {validationErrors.length > 0 && (
          <div className="banner banner-error" style={{ marginBottom:'1.25rem' }}>
            <svg viewBox="0 0 20 20" fill="currentColor" className="banner-icon">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd"/>
            </svg>
            <div className="banner-body">
              <div className="banner-title">Manifest / Repository Validation Errors</div>
              <ul style={{ paddingLeft:'1.25rem', marginTop:'0.4rem', color:'var(--red-light)' }}>
                {validationErrors.map((err, idx) => (
                  <li key={idx} style={{ fontSize:'0.84rem', marginBottom:'0.2rem' }}>{err}</li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* ── Success banner ───────────────────────────────────────────────── */}
        {successInfo && (
          <div className="banner banner-success" style={{ marginBottom:'1.25rem' }}>
            <svg viewBox="0 0 20 20" fill="currentColor" className="banner-icon">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd"/>
            </svg>
            <div className="banner-body">
              <div className="banner-title">{successInfo.message}</div>
              <div className="banner-desc">Assigned serving port: <code>{successInfo.assigned_port}</code>. Redirecting to dashboard…</div>
            </div>
          </div>
        )}

        {/* ── Repo scan result banner ──────────────────────────────────────── */}
        {treeInfo && (
          <div className={`banner ${treeInfo.mlops_yaml_found ? 'banner-info' : 'banner-warning'}`} style={{ marginBottom:'1.25rem' }}>
            <svg viewBox="0 0 20 20" fill="currentColor" className="banner-icon">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd"/>
            </svg>
            <div className="banner-body">
              <div className="banner-title">
                {treeInfo.mlops_yaml_found
                  ? `mlops.yaml auto-detected in ${treeInfo.owner}/${treeInfo.repo}`
                  : `No mlops.yaml found in ${treeInfo.owner}/${treeInfo.repo}`}
              </div>
              <div className="banner-desc">
                {treeInfo.mlops_yaml_found
                  ? 'Manifest loaded into the editor below.'
                  : 'Using starter template — edit before connecting.'}
                {' '}Detected {treeInfo.file_count} files on branch <code>{treeInfo.default_branch}</code>.
              </div>
            </div>
            <span className="badge badge-info" style={{ whiteSpace:'nowrap', alignSelf:'flex-start' }}>
              {detectedFiles.length} files
            </span>
          </div>
        )}

        {/* ── Form ─────────────────────────────────────────────────────────── */}
        <form onSubmit={handleConnect}>
          <div className="form-group">
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'0.4rem' }}>
              <label htmlFor="repo-url" style={{ marginBottom:0 }}>Repository GitHub URL</label>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => fetchRepoManifest()}
                disabled={fetchingTree}
              >
                <IconDownload />
                {fetchingTree ? 'Fetching…' : 'Fetch mlops.yaml'}
              </button>
            </div>
            <input
              id="repo-url"
              type="url"
              required
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/organization/repo-name"
            />
          </div>

          <div className="form-group">
            <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'0.4rem' }}>
              <label htmlFor="mlops-yaml" style={{ marginBottom:0 }}>
                Manifest <code style={{ fontWeight:400 }}>(mlops.yaml schema)</code>
              </label>
              <span style={{ fontSize:'0.75rem', color:'var(--text-3)' }}>Task-type &amp; metrics contract</span>
            </div>
            <textarea
              id="mlops-yaml"
              rows={12}
              style={{ fontFamily:'JetBrains Mono, monospace', fontSize:'0.83rem' }}
              value={yamlContent}
              onChange={(e) => setYamlContent(e.target.value)}
            />
          </div>

          <div style={{ display:'flex', gap:'0.75rem', justifyContent:'flex-end' }}>
            {onCancel && (
              <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
            )}
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? 'Validating & Connecting…' : 'Validate & Connect Repo'}
            </button>
          </div>
        </form>
      </div>

      <ToastStack toasts={toasts} dismiss={dismiss} />
    </div>
  );
}
