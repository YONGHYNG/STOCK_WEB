import React, { useEffect, useState } from 'react';
import '../styles/IndexPage.css';

function IndexPage() {
  const [indices, setIndices] = useState([]);

  useEffect(() => {
    fetch('http://localhost:8080/api/headline/index')
      .then(res => res.json())
      .then(data => {
        setIndices(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching indices:', err);
        setIndices([]);
      });
  }, []);

  const renderIndexValue = (value) => {
    if (!value) return '';
    
    // 값이 상승인지 하락인지 확인
    const isUp = value.includes('▲');
    const isDown = value.includes('▼');
    
    return (
      <span className={`index-value ${isUp ? 'up' : isDown ? 'down' : ''}`}>
        {value}
      </span>
    );
  };

  return (
    <div className="index-page">
      <div className="title-container">
        <h1>주요 지수</h1>
      </div>
      <div className="index-container">
        <table className="index-table">
          <thead>
            <tr>
              <th>지수명</th>
              <th>현재가</th>
            </tr>
          </thead>
          <tbody>
            {indices.length > 0 ? (
              indices.map((index, idx) => (
                <tr key={idx}>
                  <td className="index-name">{index.name}</td>
                  <td className="index-value-cell">
                    {renderIndexValue(index.value)}
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
}

export default IndexPage; 