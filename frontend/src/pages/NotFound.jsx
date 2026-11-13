import React from 'react';
import { Link } from 'react-router-dom';
import Button from '../components/ui/Button';

const NotFound = () => (
  <div className="app-page">
    <div className="wrap">
      <div className="section-head">
        <h1 className="t-h2">Page not found</h1>
        <p>The page you are looking for does not exist or has moved.</p>
        <div className="btn-row">
          <Button variant="primary" asChild>
            <Link to="/browse">Browse items</Link>
          </Button>
          <Button variant="secondary" asChild>
            <Link to="/">Go to the home page</Link>
          </Button>
        </div>
      </div>
    </div>
  </div>
);

export default NotFound;
