import React, { useEffect, useState } from 'react';
import '../styles/StockBestSeller.css';
import { FaCrown } from 'react-icons/fa';

function StockBestSeller() {
  const [stocks, setStocks] = useState([]);

  useEffect(() => {
    fetch('http://localhost:8080/api/stocks/top10')
      .then(res => res.json())
      .then(data => {
        setStocks(data);
        console.log(data);
      })
     .catch(err => console.error(err));
  }, []);

  const handleRowClick = () => {
    window.open('https://finance.naver.com/sise/nxt_sise_quant.naver?sosok=0', '_blank');
  };

  const renderRank = (index) => {
    switch(index) {
      case 0:
        return (
          <div className="crown-container">
            <span className="rank-number gold">1</span>
            <FaCrown className="crown-icon gold" />
          </div>
        );
      case 1:
        return (
          <div className="crown-container">
            <span className="rank-number silver">2</span>
            <FaCrown className="crown-icon silver" />
          </div>
        );
      case 2:
        return (
          <div className="crown-container">
            <span className="rank-number bronze">3</span>
            <FaCrown className="crown-icon bronze" />
          </div>
        );
      default:
        return index + 1;
    }
  };

  const renderStockTable = (title) => {
    return (
      <div className="stock-table-section">
        <h2>{title}</h2>
        <div className="stock-table-container">
          <table className="stock-table">
            <thead>
              <tr>
                <th>순위</th>
                <th>종목명</th>
                <th>현재가</th>
                <th>등락률</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map((stock, index) => (
                <tr 
                  key={index} 
                  onClick={handleRowClick}
                  style={{ cursor: 'pointer' }}
                >
                  <td className="rank-cell">
                    {renderRank(index)}
                  </td>
                  <td>{stock.name}</td>
                  <td>{stock.price}</td>
                  <td>{stock.changeRate}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="stock-best-seller">
      <h1>주식 마켓 베스트셀러</h1>
      <div className="stock-tables-grid">
        {renderStockTable("거래량 상위 종목")}
        {renderStockTable("시가총액 상위 종목")}
        {renderStockTable("상승률 상위 종목")}
        {renderStockTable("하락률 상위 종목")}
      </div>
    </div>
  );
}

export default StockBestSeller; 