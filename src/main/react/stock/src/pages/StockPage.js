import React, { useEffect, useState } from 'react';
import '../styles/StockPage.css';

function Top5List() {
  const [top5, setTop5] = useState([]);

  useEffect(() => {
    fetch('http://localhost:8080/api/industries/top5')
      .then(res => res.json())
      .then(data => setTop5(data))
      .catch(err => console.error(err));
  }, []);

  return (
    <div className="top5-container">
      <h2 className="top5-title">"이 업종들 요즘 난리남🔥 — 오늘 제일 많이 오른 인기 업종 TOP 10!"</h2>
      <ul className="top5-list">
        {top5.map((item, index) => (
          <li key={index} className="top5-item">
            <span className="rank">{index + 1}</span>
            <span className="name">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const StockPage = () => {
  return (
    <div className="stock-page">
      <h1>주식 페이지</h1>
      <Top5List />
    </div>
  );
};

export default StockPage; 