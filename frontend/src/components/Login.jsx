import React, { useState } from 'react';

export default function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('joel-developer');
  const [loading, setLoading] = useState(false);

  const handleGitHubLogin = () => {
    setLoading(true);
    // Simulate GitHub App OAuth session token
    setTimeout(() => {
      const user = {
        username: username,
        token: `gho_automlops_${Date.now()}`,
        avatar: `https://github.com/${username}.png`
      };
      localStorage.setItem('automlops_user', JSON.stringify(user));
      setLoading(false);
      onLoginSuccess(user);
    }, 600);
  };

  return (
    <div style={{ maxWidth: '440px', margin: '4rem auto' }}>
      <div className="card" style={{ textAlign: 'center', padding: '2.5rem 2rem' }}>
        <div className="brand-logo" style={{ width: '56px', height: '56px', margin: '0 auto 1.5rem', fontSize: '1.5rem' }}>
          AO
        </div>
        <h2 style={{ fontSize: '1.5rem', marginBottom: '0.5rem', fontWeight: 700 }}>
          Welcome to AutoMLOps
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginBottom: '2rem' }}>
          Autonomous CI/CD, Quality Gating, and Drift Retraining Engine
        </p>

        <div style={{ marginBottom: '1.5rem', textAlign: 'left' }}>
          <label htmlFor="gh-user">GitHub Account / Handle</label>
          <input
            id="gh-user"
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="e.g. joel-95"
          />
        </div>

        <button
          className="btn btn-primary"
          style={{ width: '100%', padding: '0.8rem', fontSize: '1rem' }}
          onClick={handleGitHubLogin}
          disabled={loading}
        >
          {loading ? 'Authenticating with GitHub App...' : 'Sign in with GitHub'}
        </button>

        <p style={{ marginTop: '1.5rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          Self-hosted on RTX 3050 Runner • GitHub App OAuth Secured
        </p>
      </div>
    </div>
  );
}
