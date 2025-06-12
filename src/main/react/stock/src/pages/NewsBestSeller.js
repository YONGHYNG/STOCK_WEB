import React, { useEffect, useState } from 'react';
import '../styles/NewsBestSeller.css';
import { FaCrown } from 'react-icons/fa';

function NewsBestSeller() {
  const [popularNews, setPopularNews] = useState([]);
  const [latestNews, setLatestNews] = useState([]);
  const [domesticNews, setDomesticNews] = useState([]);
  const [internationalNews, setInternationalNews] = useState([]);
  
  useEffect(() => {
    fetch('http://localhost:8080/api/news/popular')
      .then(res => res.json())
      .then(data => {
        // 데이터가 배열인지 확인하고, 아니면 빈 배열로 설정
        setPopularNews(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching popular news:', err);
        setPopularNews([]);
      });
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/news/latest')
      .then(res => res.json())
      .then(data => {
        setLatestNews(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching latest news:', err);
        setLatestNews([]);
      });
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/news/domestic')
      .then(res => res.json())
      .then(data => {
        setDomesticNews(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching domestic news:', err);
        setDomesticNews([]);
      });
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/news/international')
      .then(res => res.json())
      .then(data => {
        setInternationalNews(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching international news:', err);
        setInternationalNews([]);
      });
  }, []);

  const handleRowClick = (type) => {
    switch(type) {
      case 'popular':
        window.open('https://news.einfomax.co.kr/news/articleList.html?view_type=sm', '_blank');
        break;
      case 'latest':
        window.open('https://finance.naver.com/news/news_list.naver?mode=LSTD&section_id=101&section_id2=258&type=1', '_blank');
        break;
      case 'domestic':
        window.open(
          "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258","_blank"
        );
        break;
      case 'international':
        window.open(
          "https://finance.naver.com/news/news_list.naver?mode=LSS3D&section_id=101&section_id2=258&section_id3=403",
          "_blank"
        );
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

  return (
    <div className="news-best-seller">
      <div className="title-container">
        <h1>뉴스 베스트셀러</h1>
        <div className="date-display">
          {new Date().toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
          })}
        </div>
      </div>
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