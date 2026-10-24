import React, { useState, useEffect } from 'react';

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

  // GitHub Repo Browser State
  const [showRepoPicker, setShowRepoPicker] = useState(false);
  const [gitHubRepos, setGitHubRepos] = useState([]);
  const [loadingGitHubRepos, setLoadingGitHubRepos] = useState(false);
  const [gitHubRepoError, setGitHubRepoError] = useState(null);
  const [repoSearch, setRepoSearch] = useState('');

  // Repo Tree & mlops.yaml fetch state
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
    } catch (e) {
      // ignore
    }
    return {};
  };

  const fetchUserRepos = async () => {
    setLoadingGitHubRepos(true);
    setGitHubRepoError(null);
    try {
      const res = await fetch(`${API_BASE}/repos/github/user-repos`, {
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader()
        }
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `GitHub API error (HTTP ${res.status})`);
      }
      const data = await res.json();
      setGitHubRepos(data);
    } catch (err) {
      setGitHubRepoError(err.message);
    } finally {
      setLoadingGitHubRepos(false);
    }
  };

  const handleToggleRepoPicker = () => {
    const next = !showRepoPicker;
    setShowRepoPicker(next);
    if (next && gitHubRepos.length === 0) {
      fetchUserRepos();
    }
  };

  const parseOwnerRepo = (url) => {
    try {
      const clean = url.trim().replace(/\.git$/, '').replace(/\/$/, '');
      const parts = clean.split('/');
      if (parts.length >= 2) {
        const repo = parts[parts.length - 1];
        const owner = parts[parts.length - 2];
        return { owner, repo };
      }
    } catch (e) {
      // ignore
    }
    return null;
  };

  const fetchRepoManifest = async (urlToFetch) => {
    const targetUrl = urlToFetch || repoUrl;
    const parsed = parseOwnerRepo(targetUrl);
    if (!parsed) {
      alert('Please enter a valid GitHub repository URL first (e.g. https://github.com/owner/repo)');
      return;
    }

    setFetchingTree(true);
    setTreeInfo(null);
    try {
      const res = await fetch(
        `${API_BASE}/repos/github/repo-tree?owner=${encodeURIComponent(parsed.owner)}&repo=${encodeURIComponent(parsed.repo)}`,
        {
          headers: {
            'Content-Type': 'application/json',
            ...getAuthHeader()
          }
        }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Failed to fetch repo tree (HTTP ${res.status})`);
      }

      const data = await res.json();
      setTreeInfo(data);

      if (data.file_list && data.file_list.length > 0) {
        setDetectedFiles(data.file_list);
      }

      if (data.mlops_yaml_found && data.mlops_yaml_content) {
        setYamlContent(data.mlops_yaml_content);
      }
    } catch (err) {
      alert(`Could not fetch repo tree: ${err.message}`);
    } finally {
      setFetchingTree(false);
    }
  };

  const handleSelectRepo = (r) => {
    setRepoUrl(r.html_url);
    setShowRepoPicker(false);
    // Automatically fetch tree and mlops.yaml for the selected repo
    fetchRepoManifest(r.html_url);
  };

  const handleConnect = async (e) => {
    e.preventDefault();
    setLoading(true);
    setValidationErrors([]);
    setSuccessInfo(null);

    const parsed = parseOwnerRepo(repoUrl);
    const owner = parsed ? parsed.owner : undefined;

    try {
      const res = await fetch(`${API_BASE}/repos/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          github_url: repoUrl,
          owner: owner,
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

  const filteredRepos = gitHubRepos.filter((r) =>
    (r.full_name || r.name || '').toLowerCase().includes(repoSearch.toLowerCase())
  );

  return (
    <div style={{ maxWidth: '820px', margin: '0 auto' }}>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <div>
            <h2 style={{ fontSize: '1.35rem', fontWeight: 700 }}>Connect GitHub Repository</h2>
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
              AutoMLOps will validate your manifest and configure self-hosted GPU CI/CD.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              type="button"
              className={`btn ${showRepoPicker ? 'btn-primary' : 'btn-secondary'}`}
              onClick={handleToggleRepoPicker}
              style={{ fontSize: '0.8rem', padding: '0.45rem 0.85rem' }}
            >
              {showRepoPicker ? 'Close Repo Browser' : '🔍 Browse GitHub Repos'}
            </button>
            {onCancel && (
              <button className="btn btn-secondary" onClick={onCancel} style={{ fontSize: '0.8rem' }}>
                Back
              </button>
            )}
          </div>
        </div>

        {/* GitHub Repos Browser Modal / Drawer */}
        {showRepoPicker && (
          <div
            style={{
              background: 'rgba(10, 18, 36, 0.95)',
              border: '1px solid rgba(56, 189, 248, 0.3)',
              borderRadius: 'var(--radius-md)',
              padding: '1.25rem',
              marginBottom: '1.5rem',
              backdropFilter: 'blur(8px)'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--accent-cyan)' }}>
                Select from Your GitHub Repositories
              </h4>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}
                onClick={fetchUserRepos}
                disabled={loadingGitHubRepos}
              >
                {loadingGitHubRepos ? 'Refreshing...' : '🔄 Refresh'}
              </button>
            </div>

            <input
              type="text"
              placeholder="Search repositories..."
              value={repoSearch}
              onChange={(e) => setRepoSearch(e.target.value)}
              style={{ marginBottom: '0.75rem', fontSize: '0.85rem', padding: '0.5rem 0.75rem' }}
            />

            {loadingGitHubRepos ? (
              <div style={{ textAlign: 'center', padding: '1.5rem', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                Fetching your repositories from GitHub API...
              </div>
            ) : gitHubRepoError ? (
              <div style={{ padding: '0.75rem', color: '#f87171', fontSize: '0.8rem', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '6px' }}>
                ⚠️ {gitHubRepoError}. (Ensure a GitHub token is configured or sign in via GitHub App)
              </div>
            ) : filteredRepos.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                No repositories matched your filter.
              </div>
            ) : (
              <div style={{ maxHeight: '220px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                {filteredRepos.map((r) => (
                  <div
                    key={r.full_name}
                    onClick={() => handleSelectRepo(r)}
                    style={{
                      padding: '0.6rem 0.85rem',
                      background: 'rgba(255, 255, 255, 0.03)',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      border: '1px solid transparent',
                      transition: 'all 0.15s ease',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = 'var(--accent-cyan)';
                      e.currentTarget.style.background = 'rgba(56, 189, 248, 0.08)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = 'transparent';
                      e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', color: '#f8fafc' }}>
                        {r.full_name} {r.private && <span style={{ fontSize: '0.7rem', color: '#fbbf24' }}>🔒 private</span>}
                      </div>
                      {r.description && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.15rem' }}>
                          {r.description}
                        </div>
                      )}
                    </div>
                    {r.language && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--accent-cyan)', background: 'rgba(56, 189, 248, 0.1)', padding: '0.15rem 0.5rem', borderRadius: '4px' }}>
                        {r.language}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

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

        {treeInfo && (
          <div style={{
            background: treeInfo.mlops_yaml_found ? 'rgba(56, 189, 248, 0.12)' : 'rgba(245, 158, 11, 0.12)',
            border: `1px solid ${treeInfo.mlops_yaml_found ? 'rgba(56, 189, 248, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
            borderRadius: 'var(--radius-md)',
            padding: '0.85rem 1rem',
            marginBottom: '1.25rem',
            fontSize: '0.85rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center'
          }}>
            <div>
              {treeInfo.mlops_yaml_found ? (
                <span style={{ color: '#38bdf8' }}>
                  📄 <strong>mlops.yaml auto-detected</strong> from <code>{treeInfo.owner}/{treeInfo.repo}</code> and loaded into editor below!
                </span>
              ) : (
                <span style={{ color: '#fbbf24' }}>
                  ℹ️ No <code>mlops.yaml</code> found in <code>{treeInfo.owner}/{treeInfo.repo}</code>. Starter template provided below — edit and connect to generate CI/CD.
                </span>
              )}
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                Detected {treeInfo.file_count} files on branch <code>{treeInfo.default_branch}</code>
              </div>
            </div>
            <span className="badge badge-info" style={{ whiteSpace: 'nowrap' }}>
              {detectedFiles.length} files scanned
            </span>
          </div>
        )}

        <form onSubmit={handleConnect}>
          <div style={{ marginBottom: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <label htmlFor="repo-url" style={{ marginBottom: 0 }}>Repository GitHub URL</label>
              <button
                type="button"
                className="btn btn-secondary"
                style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}
                onClick={() => fetchRepoManifest()}
                disabled={fetchingTree}
              >
                {fetchingTree ? 'Fetching Manifest...' : '📥 Fetch mlops.yaml from Repo'}
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
