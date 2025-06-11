import React from 'react';
import { Link } from 'react-router-dom';
import '../styles/CategoryList.css';

const categories = [
  {
    id: 1,
    name: '주식',
    icon: '📈',
    path: '/clothing'
  },
  {
    id: 2,
    name: '뉴스',
    icon: '📰',
    path: '/news'
  },
  {
    id: 3,
    name: '가방',
    icon: '👜',
    path: '/bags'
  },
  {
    id: 4,
    name: '액세서리',
    icon: '⌚',
    path: '/accessories'
  },
  {
    id: 5,
    name: '커뮤니티',
    icon: '💬',
    path: '/community'
  }
];

const CategoryList = () => {
  return (
    <div className="category-list">
      {categories.map(category => (
        <Link to={category.path} key={category.id} className="category-item">
          <span className="category-icon">{category.icon}</span>
          <span className="category-name">{category.name}</span>
        </Link>
      ))}
    </div>
  );
};

export default CategoryList; 