import React, { useEffect, useState } from 'react';
import '../styles/ClothingPage.css';

function ClothingPage() {
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

  return (
    <div className="clothing-page">
      <h1>네이버 급등 상위 10 종목</h1>
      <div className="stock-table-container">
        <table className="stock-table">
          <thead>
            <tr>
              <th>종목명</th>
              <th>현재가</th>
              <th>등락률</th>
            </tr>
          </thead>
          <tbody>
            {stocks.map((stock, index) => (
              <tr key={index}>
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
}

export default ClothingPage; 