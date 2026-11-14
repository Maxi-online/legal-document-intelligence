import React, { useState } from 'react';
import { Trash2, Loader2 } from 'lucide-react';
import { clearDatabase } from '../services/api';

const ClearDatabaseButton = ({ scope = 'all', taskId = null }) => {
  const [isClearing, setIsClearing] = useState(false);

  const handleClear = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      alert('Error: You are not authorized. Please enter the system.');
      window.location.href = '/login';
      return;
    }

    const title =
      scope === 'task'
        ? `Clear the results of the task ${taskId}?`
        : 'Clear the SCJ database of results?';

    const ok = window.confirm(
      `${title}\n\nItll delete the data from PostgreSQL and cannot be cancelled.`
    );
    if (!ok) return;

    // additional confirmation for full wipe
    if (scope === 'all') {
      const ok2 = window.confirm('Are you sure youre gonna delete all the search results and logs?');
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
        `Ready. Results deleted: ${resp.deleted_cases}, Ladies: ${resp.deleted_search_logs}`
      );
    } catch (e) {
      console.error(e);
      const errorMsg = e?.detail || e?.error || 'Errors in cleaning the base';
      alert(`mistake: ${errorMsg}`);
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
      title="A Role Needed admin"
    >
      {isClearing ? (
        <>
          <Loader2 className="animate-spin" size={18} />
          Cleaning...
        </>
      ) : (
        <>
          <Trash2 size={18} />
          Clear Base
        </>
      )}
    </button>
  );
};

export default ClearDatabaseButton;

