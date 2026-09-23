import React, { useState } from 'react';
import { Lock, User, Shield, ArrowRight, Eye, EyeOff } from 'lucide-react';
import { authApi } from '../services/api';
import './LoginScreen.css';

export default function LoginScreen({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username || !password) {
      setError('Please enter both username and password.');
      return;
    }

    setLoading(true);
    setError('');

    try {
      // Hit the real FastAPI OAuth2 backend
      const response = await authApi.login(username, password);
      
      // Store the real cryptographically signed JWT
      sessionStorage.setItem('fin_mind_token', response.access_token);
      
      // We can decode the role from the token, but for now we just pass a success signal.
      // The backend will enforce permissions regardless of what the frontend thinks.
      // Let's decode the token payload minimally to get the role for UI rendering.
      const payloadBase64 = response.access_token.split('.')[1];
      const decodedPayload = JSON.parse(atob(payloadBase64));
      
      onLogin(decodedPayload.role || 'VIEWER');
    } catch (err) {
      setError(err.message || 'Invalid username or password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-box glass-panel animate-fade-in">
        <div className="login-header">
          <Shield className="login-icon" size={32} />
          <h1>Fin Mind</h1>
          <p className="login-subtitle">Secure Intelligence Platform</p>
        </div>

        {error && <div className="login-error">{error}</div>}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="input-group">
            <User size={18} className="input-icon" />
            <input 
              type="text" 
              placeholder="Username" 
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
            />
          </div>

          <div className="input-group">
            <Lock size={18} className="input-icon" />
            <input 
              type={showPassword ? "text" : "password"} 
              placeholder="Password" 
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              style={{ paddingRight: '40px' }}
            />
            <button 
              type="button" 
              className="password-toggle"
              onClick={() => setShowPassword(!showPassword)}
              style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: 'var(--color-text-muted)', cursor: 'pointer' }}
            >
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>

          <button type="submit" className="login-button" disabled={loading}>
            <span>{loading ? 'Authenticating...' : 'Authenticate'}</span>
            {!loading && <ArrowRight size={18} />}
          </button>
        </form>
      </div>
    </div>
  );
}
