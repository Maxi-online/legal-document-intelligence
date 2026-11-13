import React, { useState } from 'react';
import { Trash2, Loader2 } from 'lucide-react';
import { clearDatabase } from '../services/api';

const ClearDatabaseButton = ({ scope = 'all', taskId = null }) => {
  const [isClearing, setIsClearing] = useState(false);

  const handleClear = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      alert('Ошибка: вы не авторизованы. Пожалуйста, войдите в систему.');
      window.location.href = '/login';
      return;
    }

    const title =
      scope === 'task'
        ? `Очистить результаты задачи ${taskId}?`
        : 'Очистить ВСЮ базу данных результатов?';

    const ok = window.confirm(
      `${title}\n\nЭто удалит данные из PostgreSQL и не может быть отменено.`
    );
    if (!ok) return;

    // дополнительное подтверждение для полного wipe
    if (scope === 'all') {
      const ok2 = window.confirm('Точно удалить ВСЕ результаты и логи поиска?');
      if (!ok2) return;
    }

    setIsClearing(true);
    try {
      const resp = await clearDatabase({
        scope,
        task_id: scope === 'task' ? taskId : null,
        include_search_logs: true,
      });
      alert(
        `Готово. Удалено результатов: ${resp.deleted_cases}, логов: ${resp.deleted_search_logs}`
      );
    } catch (e) {
      console.error(e);
      const errorMsg = e?.detail || e?.error || 'Ошибка при очистке базы';
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
      disabled={isClearing || (scope === 'task' && !taskId)}
      className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
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
          Очистить базу
        </>
      )}
    </button>
  );
};

export default ClearDatabaseButton;

