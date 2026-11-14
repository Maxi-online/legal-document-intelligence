import React, { useState } from 'react';
import { Trash2, Loader2 } from 'lucide-react';
import { clearCache } from '../services/api';

const ClearCacheButton = () => {
  const [isClearing, setIsClearing] = useState(false);

  const handleClear = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) {
      alert('Error: You are not authorized. Please enter the system.');
      window.location.href = '/login';
      return;
    }

    const ok = window.confirm(
      'Clear Cash Redis?\n\nThis clears the request cache/status/Embeddings. Operation irreversible.'
    );
    if (!ok) return;

    setIsClearing(true);
    try {
      await clearCache();
      alert('Ready, cache cleared.');
    } catch (e) {
      console.error(e);
      const errorMsg = e?.detail || e?.error || 'Errors in cleaning the cash';
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
      disabled={isClearing}
      className="px-4 py-2 bg-amber-600 text-white rounded-lg hover:bg-amber-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
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
          Clear Cash
        </>
      )}
    </button>
  );
};

export default ClearCacheButton;

