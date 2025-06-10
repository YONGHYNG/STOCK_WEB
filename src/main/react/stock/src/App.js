import React, { useState } from 'react';
import { HashRouter as Router, Routes, Route } from 'react-router-dom';
import ImageSlider from './components/ImageSlider';
import ProductList from './components/ProductList';
import CategoryList from './components/CategoryList';
import LoginModal from './components/LoginModal';
import StockPage from './pages/StockPage';
import StockBestSeller from './pages/StockBestSeller';
import './styles/App.css';

function App() {
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false);

  return (
    <Router>
      <div className="App">
        <header className="App-header">
          <h1>랭킹한눈</h1>
          <button className="login-btn" onClick={() => setIsLoginModalOpen(true)}>로그인</button>
        </header>
        <main>
          <Routes>
            <Route path="/" element={
              <>
                <ImageSlider />
                <CategoryList />
                <ProductList />
              </>
            } />
            <Route path="/clothing" element={<StockBestSeller />} />
            <Route path="/shoes" element={<div className="category-page"><h1>신발 페이지</h1></div>} />
            <Route path="/bags" element={<div className="category-page"><h1>가방 페이지</h1></div>} />
            <Route path="/accessories" element={<div className="category-page"><h1>액세서리 페이지</h1></div>} />
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
