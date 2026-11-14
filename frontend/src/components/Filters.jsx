import React from 'react';

const Filters = ({ filters, onFilterChange, uniqueCourts, uniqueClassifications }) => {
  return (
    <div className="bg-white p-4 rounded-lg border border-gray-200 mb-6">
      <h3 className="text-lg font-semibold mb-4">Filters</h3>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Court
          </label>
          <select
            value={filters.court || ''}
            onChange={(e) => onFilterChange('court', e.target.value || null)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All courts</option>
            {uniqueCourts.map((court) => (
              <option key={court} value={court}>
                {court}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Classification
          </label>
          <select
            value={filters.classification || ''}
            onChange={(e) => onFilterChange('classification', e.target.value || null)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All types</option>
            {uniqueClassifications.map((classification) => (
              <option key={classification} value={classification}>
                {classification}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Date from
          </label>
          <input
            type="date"
            value={filters.dateFrom || ''}
            onChange={(e) => onFilterChange('dateFrom', e.target.value || null)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Date before
          </label>
          <input
            type="date"
            value={filters.dateTo || ''}
            onChange={(e) => onFilterChange('dateTo', e.target.value || null)}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {(filters.court || filters.classification || filters.dateFrom || filters.dateTo) && (
        <button
          onClick={() => {
            onFilterChange('court', null);
            onFilterChange('classification', null);
            onFilterChange('dateFrom', null);
            onFilterChange('dateTo', null);
          }}
          className="mt-4 px-4 py-2 text-sm text-blue-600 hover:text-blue-800 underline"
        >
          Disable Filters
        </button>
      )}
    </div>
  );
};

export default Filters;
