import React, { useState } from 'react';
import { Trash2, Loader2 } from 'lucide-react';
import { clearCache } from '../services/api';

const ClearCacheButton = () => {
  const [isClearing, setIsClearing] = useState(false);

  const handleClear = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      alert('Ошибка: вы не авторизованы. Пожалуйста, войдите в систему.');
      window.location.href = '/login';
      return;
    }

    const ok = window.confirm(
      'Очистить кэш Redis?\n\nЭто сбросит кэш запросов/статусов/эмбеддингов. Операция необратима.'
    );
    if (!ok) return;

    setIsClearing(true);
    try {
      await clearCache();
      alert('Готово: кэш очищен.');
    } catch (e) {
      console.error(e);
      const errorMsg = e?.detail || e?.error || 'Ошибка при очистке кэша';
      alert(`Ошибка: ${errorMsg}`);
      if (e?.response?.status === 401) {
        localStorage.removeItem('access_token');
        window.location.href = '/login';
      }
    } finally {
      setIsClearing(false);
    }
  };

  return (
    <button
      onClick={handleClear}
      disabled={isClearing}
      className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
      title="Требуется роль admin"
    >
      {isClearing ? (
        <>
          <Loader2 className="animate-spin" size={18} />
          Очистка...
        </>
      ) : (
        <>
          <Trash2 size={18} />
          Очистить кэш
        </>
      )}
    </button>
  );
};

export default ClearCacheButton;

