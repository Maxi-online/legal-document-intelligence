import axios from 'axios';

// Важно: при деплое через nginx (frontend container) API доступен по относительному пути `/api`.
// Если оставить дефолт `http://localhost:8000`, то в браузере пользователя "localhost" будет его ПК, а не сервер.
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
    console.log(`[API] Запрос к ${config.url} с токеном: ${token.substring(0, 20)}...`);
  } else {
    console.warn(`[API] Запрос к ${config.url} БЕЗ токена`);
  }
  return config;
});

apiClient.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error?.response?.status === 401) {
      console.error('401 Unauthorized - токен невалидный или отсутствует');
      console.error('Response:', error?.response?.data);
      localStorage.removeItem('access_token');
      // Перенаправляем на страницу логина только если это не запрос логина
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
    throw error.response?.data || { error: 'Ошибка входа' };
  }
};

export const searchCases = async (searchParams) => {
  try {
    const response = await apiClient.post('/search', searchParams);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: 'Ошибка при выполнении запроса' };
  }
};

export const getSearchStatus = async (taskId) => {
  try {
    const response = await apiClient.get(`/search/status/${taskId}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: 'Ошибка при получении статуса' };
  }
};

export const getSearchResults = async (taskId) => {
  try {
    const response = await apiClient.get(`/search/results/${taskId}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: 'Ошибка при получении результатов' };
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
    throw error.response?.data || { error: 'Ошибка при экспорте' };
  }
};

export const downloadAllActs = async (taskId) => {
  try {
    const response = await apiClient.get(`/acts/download_all/${taskId}`, {
      responseType: 'blob',
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { error: 'Ошибка при скачивании файлов' };
  }
};

export const clearDatabase = async ({ scope = 'all', task_id = null, include_search_logs = true }) => {
  try {
    console.log('[clearDatabase] Отправка запроса на очистку базы:', { scope, task_id, include_search_logs });
    const token = localStorage.getItem('access_token');
    console.log('[clearDatabase] Токен в localStorage:', token ? `${token.substring(0, 20)}...` : 'ОТСУТСТВУЕТ');
    const response = await apiClient.post('/admin/clear', {
      scope,
      task_id,
      include_search_logs,
    });
    console.log('[clearDatabase] Успешный ответ:', response.data);
    return response.data;
  } catch (error) {
    console.error('[clearDatabase] Ошибка:', error);
    console.error('[clearDatabase] Response:', error.response?.data);
    throw error.response?.data || { error: 'Ошибка при очистке базы' };
  }
};

export const clearCache = async () => {
  try {
    console.log('[clearCache] Отправка запроса на очистку кэша');
    const token = localStorage.getItem('access_token');
    console.log('[clearCache] Токен в localStorage:', token ? `${token.substring(0, 20)}...` : 'ОТСУТСТВУЕТ');
    const response = await apiClient.post('/admin/cache/clear');
    console.log('[clearCache] Успешный ответ:', response.data);
    return response.data;
  } catch (error) {
    console.error('[clearCache] Ошибка:', error);
    console.error('[clearCache] Response:', error.response?.data);
    throw error.response?.data || { error: 'Ошибка при очистке кэша' };
  }
};

export default apiClient;
