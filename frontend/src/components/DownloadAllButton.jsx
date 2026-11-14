import React, { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { downloadAllActs } from '../services/api';

const DownloadAllButton = ({ taskId }) => {
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = async () => {
    if (!taskId) return;
    setIsDownloading(true);
    try {
      const blob = await downloadAllActs(taskId);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `document_intelligence_acts_${taskId}.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error in downloading files:', error);
      alert('Error in downloading files. Try again.');
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <button
      onClick={handleDownload}
      disabled={isDownloading || !taskId}
      className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
      title="download all acts with reference (ZIP)"
    >
      {isDownloading ? (
        <>
          <Loader2 className="animate-spin" size={18} />
          The download...
        </>
      ) : (
        <>
          <Download size={18} />
          download all files
        </>
      )}
    </button>
  );
};

export default DownloadAllButton;

