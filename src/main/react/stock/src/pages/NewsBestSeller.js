import React, { useEffect, useState } from 'react';
import '../styles/NewsBestSeller.css';
import { FaCrown } from 'react-icons/fa';

function NewsBestSeller() {
  const [popularNews, setPopularNews] = useState([]);
  const [latestNews, setLatestNews] = useState([]);
  const [domesticNews, setDomesticNews] = useState([]);
  const [internationalNews, setInternationalNews] = useState([]);
  
  useEffect(() => {
    fetch('http://localhost:8080/api/news/popular-top10')
      .then(res => res.json())
      .then(data => setPopularNews(data))
      .catch(err => console.error(err));
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/news/latest-top10')
      .then(res => res.json())
      .then(data => setLatestNews(data))
      .catch(err => console.error(err));
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/news/domestic-top10')
      .then(res => res.json())
      .then(data => setDomesticNews(data))
      .catch(err => console.error(err));
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/news/international-top10')
      .then(res => res.json())
      .then(data => setInternationalNews(data))
      .catch(err => console.error(err));
  }, []);

  const handleRowClick = (type) => {
    switch(type) {
      case 'popular':
        window.open('https://news.naver.com/main/main.naver?mode=LSD&mid=shm&sid1=100', '_blank');
        break;
      case 'latest':
        window.open('https://news.naver.com/main/main.naver?mode=LSD&mid=shm&sid1=100', '_blank');
        break;
      case 'domestic':
        window.open('https://news.naver.com/main/main.naver?mode=LSD&mid=shm&sid1=100', '_blank');
        break;
      case 'international':
        window.open('https://news.naver.com/main/main.naver?mode=LSD&mid=shm&sid1=104', '_blank');
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

  const renderNewsTable = (title, news, type) => {
    return (
      <div className="news-table-section">
        <h2>{title}</h2>
        <div className="news-table-container">
          <table className="news-table">
            <thead>
              <tr>
                <th>순위</th>
                <th>제목</th>
                <th>언론사</th>
                <th>작성일</th>
              </tr>
            </thead>
            <tbody>
              {news.map((item, index) => (
                <tr 
                  key={index} 
                  onClick={() => handleRowClick(type)}
                  style={{ cursor: 'pointer' }}
                >
                  <td className="rank-cell">
                    {renderRank(index)}
                  </td>
                  <td>{item.title}</td>
                  <td>{item.publisher}</td>
                  <td>{item.date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="news-best-seller">
      <h1>뉴스 베스트셀러</h1>
      <div className="news-tables-grid">
        {renderNewsTable("많이 본 뉴스", popularNews, 'popular')}
        {renderNewsTable("최신 뉴스", latestNews, 'latest')}
        {renderNewsTable("국내 뉴스", domesticNews, 'domestic')}
        {renderNewsTable("해외 뉴스", internationalNews, 'international')}
      </div>
    </div>
  );
}

export default NewsBestSeller; 