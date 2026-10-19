import React, { useState, useEffect } from 'react';
import Login from './components/Login.jsx';
import ConnectRepo from './components/ConnectRepo.jsx';
import StatusPage from './components/StatusPage.jsx';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export default function App() {
  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('automlops_user');
    return saved ? JSON.parse(saved) : null;
  });

  const [currentView, setCurrentView] = useState('list'); // 'list' | 'connect' | 'status'
  const [selectedRepoId, setSelectedRepoId] = useState(null);
  const [repos, setRepos] = useState([]);
  const [loadingRepos, setLoadingRepos] = useState(false);

  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState(null);

  // Check URL query parameters for GitHub OAuth callback code
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    if (code) {
      setAuthLoading(true);
      setAuthError(null);
      // Clean query string from browser address bar
      window.history.replaceState({}, document.title, window.location.pathname);

      fetch(`${API_BASE}/auth/github/callback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      })
        .then(async (res) => {
          if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'GitHub authentication failed');
          }
          return res.json();
        })
        .then((profile) => {
          localStorage.setItem('automlops_user', JSON.stringify(profile));
          setUser(profile);
        })
        .catch((err) => {
          setAuthError(err.message);
          localStorage.removeItem('automlops_user');
          setUser(null);
        })
        .finally(() => {
          setAuthLoading(false);
        });
    }
  }, []);

  const fetchRepos = async () => {
    try {
      setLoadingRepos(true);
      const res = await fetch(`${API_BASE}/repos`);
      if (res.ok) {
        const data = await res.json();
        setRepos(data);
      }
    } catch (err) {
      console.error('Error fetching repos:', err);
    } finally {
      setLoadingRepos(false);
    }
  };

  useEffect(() => {
    if (user) {
      fetchRepos();
    }
  }, [user]);

  const handleLogout = () => {
    localStorage.removeItem('automlops_user');
    setUser(null);
    setCurrentView('list');
  };

  const handleSelectRepo = (id) => {
    setSelectedRepoId(id);
    setCurrentView('status');
  };

  const handleRepoConnected = (newRepoId) => {
    fetchRepos();
    setSelectedRepoId(newRepoId);
    setCurrentView('status');
  };

  const handleDeleteRepo = async (e, repoId) => {
    e.stopPropagation();
    if (!window.confirm(`Disconnect and stop deployment for '${repoId}'?`)) return;
    try {
      await fetch(`${API_BASE}/repos/${repoId}`, { method: 'DELETE' });
      fetchRepos();
      if (selectedRepoId === repoId) {
        setCurrentView('list');
      }
    } catch (err) {
      alert(`Failed to delete repo: ${err.message}`);
    }
  };

  if (authLoading) {
    return (
      <div style={{ textAlign: 'center', padding: '6rem 2rem' }}>
        <div style={{ color: 'var(--accent-cyan)', fontSize: '1.3rem', fontWeight: 700, marginBottom: '0.75rem' }}>
          Authenticating with GitHub App...
        </div>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Exchanging authorization token &amp; fetching your verified GitHub profile
        </p>
      </div>
    );
  }

  if (!user) {
    return <Login onLoginSuccess={(u) => setUser(u)} authError={authError} />;
  }

  return (
    <div className="app-container">
      {/* Top Navbar */}
      <header className="navbar">
        <div className="brand" onClick={() => setCurrentView('list')} style={{ cursor: 'pointer' }}>
          <div className="brand-logo">AO</div>
          <div>
            <div className="brand-title">AutoMLOps</div>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', letterSpacing: '0.05em' }}>
              SELF-HOSTED ML LIFECYCLE
            </div>
          </div>
        </div>

        <nav className="nav-links">
          <button
            className={`btn ${currentView === 'list' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => { setCurrentView('list'); fetchRepos(); }}
          >
            Connected Repos ({repos.length})
          </button>
          <button
            className={`btn ${currentView === 'connect' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setCurrentView('connect')}
          >
            + Connect Repo
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginLeft: '0.5rem' }}>
            {user.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.username}
                style={{ width: '32px', height: '32px', borderRadius: '50%', border: '1px solid var(--accent-cyan)' }}
              />
            ) : (
              <span>👤</span>
            )}
            <span style={{ fontSize: '0.85rem', color: 'var(--text-primary)', fontWeight: 600 }}>
              {user.name || user.username}
            </span>
            <button
              className="btn btn-secondary"
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.75rem' }}
              onClick={handleLogout}
            >
              Sign Out
            </button>
          </div>
        </nav>
      </header>

      {/* Main View Router */}
      <main>
        {currentView === 'connect' && (
          <ConnectRepo
            onRepoConnected={handleRepoConnected}
            onCancel={() => setCurrentView('list')}
          />
        )}

        {currentView === 'status' && selectedRepoId && (
          <div>
            <div style={{ marginBottom: '1rem' }}>
              <button
                className="btn btn-secondary"
                style={{ fontSize: '0.8rem', padding: '0.4rem 0.8rem' }}
                onClick={() => setCurrentView('list')}
              >
                ← Back to All Repositories
              </button>
            </div>
            <StatusPage repoId={selectedRepoId} onBackToList={() => setCurrentView('list')} />
          </div>
        )}

        {currentView === 'list' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
              <div>
                <h2 style={{ fontSize: '1.4rem', fontWeight: 700 }}>Connected Repositories</h2>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                  Manage active ML projects, deployments, and production monitoring loops.
                </p>
              </div>
              <button className="btn btn-primary" onClick={() => setCurrentView('connect')}>
                + Connect New Repo
              </button>
            </div>

            {loadingRepos && repos.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)' }}>
                Loading connected repositories...
              </div>
            ) : repos.length === 0 ? (
              <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
                <h3 style={{ marginBottom: '0.5rem', color: 'var(--text-primary)' }}>No Repositories Connected Yet</h3>
                <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
                  Connect your first GitHub machine learning repo to generate CI/CD workflows and self-hosted GPU pipelines.
                </p>
                <button className="btn btn-primary" onClick={() => setCurrentView('connect')}>
                  Connect Reference Demo Repo
                </button>
              </div>
            ) : (
              <div className="grid-2">
                {repos.map((r) => (
                  <div
                    key={r.id}
                    className="card"
                    style={{ cursor: 'pointer', position: 'relative' }}
                    onClick={() => handleSelectRepo(r.id)}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.75rem' }}>
                      <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: '#f8fafc' }}>
                        {r.repo_name}
                      </h3>
                      <button
                        className="btn btn-danger"
                        style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem' }}
                        title="Disconnect repository"
                        onClick={(e) => handleDeleteRepo(e, r.id)}
                      >
                        ✕
                      </button>
                    </div>

                    <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
                      <span className={`badge badge-${r.latest_run_status}`}>
                        Pipeline: {r.latest_run_status}
                      </span>
                      <span className={`badge ${r.is_deployed ? 'badge-active' : 'badge-warning'}`}>
                        {r.is_deployed ? `Port ${r.port}` : 'Not Deployed'}
                      </span>
                    </div>

                    <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                      GitHub: <span style={{ color: 'var(--accent-cyan)' }}>{r.github_url}</span>
                    </div>
                    {r.tunnel_url && (
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                        Live URL: <code style={{ color: '#34d399' }}>{r.tunnel_url}</code>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
