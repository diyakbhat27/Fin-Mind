import React, { useState, useEffect } from 'react';
import LoginScreen from './components/LoginScreen';
import ChatInterface from './components/ChatInterface';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [userRole, setUserRole] = useState(null);

  useEffect(() => {
    // Check if token exists on load
    const token = sessionStorage.getItem('fin_mind_token');
    if (token) {
      try {
        // Decode mock JWT payload
        const payload = JSON.parse(atob(token.split('.')[1]));
        if (payload.exp * 1000 > Date.now()) {
          setIsAuthenticated(true);
          setUserRole(payload.role);
        } else {
          sessionStorage.removeItem('fin_mind_token');
        }
      } catch (e) {
        sessionStorage.removeItem('fin_mind_token');
      }
    }
  }, []);

  const handleLogin = (role) => {
    setIsAuthenticated(true);
    setUserRole(role);
  };

  const handleLogout = () => {
    sessionStorage.removeItem('fin_mind_token');
    setIsAuthenticated(false);
    setUserRole(null);
  };

  const [theme, setTheme] = useState('dark');

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark');
  };

  return (
    <div className={`app-container ${theme}-theme`}>
      <button 
        onClick={toggleTheme} 
        style={{
          position: 'absolute', top: '16px', right: isAuthenticated ? '80px' : '24px', zIndex: 1000,
          background: 'rgba(255, 255, 255, 0.1)', border: '1px solid rgba(255, 255, 255, 0.2)',
          padding: '8px 12px', borderRadius: '20px', color: 'var(--text-primary)',
          cursor: 'pointer', backdropFilter: 'blur(10px)', display: 'flex', alignItems: 'center', gap: '8px'
        }}
      >
        {theme === 'dark' ? '☀️ Light Mode' : '🌙 Dark Mode'}
      </button>

      {!isAuthenticated ? (
        <LoginScreen onLogin={handleLogin} />
      ) : (
        <ChatInterface role={userRole} onLogout={handleLogout} />
      )}
    </div>
  );
}

export default App;
