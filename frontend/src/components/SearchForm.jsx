import React, { useState } from 'react';
import { Search, Loader2 } from 'lucide-react';

const SearchForm = ({ onSearch, isLoading }) => {
  const [formData, setFormData] = useState({
    query: '',
    searchType: 'fio',
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (formData.query.trim()) {
      onSearch({
        query: formData.query.trim(),
        search_type: formData.searchType,
      });
    }
  };

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-4xl mx-auto">
      <div className="flex flex-col gap-4">
        <div className="flex gap-4">
          <select
            name="searchType"
            value={formData.searchType}
            onChange={handleChange}
            className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="fio">ФИО</option>
            <option value="inn">ИНН</option>
            <option value="company">Наименование юридического лица</option>
          </select>
          <input
            type="text"
            name="query"
            value={formData.query}
            onChange={handleChange}
            placeholder={
              formData.searchType === 'fio'
                ? 'Введите ФИО'
                : formData.searchType === 'inn'
                ? 'Введите ИНН'
                : 'Введите наименование организации'
            }
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !formData.query.trim()}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isLoading ? (
              <>
                <Loader2 className="animate-spin" size={20} />
                Поиск...
              </>
            ) : (
              <>
                <Search size={20} />
                Найти
              </>
            )}
          </button>
        </div>
      </div>
    </form>
  );
};

export default SearchForm;
