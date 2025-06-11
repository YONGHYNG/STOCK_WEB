import React, { useEffect, useState } from 'react';
import '../styles/StockBestSeller.css';
import { FaCrown } from 'react-icons/fa';

function StockBestSeller() {

  const [volumeStocks, setVolumeStocks] = useState([]);
  const [marketCapStocks, setMarketCapStocks] = useState([]);
  const [risingStocks, setRisingStocks] = useState([]);
  const [fallingStocks, setFallingStocks] = useState([]);
  
   useEffect(() => {
    fetch('http://localhost:8080/api/stocks/volume-top10')
      .then(res => res.json())
      .then(data => setVolumeStocks(data))
      .catch(err => console.error(err));
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/stocks/marketcap-top10')
      .then(res => res.json())
      .then(data => setMarketCapStocks(data))
      .catch(err => console.error(err));
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/stocks/rising-top10')
      .then(res => res.json())
      .then(data => setRisingStocks(data))
      .catch(err => console.error(err));
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/stocks/falling-top10')
      .then(res => res.json())
      .then(data => setFallingStocks(data))
      .catch(err => console.error(err));
  }, []);

  const handleRowClick = (type) => {
    switch(type) {
      case 'volume':
        window.open('https://finance.naver.com/sise/nxt_sise_quant.naver?sosok=0', '_blank');
        break;
      case 'marketcap':
        window.open('https://finance.naver.com/sise/sise_market_sum.naver?sosok=0&page=1', '_blank');
        break;
      case 'rising':
        window.open('https://finance.naver.com/sise/sise_rise.naver', '_blank');
        break;
      case 'falling':
        window.open('https://finance.naver.com/sise/sise_fall.naver', '_blank');
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

  const renderStockTable = (title, stocks, type) => {
    return (
      <div className="stock-table-section">
        <h2>{title}</h2>
        <div className="stock-table-container">
          <table className="stock-table">
            <thead>
              <tr>
                <th>순위</th>
                <th>이름</th>
                <th>지금 가격</th>
                <th>등락률</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map((stock, index) => (
                <tr 
                  key={index} 
                  onClick={() => handleRowClick(type)}
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
        {renderStockTable("거래량 상위 종목", volumeStocks, 'volume')}
        {renderStockTable("시가총액 상위 종목", marketCapStocks, 'marketcap')}
        {renderStockTable("상승률 상위 종목", risingStocks, 'rising')}
        {renderStockTable("하락률 상위 종목", fallingStocks, 'falling')}
      </div>
    </div>
  );
}

export default StockBestSeller; 