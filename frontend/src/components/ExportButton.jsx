import React, { useState } from 'react';
import { Download, Loader2 } from 'lucide-react';
import { exportResults } from '../services/api';

const ExportButton = ({ taskId }) => {
  const [isExporting, setIsExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState('excel');

  const handleExport = async () => {
    if (!taskId) return;

    setIsExporting(true);
    try {
      const blob = await exportResults(taskId, exportFormat);
      
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      
      const extension = exportFormat === 'excel' ? 'xlsx' : exportFormat;
      link.download = `document_intelligence_results_${taskId}.${extension}`;
      
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Errors in Export:', error);
      alert('Errors in data export. Try again.');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <select
        value={exportFormat}
        onChange={(e) => setExportFormat(e.target.value)}
        className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        disabled={isExporting}
      >
        <option value="excel">Excel</option>
        <option value="pdf">PDF</option>
        <option value="json">JSON</option>
      </select>
      <button
        onClick={handleExport}
        disabled={isExporting || !taskId}
        className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
      >
        {isExporting ? (
          <>
            <Loader2 className="animate-spin" size={18} />
            Export...
          </>
        ) : (
          <>
            <Download size={18} />
            Exports
          </>
        )}
      </button>
    </div>
  );
};

export default ExportButton;
