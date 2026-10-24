import React, { useState, useEffect } from 'react';
import Login from './components/Login.jsx';
import ConnectRepo from './components/ConnectRepo.jsx';
import StatusPage from './components/StatusPage.jsx';
import { useToast, ToastStack } from './components/Toast.jsx';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

/* SVG icons used in the navbar */
const IconGrid = () => (
  <svg width="15" height="15" viewBox="0 0 20 20" fill="currentColor">
    <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM11 13a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/>
  </svg>
);

const IconPlus = () => (
  <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd"/>
  </svg>
);

const IconLogout = () => (
  <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M3 3a1 1 0 00-1 1v12a1 1 0 102 0V4a1 1 0 00-1-1zm10.293 9.293a1 1 0 001.414 1.414l3-3a1 1 0 000-1.414l-3-3a1 1 0 10-1.414 1.414L14.586 9H7a1 1 0 100 2h7.586l-1.293 1.293z" clipRule="evenodd"/>
  </svg>
);

const IconGitHub = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
  </svg>
);

const IconTrash = () => (
  <svg width="13" height="13" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd"/>
  </svg>
);

export default function App() {
  const { toasts, push, dismiss } = useToast();

  const [user, setUser] = useState(() => {
    const saved = localStorage.getItem('automlops_user');
    return saved ? JSON.parse(saved) : null;
  });

  const [currentView, setCurrentView] = useState('list');
  const [selectedRepoId, setSelectedRepoId] = useState(null);
  const [repos, setRepos] = useState([]);
  const [loadingRepos, setLoadingRepos] = useState(false);
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    if (code) {
      setAuthLoading(true);
      setAuthError(null);
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
        .finally(() => setAuthLoading(false));
    }
  }, []);

  const fetchRepos = async () => {
    try {
      setLoadingRepos(true);
      const res = await fetch(`${API_BASE}/repos`);
      if (res.ok) setRepos(await res.json());
    } catch (err) {
      console.error('Error fetching repos:', err);
    } finally {
      setLoadingRepos(false);
    }
  };

  useEffect(() => { if (user) fetchRepos(); }, [user]);

  const handleLogout = () => {
    localStorage.removeItem('automlops_user');
    setUser(null);
    setCurrentView('list');
  };

  const handleSelectRepo    = (id) => { setSelectedRepoId(id); setCurrentView('status'); };
  const handleRepoConnected = (id) => { fetchRepos(); setSelectedRepoId(id); setCurrentView('status'); };

  const handleDeleteRepo = async (e, repoId) => {
    e.stopPropagation();
    if (!window.confirm(`Disconnect and stop deployment for '${repoId}'?`)) return;
    try {
      await fetch(`${API_BASE}/repos/${repoId}`, { method: 'DELETE' });
      fetchRepos();
      if (selectedRepoId === repoId) setCurrentView('list');
    } catch (err) {
      push(`Failed to disconnect repo: ${err.message}`, 'error');
    }
  };

  if (authLoading) {
    return (
      <div className="loading-state">
        <div className="loading-spinner" />
        <div className="loading-state-title">Authenticating with GitHub</div>
        <div className="loading-state-sub">Exchanging authorization token and verifying identity</div>
      </div>
    );
  }

  if (!user) {
    return <Login onLoginSuccess={(u) => setUser(u)} authError={authError} />;
  }

  return (
    <div className="app-container">
      <header className="navbar">
        <div className="brand" onClick={() => setCurrentView('list')}>
          <div className="brand-logo">AO</div>
          <div>
            <div className="brand-title">AutoMLOps</div>
            <div className="brand-sub">Self-hosted ML Lifecycle</div>
          </div>
        </div>

        <nav className="nav-links">
          <button
            className={`btn btn-sm ${currentView === 'list' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => { setCurrentView('list'); fetchRepos(); }}
          >
            <IconGrid />
            Repositories
            <span style={{ opacity: 0.65, fontWeight: 500 }}>({repos.length})</span>
          </button>
          <button
            className={`btn btn-sm ${currentView === 'connect' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setCurrentView('connect')}
          >
            <IconPlus />
            Connect Repo
          </button>

          <div className="nav-divider" />

          <div className="nav-user">
            {user.avatar_url
              ? <img src={user.avatar_url} alt={user.username} className="nav-avatar" />
              : <div style={{ width:30, height:30, borderRadius:'50%', background:'var(--bg-card)', border:'1px solid var(--border-md)', display:'flex', alignItems:'center', justifyContent:'center' }}><IconGitHub/></div>
            }
            <span className="nav-username">{user.name || user.username}</span>
            <button className="btn btn-ghost btn-sm" onClick={handleLogout} title="Sign out">
              <IconLogout />
            </button>
          </div>
        </nav>
      </header>

      <main>
        {currentView === 'connect' && (
          <ConnectRepo onRepoConnected={handleRepoConnected} onCancel={() => setCurrentView('list')} />
        )}

        {currentView === 'status' && selectedRepoId && (
          <div>
            <button className="back-link" onClick={() => setCurrentView('list')}>
              <svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z" clipRule="evenodd"/>
              </svg>
              All Repositories
            </button>
            <StatusPage repoId={selectedRepoId} onBackToList={() => setCurrentView('list')} />
          </div>
        )}

        {currentView === 'list' && (
          <div>
            <div className="page-header">
              <div className="page-header-text">
                <h2>Connected Repositories</h2>
                <p>Manage active ML projects, deployments, and production monitoring loops.</p>
              </div>
              <div className="page-header-actions">
                <button className="btn btn-primary" onClick={() => setCurrentView('connect')}>
                  <IconPlus />
                  Connect Repo
                </button>
              </div>
            </div>

            {loadingRepos && repos.length === 0 ? (
              <div className="loading-state" style={{ padding: '3rem' }}>
                <div className="loading-spinner" />
                <div className="loading-state-sub">Loading connected repositories…</div>
              </div>
            ) : repos.length === 0 ? (
              <div className="card">
                <div className="empty-state">
                  <svg className="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"/>
                  </svg>
                  <h3>No Repositories Connected</h3>
                  <p>Connect your first GitHub ML repository to start automating training, quality gating, and deployment.</p>
                  <button className="btn btn-primary" onClick={() => setCurrentView('connect')}>
                    <IconPlus />
                    Connect Your First Repo
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid-2">
                {repos.map((r) => (
                  <div key={r.id} className="card repo-card" onClick={() => handleSelectRepo(r.id)}>
                    <div className="repo-card-header">
                      <div className="repo-card-name">{r.repo_name}</div>
                      <button
                        className="btn btn-danger btn-sm btn-icon"
                        title="Disconnect repository"
                        onClick={(e) => handleDeleteRepo(e, r.id)}
                      >
                        <IconTrash />
                      </button>
                    </div>

                    <div className="repo-card-badges">
                      <span className={`badge badge-${r.latest_run_status}`}>
                        Pipeline: {r.latest_run_status}
                      </span>
                      <span className={`badge ${r.is_deployed ? 'badge-active' : 'badge-warning'}`}>
                        {r.is_deployed ? `Port ${r.port}` : 'Not Deployed'}
                      </span>
                    </div>

                    <div className="repo-card-meta">
                      <div>
                        GitHub: <span>{r.github_url}</span>
                      </div>
                      {r.tunnel_url && (
                        <div style={{ marginTop: '0.2rem' }}>
                          Live: <code>{r.tunnel_url}</code>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </main>

      <ToastStack toasts={toasts} dismiss={dismiss} />
    </div>
  );
}
