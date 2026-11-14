import axios from 'axios';

// Its important to do it through nginx (frontend container) API Available on a Relative Way `/api`.
// If you leave the default. `http://localhost:8000`, in the user browser. "localhost" Itll be his PC, not his server.
const API_URL = import.meta.env.VITE_API_URL || import.meta.env.REACT_APP_API_URL || '';

const apiClient = axios.create({
  baseURL: API_URL ? `${API_URL}/api` : '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
    console.log(`[API] Request ${config.url} with current: ${token.substring(0, 20)}...`);
  } else {
    console.warn(`[API] Request ${config.url} Free of electron`);
  }
  return config;
});

apiClient.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error?.response?.status === 401) {
      console.error('401 Unauthorized - No or no current');
      console.error('Response:', error?.response?.data);
      localStorage.removeItem('access_token');
      // Rerouted to a page is logical only if it is not a request for logic
      if (!error.config?.url?.includes('/auth/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export const login = async ({ username, password }) => {
  try {
    const response = await apiClient.post('/auth/login', { username, password });
    if (response.data?.access_token) {
      localStorage.setItem('access_token', response.data.access_token);
    }
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: 'Error of entrance' };
  }
};

export const searchCases = async (searchParams) => {
  try {
    const response = await apiClient.post('/search', searchParams);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: 'Error in fulfilling the request' };
  }
};

export const getSearchStatus = async (taskId) => {
  try {
    const response = await apiClient.get(`/search/status/${taskId}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: 'Error in obtaining status' };
  }
};

export const getSearchResults = async (taskId) => {
  try {
    const response = await apiClient.get(`/search/results/${taskId}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: 'Error in obtaining results' };
  }
};

export const exportResults = async (taskId, format) => {
  try {
    const response = await apiClient.get(`/export/${taskId}`, {
      params: { format },
      responseType: 'blob',
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: 'Errors in Export' };
  }
};

export const downloadAllActs = async (taskId) => {
  try {
    const response = await apiClient.get(`/acts/download_all/${taskId}`, {
      responseType: 'blob',
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: 'Error in downloading files' };
  }
};

export const clearDatabase = async ({ scope = 'all', task_id = null, include_search_logs = true }) => {
  try {
    console.log('[clearDatabase] Request for base clean-up:', { scope, task_id, include_search_logs });
    const token = localStorage.getItem('access_token');
    console.log('[clearDatabase] Token in localStorage:', token ? `${token.substring(0, 20)}...` : 'EXISTING');
    const response = await apiClient.post('/admin/clear', {
      scope,
      task_id,
      include_search_logs,
    });
    console.log('[clearDatabase] Successful response:', response.data);
    return response.data;
  } catch (error) {
    console.error('[clearDatabase] mistake:', error);
    console.error('[clearDatabase] Response:', error.response?.data);
    throw error.response?.data || { error: 'Errors in cleaning the base' };
  }
};

export const clearCache = async () => {
  try {
    console.log('[clearCache] Send a request for cache cleaning');
    const token = localStorage.getItem('access_token');
    console.log('[clearCache] Token in localStorage:', token ? `${token.substring(0, 20)}...` : 'EXISTING');
    const response = await apiClient.post('/admin/cache/clear');
    console.log('[clearCache] Successful response:', response.data);
    return response.data;
  } catch (error) {
    console.error('[clearCache] mistake:', error);
    console.error('[clearCache] Response:', error.response?.data);
    throw error.response?.data || { error: 'Errors in cleaning the cash' };
  }
};

export default apiClient;
