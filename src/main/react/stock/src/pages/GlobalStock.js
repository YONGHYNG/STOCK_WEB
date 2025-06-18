import React, { useState, useEffect } from 'react';
import '../styles/GlobalStock.css';
import { FaCrown } from 'react-icons/fa';

function GlobalStock() {
  const [nasdaqData, setNasdaqData] = useState([]);
  const [europeData, setEuropeData] = useState([]);
  const [asiaData, setAsiaData] = useState([]);
  const [emergingData, setEmergingData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [nasdaqResponse, europeResponse, asiaResponse, emergingResponse] = await Promise.all([
          fetch('http://localhost:8080/api/reports/globalStock'),
          fetch('http://localhost:8080/api/reports/europeStock'),
          fetch('http://localhost:8080/api/reports/asiaStock'),
          fetch('http://localhost:8080/api/reports/emergingStock')
        ]);

        if (!nasdaqResponse.ok || !europeResponse.ok || !asiaResponse.ok || !emergingResponse.ok) {
          throw new Error('데이터를 가져오는데 실패했습니다.');
        }

        const [nasdaq, europe, asia, emerging] = await Promise.all([
          nasdaqResponse.json(),
          europeResponse.json(),
          asiaResponse.json(),
          emergingResponse.json()
        ]);

        setNasdaqData(nasdaq);
        setEuropeData(europe);
        setAsiaData(asia);
        setEmergingData(emerging);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const handleRowClick = (type) => {
    switch(type) {
      case 'nasdaq':
        window.open('https://m.stock.naver.com/worldstock/home/USA/marketValue/NASDAQ', '_blank');
        break;
      case 'europe':
        window.open('https://m.stock.naver.com/worldstock/home/EUR/marketValue', '_blank');
        break;
      case 'asia':
        window.open('https://m.stock.naver.com/worldstock/home/JPY/marketValue', '_blank');
        break;
      case 'emerging':
        window.open('https://m.stock.naver.com/worldstock/home/CNY/marketValue', '_blank');
        break;
      default:
        break;
    }
  };

  const renderRank = (index) => {
    switch(index) {
      case 0:
        return (
          <div className="crown-container">
            <span className="rank-number gold">1.</span>
            <FaCrown className="crown-icon gold" />
          </div>
        );
      case 1:
        return (
          <div className="crown-container">
            <span className="rank-number silver">2.</span>
            <FaCrown className="crown-icon silver" />
          </div>
        );
      case 2:
        return (
          <div className="crown-container">
            <span className="rank-number bronze">3.</span>
            <FaCrown className="crown-icon bronze" />
          </div>
        );
      default:
        return `${index + 1}.`;
    }
  };

  const renderStockTable = (title, data, type) => {
    const stockArray = Array.isArray(data) ? data : [];
    
    return (
      <div className="stock-table-section">
        <h2>{title}</h2>
        <div className="stock-table-container">
          <table className="stock-table">
            <thead>
              <tr>
                <th>순위</th>
                <th>종목</th>
                <th>가격</th>
                <th>변동</th>
              </tr>
            </thead>
            <tbody>
              {stockArray.length > 0 ? (
                stockArray.map((item, index) => (
                  <tr 
                    key={index} 
                    onClick={() => handleRowClick(type)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td className="rank-cell">
                      {renderRank(index)}
                    </td>
                    <td className="name-cell">{item.name}</td>
                    <td className="price-cell">{item.price}</td>
                    <td className={`change-cell ${item.rate.startsWith('+') ? 'positive' : 'negative'}`}>
                      {item.rate}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="4" style={{ textAlign: 'center' }}>데이터를 불러오는 중입니다...</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="global-stock-page">
      <div className="title-container">
        <h1>글로벌 주식 시장</h1>
        <div className="date-display">
          {new Date().toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
          })}
        </div>
      </div>
      <div className="stock-tables-grid">
        {renderStockTable("나스닥 상위 종목", nasdaqData, 'nasdaq')}
        {renderStockTable("유럽 시장", europeData, 'europe')}
        {renderStockTable("아시아 시장", asiaData, 'asia')}
        {renderStockTable("신흥 시장", emergingData, 'emerging')}
      </div>
    </div>
  );
}

export default GlobalStock; 