import React, { useEffect, useState } from 'react';
import '../styles/NewsBestSeller.css';
import { FaCrown } from 'react-icons/fa';

function NewsSection() {
  const [popularNews, setPopularNews] = useState([]);
  const [volumeStocks, setVolumeStocks] = useState([]);
  const [risingStocks, setRisingStocks] = useState([]);
  
  useEffect(() => {
    fetch('http://localhost:8080/api/news/popular')
      .then(res => res.json())
      .then(data => {
        setPopularNews(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching popular news:', err);
        setPopularNews([]);
      });
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/stock/volume')
      .then(res => res.json())
      .then(data => {
        setVolumeStocks(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching volume stocks:', err);
        setVolumeStocks([]);
      });
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/stocks/rising-top10')
      .then(res => res.json())
      .then(data => {
        setRisingStocks(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching rising stocks:', err);
        setRisingStocks([]);
      });
  }, []);

  const handleRowClick = (type) => {
    switch(type) {
      case 'popular':
        window.open('https://news.einfomax.co.kr/news/articleList.html?view_type=sm', '_blank');
        break;
      case 'volume':
        window.open('https://finance.naver.com/sise/nxt_sise_quant.naver?sosok=0', '_blank');
        break;
      case 'rising':
        window.open('https://finance.naver.com/sise/sise_rise.naver', '_blank');
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

  const renderNewsTable = (title, news, type) => {
    const newsArray = Array.isArray(news) ? news : [];
    
    return (
      <div className="news-table-section">
        <h2>{title}</h2>
        <div className="news-table-container">
          <table className="news-table">
            <thead>
              <tr>
                <th>순위</th>
                <th>제목</th>
              </tr>
            </thead>
            <tbody>
              {newsArray.length > 0 ? (
                newsArray.map((item, index) => (
                  <tr 
                    key={index} 
                    onClick={() => handleRowClick(type)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td className="rank-cell">
                      {renderRank(index)}
                    </td>
                    <td className="title-cell">
                      {type === 'popular' ? 
                        (item.title ? item.title.substring(2).trim() : item) 
                        : (item.title || item)
                      }
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan="2" style={{ textAlign: 'center' }}>데이터를 불러오는 중입니다...</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderStockTable = (title, stocks, type) => {
    const stocksArray = Array.isArray(stocks) ? stocks : [];
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
              {stocksArray.length > 0 ? (
                stocksArray.map((item, index) => (
                  <tr 
                    key={index} 
                    onClick={() => handleRowClick(type)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td className="rank-cell">
                      {renderRank(index)}
                    </td>
                    <td className="stock-name-cell">{item.name}</td>
                    <td className="stock-price-cell">{item.price}</td>
                    <td className={`stock-change-cell ${item.changeRate && item.changeRate.startsWith('+') ? 'positive' : (item.changeRate && item.changeRate.startsWith('-') ? 'negative' : '')}`}>
                      {item.changeRate}
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
    <div className="news-best-seller">
      <div className="title-container">
        <h1>Top List</h1>
      </div>
      <div className="news-tables-grid">
        {renderNewsTable("많이 본 뉴스", popularNews, 'popular')}
        {renderStockTable("거래량 상위 종목", volumeStocks, 'volume')}
        {renderStockTable("상승률 상위 종목", risingStocks, 'rising')}
      </div>
    </div>
  );
}

export default NewsSection; 