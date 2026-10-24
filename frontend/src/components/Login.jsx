import React, { useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const GitHubIcon = () => (
  <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
    <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
  </svg>
);

const BoltIcon = () => (
  <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
    <path fillRule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clipRule="evenodd"/>
  </svg>
);

export default function Login({ onLoginSuccess, authError }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(authError || null);

  const handleRealGitHubLogin = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/auth/github/url`);
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Failed to fetch GitHub OAuth URL');
      }
      const data = await res.json();
      if (data.url) window.location.href = data.url;
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  const handleTokenLogin = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/auth/token-login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Token authentication failed');
      }
      onLoginSuccess(await res.json());
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  return (
    <div className="login-wrap">
      <div className="card login-card">
        <div className="brand-logo login-logo">AO</div>

        <h2 className="login-title">AutoMLOps</h2>
        <p className="login-sub">Autonomous CI/CD, quality gating, and drift monitoring for ML projects.</p>

        {error && (
          <div className="banner banner-error" style={{ marginBottom: '1.25rem', textAlign: 'left' }}>
            <svg viewBox="0 0 20 20" fill="currentColor" className="banner-icon">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd"/>
            </svg>
            <div className="banner-body">
              <div className="banner-title">Authentication failed</div>
              <div className="banner-desc">{error}</div>
            </div>
          </div>
        )}

        <div className="login-actions">
          <button
            className="btn btn-primary btn-lg"
            style={{ width: '100%', justifyContent: 'center' }}
            onClick={handleRealGitHubLogin}
            disabled={loading}
          >
            <GitHubIcon />
            {loading ? 'Connecting…' : 'Sign in with GitHub'}
          </button>

          <button
            className="btn btn-secondary btn-lg"
            style={{ width: '100%', justifyContent: 'center' }}
            onClick={handleTokenLogin}
            disabled={loading}
          >
            <BoltIcon />
            Quick sign-in (.env token)
          </button>
        </div>

        <div className="login-notice">
          <strong>GitHub App notice:</strong> If GitHub returns a 404, verify that the Callback URL is set to{' '}
          <code>http://localhost:3000</code> in your App settings, or{' '}
          <a
            href="https://github.com/apps/mlops-authentication/installations/new"
            target="_blank"
            rel="noreferrer"
          >
            install the App on your account
          </a>.
        </div>
      </div>
    </div>
  );
}
