import React, { useEffect, useState } from 'react';
import '../styles/CommunityBestSeller.css';
import { FaCrown } from 'react-icons/fa';

function CommunityBestSeller() {
  const [bestPosts, setBestPosts] = useState([]);
  const [bestOfBestPosts, setBestOfBestPosts] = useState([]);

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
                      onClick={() => handleRowClick(post.postUrl)}
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
                      onClick={() => handleRowClick(post.postUrl)}
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
      </div>
    </div>
  );
}

export default CommunityBestSeller; 