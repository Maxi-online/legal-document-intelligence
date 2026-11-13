import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import ResultTable from '../components/ResultTable';
import ExportButton from '../components/ExportButton';
import DownloadAllButton from '../components/DownloadAllButton';
import Filters from '../components/Filters';
import { getSearchStatus, getSearchResults } from '../services/api';
import { Loader2 } from 'lucide-react';

const SearchResultsPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const taskId = searchParams.get('taskId');
  const query = searchParams.get('query') || '';
  const highlightTerms = query
    .split(',')
    .map((q) => q.trim())
    .filter(Boolean);
  
  const [results, setResults] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [status, setStatus] = useState('pending');
  const [filters, setFilters] = useState({
    court: null,
    classification: null,
    dateFrom: null,
    dateTo: null,
  });

  useEffect(() => {
    if (!taskId) return;

    let timeoutId = null;
    let isMounted = true;

    const checkStatus = async () => {
      if (!isMounted) return;

      try {
        const statusData = await getSearchStatus(taskId);
        if (!isMounted) return;

        setStatus(statusData.status);

        if (statusData.status === 'completed') {
          const resultsData = await getSearchResults(taskId);
          if (!isMounted) return;
          
          setResults(resultsData.results || []);
          // Обновляем URL с информацией об уникальных делах
          if (resultsData.unique_cases_count !== undefined) {
            const newSearchParams = new URLSearchParams(searchParams);
            newSearchParams.set('uniqueCases', resultsData.unique_cases_count);
            window.history.replaceState({}, '', `?${newSearchParams.toString()}`);
          }
          setIsLoading(false);
        } else if (statusData.status === 'failed') {
          setIsLoading(false);
          alert('Ошибка при выполнении поиска');
        } else {
          // Опрашиваем снова только если статус pending или processing
          if (isMounted) {
            timeoutId = setTimeout(checkStatus, 2000);
          }
        }
      } catch (error) {
        console.error('Ошибка при проверке статуса:', error);
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    checkStatus();

    // Cleanup функция для отмены таймера при размонтировании компонента
    return () => {
      isMounted = false;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [taskId, searchParams]);

  const handleFilterChange = (key, value) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value,
    }));
  };

  const uniqueCourts = [...new Set(results.map((r) => r.court).filter(Boolean))];
  const uniqueClassifications = [
    ...new Set(results.map((r) => r.classification).filter(Boolean)),
  ];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <Loader2 className="animate-spin mx-auto mb-4" size={48} />
          <p className="text-lg text-gray-600">
            {status === 'pending' ? 'Обработка запроса...' : 'Поиск результатов...'}
          </p>
          <button
            onClick={() => navigate('/')}
            className="mt-6 px-4 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-900"
          >
            Назад к поиску
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6 flex justify-between items-center">
        <h1 className="text-3xl font-bold text-gray-900">Результаты поиска</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="px-4 py-2 bg-gray-800 text-white rounded-lg hover:bg-gray-900"
            title="Вернуться к форме поиска"
          >
            Новый поиск
          </button>
          <DownloadAllButton taskId={taskId} />
          <ExportButton taskId={taskId} />
        </div>
      </div>

      {results.length > 0 && (
        <Filters
          filters={filters}
          onFilterChange={handleFilterChange}
          uniqueCourts={uniqueCourts}
          uniqueClassifications={uniqueClassifications}
        />
      )}

      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        {results.length > 0 ? (
          <>
            <div className="mb-4 space-y-1 text-sm text-gray-600">
              <div>Найдено упоминаний: {results.length}</div>
              {searchParams.get('uniqueCases') && (
                <div>Уникальных дел: {searchParams.get('uniqueCases')}</div>
              )}
            </div>
            <ResultTable results={results} filters={filters} highlightTerms={highlightTerms} />
          </>
        ) : (
          <div className="text-center py-12">
            <p className="text-lg text-gray-600">Результаты не найдены</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default SearchResultsPage;
