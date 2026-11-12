import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
// taste-skill kit CSS (bundled by Vite, no public/assets dependency)
import './design/skill-kit/system.css';
import './design/skill-kit/cards.css';
import './design/skill-kit/motion.css';
import './design/skill-kit/backgrounds.css';
import './design/skill-kit/layout.css';
import './design/skill-kit/icon.css';
import './design/theme.css';
import './design/global.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
