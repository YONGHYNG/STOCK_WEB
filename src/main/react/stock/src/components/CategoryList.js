import React from 'react';
import { Link } from 'react-router-dom';
import { 
  FaChartLine, FaNewspaper, FaShoppingBag, FaGem, FaUsers,
  FaMoneyBillWave, FaChartPie, FaGlobe, FaBuilding, FaIndustry,
  FaCar, FaPlane, FaShip, FaTrain, FaTruck
} from 'react-icons/fa';
import '../styles/CategoryList.css';

const categories = [
  // First Row - Main Categories
  {
    id: 1,
    name: '주식',
    icon: <FaChartLine />,
    path: '/clothing'
  },
  {
    id: 2,
    name: '뉴스',
    icon: <FaNewspaper />,
    path: '/news'
  },
  {
    id: 3,
    name: '가방',
    icon: <FaShoppingBag />,
    path: '/bags'
  },
  {
    id: 4,
    name: '액세서리',
    icon: <FaGem />,
    path: '/accessories'
  },
  {
    id: 5,
    name: '커뮤니티',
    icon: <FaUsers />,
    path: '/community'
  },
  // Second Row - Financial Categories
  {
    id: 6,
    name: '금융',
    icon: <FaMoneyBillWave />,
    path: '/finance'
  },
  {
    id: 7,
    name: '투자',
    icon: <FaChartPie />,
    path: '/investment'
  },
  {
    id: 8,
    name: '글로벌',
    icon: <FaGlobe />,
    path: '/global'
  },
  {
    id: 9,
    name: '부동산',
    icon: <FaBuilding />,
    path: '/realestate'
  },
  {
    id: 10,
    name: '제조업',
    icon: <FaIndustry />,
    path: '/manufacturing'
  },

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