import React from 'react';
import '../styles/StockIndices.css';

const StockIndices = () => {
  const indices = [
    { name: 'KOSPI', value: '2,742.50', change: '+1.25%', isPositive: true },
    { name: 'KOSDAQ', value: '892.45', change: '-0.75%', isPositive: false },
    { name: 'KOSPI200', value: '367.80', change: '+0.85%', isPositive: true },
    { name: 'USD/KRW', value: '1,350.50', change: '-0.30%', isPositive: false },
    { name: 'JPY/KRW', value: '8.45', change: '+0.15%', isPositive: true },
    { name: 'CNY/KRW', value: '186.80', change: '-0.20%', isPositive: false },
    { name: 'S&P500', value: '5,234.50', change: '+0.95%', isPositive: true },
    { name: 'NASDAQ', value: '16,345.80', change: '+1.15%', isPositive: true },
    { name: 'DOW', value: '39,234.50', change: '+0.65%', isPositive: true },
    { name: 'VIX', value: '12.45', change: '-2.15%', isPositive: false }
  ];

  // Create multiple copies of the indices array for smoother infinite scroll
  const duplicatedIndices = [...indices, ...indices, ...indices, ...indices];

  return (
    <div className="stock-indices-container">
      <div className="indices-grid">
        {duplicatedIndices.map((index, idx) => (
          <div key={idx} className="index-item">
            <span className="index-name">{index.name}</span>
            <span className="index-value">{index.value}</span>
            <span className={`index-change ${index.isPositive ? 'positive' : 'negative'}`}>
              {index.change}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default StockIndices; 