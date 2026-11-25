import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
const TOKEN_KEY = 'rsd_token';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Attach token to every request
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401, clear token and dispatch logout event
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_KEY);
      window.dispatchEvent(new Event('rsd:auth:logout'));
    }
    return Promise.reject(error);
  }
);

export const authAPI = {
  register: (data) => apiClient.post('/auth/register', data),
  loginJson: (data) => apiClient.post('/auth/login/json', data),
  getMe: () => apiClient.get('/auth/me'),
};

export const riskAPI = {
  createAssessment: (data) => apiClient.post('/risk/assess', data),
  getAssessment: (id) => apiClient.get(`/risk/assess/${id}`),
  listAssessments: (skip = 0, limit = 100) => apiClient.get(`/risk/assessments?skip=${skip}&limit=${limit}`),
  detectAnomalies: (assessmentId) => apiClient.post(`/risk/anomaly/${assessmentId}`),
  predict: (assessmentId) => apiClient.post(`/risk/predict/${assessmentId}`),
  // Latest stored prediction (404 if none yet) — does not run the model.
  getPrediction: (assessmentId) => apiClient.get(`/risk/predict/${assessmentId}`),
  // What-If: score edited answers against this assessment; nothing is saved.
  simulate: (assessmentId, scenario) => apiClient.post(`/risk/assess/${assessmentId}/simulate`, scenario),
  // Token goes in the Authorization header (via interceptor), never the URL.
  downloadReport: (assessmentId) =>
    apiClient.get(`/risk/assess/${assessmentId}/report`, { responseType: 'blob' }),
};

export const health = () => apiClient.get('/');
export default apiClient;

/**
 * Human-readable message from an API error.
 * FastAPI returns `detail` as a string for HTTPException but as a list of
 * {loc, msg} objects for 422 validation errors; rendering that list directly
 * would crash React.
 */
export function errorMessage(err, fallback = 'Something went wrong') {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d) => {
        const field = d?.loc?.[d.loc.length - 1];
        const label = typeof field === 'string' ? field.replace(/_/g, ' ') : null;
        return label ? `${label}: ${d.msg}` : d?.msg;
      })
      .filter(Boolean)
      .join('; ') || fallback;
  }
  return fallback;
}
