import React, { useState } from 'react';
import '../styles/LoginModal.css';
import SignupModal from './SignupModal';

const LoginModal = ({ isOpen, onClose }) => {
  const [id, setId] = useState('');
  const [password, setPassword] = useState('');
  const [isSignupModalOpen, setIsSignupModalOpen] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    // 여기에 로그인 로직 추가
    console.log('Login attempt:', { id, password });
    onClose();
  };

  const handleSignup = () => {
    setIsSignupModalOpen(true);
  };

  if (!isOpen) return null;

  return (
    <>
      <div className="modal-overlay">
        <div className="modal-content">
          <button className="close-button" onClick={onClose}>×</button>
          <h2>로그인</h2>
          <form onSubmit={handleSubmit}>
            <div className="input-group">
              <label htmlFor="id">아이디</label>
              <input
                type="text"
                id="id"
                value={id}
                onChange={(e) => setId(e.target.value)}
                placeholder="아이디를 입력하세요"
                required
              />
            </div>
            <div className="input-group">
              <label htmlFor="password">비밀번호</label>
              <input
                type="password"
                id="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="비밀번호를 입력하세요"
                required
              />
            </div>
            <button type="submit" className="submit-button">로그인</button>
            <button type="button" className="signup-button" onClick={handleSignup}>
              회원가입
            </button>
            <div className="find-links">
              <a href="#" className="find-link">아이디 찾기</a>
              <span className="divider">|</span>
              <a href="#" className="find-link">비밀번호 찾기</a>
            </div>
          </form>
        </div>
      </div>
      <SignupModal 
        isOpen={isSignupModalOpen} 
        onClose={() => setIsSignupModalOpen(false)} 
      />
    </>
  );
};

export default LoginModal; 