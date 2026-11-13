import React, { useState } from 'react';
import { BrowserRouter as Router, Routes, Route, useNavigate, Navigate, useLocation } from 'react-router-dom';
import SearchForm from './components/SearchForm';
import SearchResultsPage from './pages/SearchResultsPage';
import LoginPage from './pages/LoginPage';
import { searchCases } from './services/api';
import ClearDatabaseButton from './components/ClearDatabaseButton';
import ClearCacheButton from './components/ClearCacheButton';

const RequireAuth = ({ children }) => {
  const location = useLocation();
  const token = localStorage.getItem('access_token');
  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return children;
};

const HomePage = () => {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(false);

  const handleSearch = async (searchParams) => {
    setIsLoading(true);
    try {
      const response = await searchCases(searchParams);
      if (response.task_id) {
        const qp = new URLSearchParams();
        qp.set('taskId', response.task_id);
        if (searchParams?.query) qp.set('query', searchParams.query);
        if (searchParams?.search_type) qp.set('searchType', searchParams.search_type);
        navigate(`/results?${qp.toString()}`);
      } else {
        alert('Ошибка: не получен task_id');
      }
    } catch (error) {
      console.error('Ошибка при поиске:', error);
      alert(error.error || 'Ошибка при выполнении поиска');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="container mx-auto px-4 py-16">
        <div className="text-center mb-12">
          <h1 className="text-5xl font-bold text-gray-900 mb-4">DocumentIntelligence</h1>
          <p className="text-xl text-gray-600">
            Система поиска и анализа судебных актов
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <ClearCacheButton />
            <ClearDatabaseButton scope="all" />
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-xl p-8 mb-8">
          <SearchForm onSearch={handleSearch} isLoading={isLoading} />
        </div>

        <div className="bg-white rounded-lg shadow-lg p-6">
          <h2 className="text-2xl font-semibold mb-4">Как это работает?</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="text-center">
              <div className="text-4xl mb-2">1️⃣</div>
              <h3 className="font-semibold mb-2">Введите запрос</h3>
              <p className="text-gray-600 text-sm">
                Укажите ФИО, ИНН или наименование организации
              </p>
            </div>
            <div className="text-center">
              <div className="text-4xl mb-2">2️⃣</div>
              <h3 className="font-semibold mb-2">ИИ обработка</h3>
              <p className="text-gray-600 text-sm">
                Система найдет и проанализирует судебные акты с помощью ИИ
              </p>
            </div>
            <div className="text-center">
              <div className="text-4xl mb-2">3️⃣</div>
              <h3 className="font-semibold mb-2">Получите результаты</h3>
              <p className="text-gray-600 text-sm">
                Просматривайте, фильтруйте и экспортируйте результаты
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const App = () => {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <HomePage />
            </RequireAuth>
          }
        />
        <Route
          path="/results"
          element={
            <RequireAuth>
              <SearchResultsPage />
            </RequireAuth>
          }
        />
      </Routes>
    </Router>
  );
};

export default App;
