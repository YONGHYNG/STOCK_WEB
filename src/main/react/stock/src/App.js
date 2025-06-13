import React, { useState } from 'react';
import { HashRouter as Router, Routes, Route } from 'react-router-dom';
import ProductList from './components/ProductList';
import CategoryList from './components/CategoryList';
import LoginModal from './components/LoginModal';
import StockPage from './pages/StockPage';
import StockBestSeller from './pages/StockBestSeller';
import NewsBestSeller from './pages/NewsBestSeller';
import StockIndices from './components/StockIndices';
import './styles/App.css';

function App() {
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);

  return (
    <Router>
      <div className="App">
        <header className="App-header">
          <StockIndices />
        </header>
        <main>
          <Routes>
            <Route path="/" element={
              <>
                <h1 className="main-title"><span className="large">오</span>늘의 <span className="large">리</span>스트</h1>
                <CategoryList />
                <ProductList />
              </>
            } />
            <Route path="/clothing" element={<StockBestSeller />} />
            <Route path="/news" element={<NewsBestSeller />} />
            <Route path="/bags" element={<div className="category-page"><h1>가방 페이지</h1></div>} />
            <Route path="/accessories" element={<div className="category-page"><h1>액세서리 페이지</h1></div>} />
            <Route path="/community" element={<div className="category-page"><h1>커뮤니티 페이지</h1></div>} />
            <Route path="/stock" element={<StockPage />} />
          </Routes>
        </main>
        <LoginModal 
          isOpen={isLoginModalOpen} 
          onClose={() => setIsLoginModalOpen(false)} 
        />
      </div>
    </Router>
  );
}

export default App;
