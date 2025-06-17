import React from "react";
import "../styles/ProductList.css";

function NewsSection() {
  const renderTable = (title) => (
    <div className="table-section">
      <h2>{title}</h2>
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th>순위</th>
              <th>항목</th>
              <th>값</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>1</td>
              <td>예시 데이터</td>
              <td>123</td>
            </tr>
            <tr>
              <td>2</td>
              <td>예시 데이터</td>
              <td>456</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <div className="news-best-seller">
      <div className="title-container">
        <h1>Top 9 Lists</h1>
      </div>
      <div className="tables-grid">
        {renderTable("테이블 1")}
        {renderTable("테이블 2")}
        {renderTable("테이블 3")}
        {renderTable("테이블 4")}
        {renderTable("테이블 5")}
        {renderTable("테이블 6")}
        {renderTable("테이블 7")}
        {renderTable("테이블 8")}
        {renderTable("테이블 9")}
      </div>
    </div>
  );
}

export default NewsSection;
