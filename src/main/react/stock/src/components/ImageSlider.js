import React, { useState, useEffect } from 'react';
import '../styles/ImageSlider.css';

const ImageSlider = () => {
  const [currentSlide, setCurrentSlide] = useState(0);
  
  const slides = [
    {
      url: 'https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?w=800&auto=format&fit=crop',
      title: '슬라이드 1'
    },
    {
      url: 'https://images.unsplash.com/photo-1607082349566-187342175e2f?w=800&auto=format&fit=crop',
      title: '슬라이드 2'
    },
    {
      url: 'https://images.unsplash.com/photo-1607083206968-13611e3d76db?w=800&auto=format&fit=crop',
      title: '슬라이드 3'
    }
  ];

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % slides.length);
    }, 3000);

    return () => clearInterval(timer);
  }, [slides.length]);

  return (
    <div className="slider-container">
      <div 
        className="slider"
        style={{ transform: `translateX(-${currentSlide * 100}%)` }}
      >
        {slides.map((slide, index) => (
          <div key={index} className="slide">
            <img src={slide.url} alt={slide.title} />
          </div>
        ))}
      </div>
      <div className="slider-dots">
        {slides.map((_, index) => (
          <span
            key={index}
            className={`dot ${currentSlide === index ? 'active' : ''}`}
            onClick={() => setCurrentSlide(index)}
          />
        ))}
      </div>
    </div>
  );
};

export default ImageSlider; 