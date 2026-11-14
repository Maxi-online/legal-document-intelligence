import React, { useMemo, useState, useEffect } from 'react';
import { ExternalLink, ChevronDown, ChevronUp } from 'lucide-react';
import { format } from 'date-fns';

const escapeRegExp = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const HighlightedText = ({ text, terms }) => {
  const safeText = String(text || '');
  const safeTerms = Array.isArray(terms) ? terms.filter(Boolean) : [];

  const parts = useMemo(() => {
    if (!safeText || safeTerms.length === 0) return [safeText];
    const pattern = safeTerms.map(escapeRegExp).join('|');
    const re = new RegExp(`(${pattern})`, 'gi');
    return safeText.split(re);
  }, [safeText, safeTerms]);

  if (safeTerms.length === 0) return <>{safeText}</>;

  return (
    <>
      {parts.map((p, idx) => {
        const isHit = safeTerms.some((t) => p.toLowerCase() === String(t).toLowerCase());
        return isHit ? (
          <mark key={idx} className="bg-yellow-200 px-0.5 rounded">
            {p}
          </mark>
        ) : (
          <React.Fragment key={idx}>{p}</React.Fragment>
        );
      })}
    </>
  );
};

const ResultTable = ({ results, filters, highlightTerms = [] }) => {
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });
  const [expandedRow, setExpandedRow] = useState(null);
  const [translations, setTranslations] = useState(null);

  useEffect(() => {
    fetch('/translations.json')
      .then(res => res.json())
      .then(data => setTranslations(data))
      .catch(err => console.error('Failed to load translations:', err));
  }, []);

  const translateType = (type) => {
    if (!type || !translations) return type;
    const sideTypes = translations.side_types || {};
    // Precise values shall be processed (e.g. "debtor,creditor")
    const types = type.split(',').map(t => t.trim());
    const translated = types.map(t => {
      const lower = t.toLowerCase();
      return sideTypes[lower] || sideTypes[t] || t;
    });
    return translated.join(', ');
  };

  const translateParties = (parties) => {
    if (!parties || !translations) return parties;
    if (typeof parties === 'string') {
      const sideTypes = translations.side_types || {};
      let translated = parties;
      Object.keys(sideTypes).forEach(key => {
        const regex = new RegExp(`\\(${key}\\)`, 'gi');
        translated = translated.replace(regex, `(${sideTypes[key]})`);
      });
      return translated;
    }
    return parties;
  };

  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const sortedResults = [...results].sort((a, b) => {
    if (!sortConfig.key) return 0;

    let aValue = a[sortConfig.key];
    let bValue = b[sortConfig.key];

    if (sortConfig.key === 'date' || sortConfig.key === 'ingested_at') {
      aValue = new Date(aValue);
      bValue = new Date(bValue);
    }

    if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1;
    if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1;
    return 0;
  });

  const filteredResults = sortedResults.filter((result) => {
    if (filters.court && result.court !== filters.court) return false;
    if (filters.classification && result.classification !== filters.classification) return false;
    if (filters.dateFrom && new Date(result.date) < new Date(filters.dateFrom)) return false;
    if (filters.dateTo && new Date(result.date) > new Date(filters.dateTo)) return false;
    return true;
  });

  const getClassificationBadgeColor = (classification) => {
    const colors = {
      'Claimant': 'bg-green-100 text-green-800',
      'respondent': 'bg-red-100 text-red-800',
      'State party': 'bg-blue-100 text-blue-800',
      'counterparty': 'bg-yellow-100 text-yellow-800',
    };
    return colors[classification?.toLowerCase()] || 'bg-gray-100 text-gray-800';
  };

  return (
    <div className="w-full overflow-x-auto">
      <table className="min-w-full bg-white border border-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th
              className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100"
              onClick={() => handleSort('case_number')}
            >
              Case number
            </th>
            <th
              className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100"
              onClick={() => handleSort('court')}
            >
              Court
            </th>
            <th
              className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100"
              onClick={() => handleSort('date')}
            >
              Date of act
            </th>
            <th
              className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase cursor-pointer hover:bg-gray-100"
              onClick={() => handleSort('ingested_at')}
            >
              Loading date
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Type of reference
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Classification
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Relevance
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Context
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200">
          {filteredResults.length === 0 ? (
            <tr>
              <td colSpan="9" className="px-4 py-8 text-center text-gray-500">
                No results found
              </td>
            </tr>
          ) : (
            filteredResults.map((result, index) => (
              <React.Fragment key={result.id || index}>
                <tr className="hover:bg-gray-50">
                  <td className="px-4 py-3 text-sm text-gray-900">{result.case_number}</td>
                  <td className="px-4 py-3 text-sm text-gray-900">{result.court}</td>
                  <td className="px-4 py-3 text-sm text-gray-900">
                    {result.date
                      ? format(new Date(result.date), 'dd.MM.yyyy')
                      : 'N/A'}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">
                    {result.ingested_at
                      ? format(new Date(result.ingested_at), 'dd.MM.yyyy')
                      : '—'}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">
                    {result.type_of_mention ? translateType(result.type_of_mention) : '—'}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <span
                      className={`px-2 py-1 rounded-full text-xs font-medium ${getClassificationBadgeColor(
                        result.classification
                      )}`}
                    >
                      {result.classification || 'Not specified'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">
                    {result.relevance_score ? `${(result.relevance_score * 100).toFixed(1)}%` : 'N/A'}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700 max-w-[520px]">
                    <div className="max-h-10 overflow-hidden">
                      <HighlightedText text={(result.context || '').slice(0, 180)} terms={highlightTerms} />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <div className="flex items-center gap-2">
                      {result.act_url && (
                        <a
                          href={result.act_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:text-blue-800 flex items-center gap-1"
                        >
                          <ExternalLink size={16} />
                          Open
                        </a>
                      )}
                      <button
                        onClick={() =>
                          setExpandedRow(expandedRow === index ? null : index)
                        }
                        className="text-gray-600 hover:text-gray-800"
                      >
                        {expandedRow === index ? (
                          <ChevronUp size={16} />
                        ) : (
                          <ChevronDown size={16} />
                        )}
                      </button>
                    </div>
                  </td>
                </tr>
                {expandedRow === index && (
                  <tr>
                    <td colSpan="9" className="px-4 py-4 bg-gray-50">
                      <div className="space-y-2">
                        <div>
                          <strong>Context of reference:</strong>
                          <p className="mt-1 text-sm text-gray-700 whitespace-pre-wrap">
                            <HighlightedText text={result.context || 'Not specified'} terms={highlightTerms} />
                          </p>
                        </div>
                        {result.ingested_at && (
                          <div>
                            <strong>Loaded to base:</strong>
                            <p className="mt-1 text-sm text-gray-700">
                              {format(new Date(result.ingested_at), 'dd.MM.yyyy')}
                            </p>
                          </div>
                        )}
                        {result.parties && (
                          <div>
                            <strong>Parties to the case:</strong>
                            <p className="mt-1 text-sm text-gray-700">{translateParties(result.parties)}</p>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};

export default ResultTable;
