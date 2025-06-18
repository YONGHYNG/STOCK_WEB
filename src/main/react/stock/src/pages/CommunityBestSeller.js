import React, { useEffect, useState } from 'react';
import '../styles/CommunityBestSeller.css';
import { FaCrown } from 'react-icons/fa';

function CommunityBestSeller() {
  const [bestPosts, setBestPosts] = useState([]);
  const [bestOfBestPosts, setBestOfBestPosts] = useState([]);
  const [dcBestPosts, setDcBestPosts] = useState([]);
  const [dogdripPosts, setDogdripPosts] = useState([]);

  useEffect(() => {
    fetch('http://localhost:8080/api/community/humor/best')
      .then(res => res.json())
      .then(data => {
        setBestPosts(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching best posts:', err);
        setBestPosts([]);
      });
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/community/humor/bestofbest')
      .then(res => res.json())
      .then(data => {
        setBestOfBestPosts(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching best of best posts:', err);
        setBestOfBestPosts([]);
      });
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/community/dcbest')
      .then(res => res.json())
      .then(data => {
        setDcBestPosts(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching DC best posts:', err);
        setDcBestPosts([]);
      });
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/community/dogdrip')
      .then(res => res.json())
      .then(data => {
        setDogdripPosts(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching Dogdrip popular posts:', err);
        setDogdripPosts([]);
      });
  }, []);

  const handleRowClick = (postUrl) => {
    window.open(postUrl, '_blank');
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

  return (
    <div className="community-best-seller">
      <div className="title-container">
        <h1>오늘의 유머 베스트</h1>
      </div>
      <div className="community-tables-grid">
        <div className="community-table-section">
          <h2>인기 게시글</h2>
          <div className="community-table-container">
            <table className="community-table">
              <thead>
                <tr>
                  <th>순위</th>
                  <th>제목</th>
                  <th>조회수</th>
                  <th>추천수</th>
                </tr>
              </thead>
              <tbody>
                {bestPosts.length > 0 ? (
                  bestPosts.map((post, index) => (
                    <tr 
                      key={index} 
                      onClick={() => handleRowClick(post.postUrl || 'https://www.todayhumor.co.kr/board/list.php?table=humorbest')}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="rank-cell">
                        {renderRank(index)}
                      </td>
                      <td className="title-cell">
                        {post.title}
                      </td>
                      <td className="hits-cell">
                        {post.hits}
                      </td>
                      <td className="likes-cell">
                        {post.likes}
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

        <div className="community-table-section">
          <h2>명예의 전당 게시글</h2>
          <div className="community-table-container">
            <table className="community-table">
              <thead>
                <tr>
                  <th>순위</th>
                  <th>제목</th>
                  <th>조회수</th>
                  <th>추천수</th>
                </tr>
              </thead>
              <tbody>
                {bestOfBestPosts.length > 0 ? (
                  bestOfBestPosts.map((post, index) => (
                    <tr 
                      key={index} 
                      onClick={() => handleRowClick(post.postUrl || 'https://www.todayhumor.co.kr/board/list.php?table=humorbest')}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="rank-cell">
                        {renderRank(index)}
                      </td>
                      <td className="title-cell">
                        {post.title}
                      </td>
                      <td className="hits-cell">
                        {post.hits}
                      </td>
                      <td className="likes-cell">
                        {post.likes}
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

        <div className="community-table-section">
          <h2>DC 인사이드 베스트 게시글</h2>
          <div className="community-table-container">
            <table className="community-table">
              <thead>
                <tr>
                  <th>순위</th>
                  <th>제목</th>
                  <th>조회수</th>
                  <th>추천수</th>
                </tr>
              </thead>
              <tbody>
                {dcBestPosts.length > 0 ? (
                  dcBestPosts.map((post, index) => (
                    <tr 
                      key={index} 
                      onClick={() => handleRowClick(post.postUrl || 'https://gall.dcinside.com/board/lists?id=dcbest')}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="rank-cell">
                        {renderRank(index)}
                      </td>
                      <td className="title-cell">
                        {post.title}
                      </td>
                      <td className="hits-cell">
                        {post.views}
                      </td>
                      <td className="likes-cell">
                        {post.likes}
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

        <div className="community-table-section">
          <h2>개드립 인기글</h2>
          <div className="community-table-container">
            <table className="community-table">
              <thead>
                <tr>
                  <th>순위</th>
                  <th>제목</th>
                  <th>추천수</th>
                  <th>댓글수</th>
                </tr>
              </thead>
              <tbody>
                {dogdripPosts.length > 0 ? (
                  dogdripPosts.map((post, index) => (
                    <tr 
                      key={index} 
                      onClick={() => handleRowClick('https://www.dogdrip.net/dogdrip')}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="rank-cell">
                        {renderRank(index)}
                      </td>
                      <td className="title-cell">
                        {post.title}
                      </td>
                      <td className="hits-cell">
                        {post.likes}
                      </td>
                      <td className="likes-cell">
                        {post.replys}
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
      </div>
    </div>
  );
}

export default CommunityBestSeller; 