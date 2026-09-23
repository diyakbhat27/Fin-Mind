import axios from 'axios';

// The centralized API client for the Fin Mind frontend
// Points to the FastAPI LangGraph backend
const api = axios.create({
  // Fallback to localhost if VITE_API_URL is not provided
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 60000, // 60 second timeout for slow connections
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to automatically attach the mock JWT from localStorage
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('fin_mind_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const chatApi = {
  // unified endpoint from Phase 5
  sendMessage: async (query) => {
    try {
      const response = await api.post('/api/v1/chat', { query });
      return response.data;
    } catch (error) {
      if (error.response) {
        // Return the structured error from LangGraph (e.g., RBAC 403)
        throw error.response.data;
      }
      throw new Error("Network error connecting to backend");
    }
  }
};

export const authApi = {
  login: async (username, password) => {
    const params = new URLSearchParams();
    params.append('username', username);
    params.append('password', password);
    
    try {
      const response = await api.post('/api/v1/auth/login', params, {
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded'
        }
      });
      return response.data;
    } catch (error) {
      if (error.response && error.response.data) {
        throw new Error(error.response.data.detail || "Authentication failed");
      }
      throw new Error("Network error connecting to backend");
    }
  }
};

export default api;
