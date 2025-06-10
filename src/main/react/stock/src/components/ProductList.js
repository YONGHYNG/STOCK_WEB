import React, { useState } from 'react';
import '../styles/ProductList.css';

const ProductList = () => {
  const [showAll, setShowAll] = useState(false);
  
  const products = [
    {
      id: 1,
      name: '베이직 티셔츠',
      price: '29,000원',
      image: 'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=400&auto=format&fit=crop',
      icon: '👕'
    },
    {
      id: 2,
      name: '클래식 시계',
      price: '199,000원',
      image: 'https://images.unsplash.com/photo-1524805444758-089113d48a6d?w=400&auto=format&fit=crop',
      icon: '⌚'
    },
    {
      id: 3,
      name: '캐주얼 스니커즈',
      price: '79,000원',
      image: 'https://images.unsplash.com/photo-1549298916-b41d501d3772?w=400&auto=format&fit=crop',
      icon: '👟'
    },
    {
      id: 4,
      name: '클래식 토트백',
      price: '129,000원',
      image: 'https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=400&auto=format&fit=crop',
      icon: '👜'
    },
    {
      id: 5,
      name: '실버 목걸이',
      price: '89,000원',
      image: 'https://images.unsplash.com/photo-1599643478518-a784e5dc4c8f?w=400&auto=format&fit=crop',
      icon: '💍'
    },
    {
      id: 6,
      name: '프로 축구공',
      price: '49,000원',
      image: 'https://images.unsplash.com/photo-1579952363873-27f3bade9f55?w=400&auto=format&fit=crop',
      icon: '⚽'
    },
    {
      id: 7,
      name: '디자인 선글라스',
      price: '79,000원',
      image: 'https://images.unsplash.com/photo-1577803645773-f96470509666?w=400&auto=format&fit=crop',
      icon: '🕶️'
    },
    {
      id: 8,
      name: '요가 매트',
      price: '29,000원',
      image: 'https://images.unsplash.com/photo-1592432678016-e910b452f9a2?w=400&auto=format&fit=crop',
      icon: '🧘'
    }
  ];

  const displayedProducts = showAll ? products : products.slice(0, 3);

  return (
    <div className="product-container">
      <h2>TOP LIST</h2>
      <div className="product-grid">
        {displayedProducts.map((product) => (
          <div key={product.id} className="product-card">
            <div className="product-icon">{product.icon}</div>
            <img src={product.image} alt={product.name} />
            <h3>{product.name}</h3>
            <p className="price">{product.price}</p>
          </div>
        ))}
      </div>
      {!showAll && (
        <button 
          className="view-more-btn"
          onClick={() => setShowAll(true)}
        >
          더보기
        </button>
      )}
    </div>
  );
};

export default ProductList; 