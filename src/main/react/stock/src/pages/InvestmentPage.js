import React, { useEffect, useState } from 'react';
import '../styles/InvestmentPage.css';
import { FaCrown } from 'react-icons/fa';

function InvestmentPage() {
  const [stockReports, setStockReports] = useState([]);
  const [industryReports, setIndustryReports] = useState([]);
  const [investmentReports, setInvestmentReports] = useState([]);
  const [topMarketCap, setTopMarketCap] = useState([]);

  useEffect(() => {
    fetch('http://localhost:8080/api/reports/stocks')
      .then(res => res.json())
      .then(data => {
        setStockReports(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching stock reports:', err);
        setStockReports([]);
      });
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/reports/industry')
      .then(res => res.json())
      .then(data => {
        setIndustryReports(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching industry reports:', err);
        setIndustryReports([]);
      });
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/reports/investment')
      .then(res => res.json())
      .then(data => {
        setInvestmentReports(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching investment reports:', err);
        setInvestmentReports([]);
      });
  }, []);

  useEffect(() => {
    fetch('http://localhost:8080/api/stock/top-market-cap')
      .then(res => res.json())
      .then(data => {
        setTopMarketCap(Array.isArray(data) ? data : []);
      })
      .catch(err => {
        console.error('Error fetching top market cap:', err);
        setTopMarketCap([]);
      });
  }, []);

  const handleRowClick = (stockCodeOrUrl) => {
    window.open(`https://finance.naver.com/item/main.naver?code=${stockCodeOrUrl}`, '_blank');
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
    <div className="investment-page">
      <div className="title-container">
        <h1>주식 리포트</h1>
      </div>
      <div className="investment-tables-grid">
        <div className="investment-table-section">
          <h2>기업 리포트</h2>
          <div className="investment-table-container">
            <table className="investment-table">
              <thead>
                <tr>
                  <th>순위</th>
                  <th>종목명</th>
                  <th colSpan="2">리포트 제목</th>
                </tr>
              </thead>
              <tbody>
                {stockReports.length > 0 ? (
                  stockReports.map((report, index) => (
                    <tr key={index}>
                      <td className="rank-cell">{renderRank(index)}</td>
                      <td className="name-cell">{report.stockName}</td>
                      <td className="title-cell" colSpan="2">{report.title}</td>
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

        <div className="investment-table-section">
          <h2>산업 리포트</h2>
          <div className="investment-table-container">
            <table className="investment-table">
              <thead>
                <tr>
                  <th>순위</th>
                  <th>증권사</th>
                  <th colSpan="2">리포트 제목</th>
                </tr>
              </thead>
              <tbody>
                {industryReports.length > 0 ? (
                  industryReports.map((report, index) => (
                    <tr key={index}>
                      <td className="rank-cell">{renderRank(index)}</td>
                      <td className="name-cell">{report.company}</td>
                      <td className="title-cell" colSpan="2">{report.title}</td>
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

        <div className="investment-table-section">
          <h2>투자 리포트</h2>
          <div className="investment-table-container">
            <table className="investment-table">
              <thead>
                <tr>
                  <th>순위</th>
                  <th>증권사</th>
                  <th colSpan="2">제목</th>
                </tr>
              </thead>
              <tbody>
                {investmentReports.length > 0 ? (
                  investmentReports.map((report, index) => (
                    <tr key={index}>
                      <td className="rank-cell">{renderRank(index)}</td>
                      <td className="name-cell">{report.company}</td>
                      <td className="title-cell" colSpan="2">{report.title}</td>
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

        <div className="investment-table-section">
          <h2>시가총액 상위 종목</h2>
          <div className="investment-table-container">
            <table className="investment-table">
              <thead>
                <tr>
                  <th>순위</th>
                  <th>종목명</th>
                  <th>현재가</th>
                  <th>시가총액</th>
                </tr>
              </thead>
              <tbody>
                {topMarketCap.length > 0 ? (
                  topMarketCap.map((stock, index) => (
                    <tr 
                      key={index} 
                      onClick={() => handleRowClick(stock.code)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="rank-cell">
                        {renderRank(index)}
                      </td>
                      <td className="name-cell">
                        {stock.name}
                      </td>
                      <td className="price-cell">
                        {stock.price}
                      </td>
                      <td className="market-cap-cell">
                        {stock.marketCap}
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

export default InvestmentPage; 