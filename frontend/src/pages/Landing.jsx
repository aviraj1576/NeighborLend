import React, { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Camera, Shield, Map as MapIcon, ArrowRight, Zap, CheckCircle2 } from 'lucide-react';
import './Landing.css';

const Landing = () => {
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
          }
        });
      },
      { threshold: 0.1 }
    );

    document.querySelectorAll('.animate-on-scroll').forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  return (
    <div className="landing-page">
      {/* Hero Section */}
      <section className="hero">
        <div className="hero-bg-glow"></div>
        <div className="container hero-content fade-in-up">
          <div className="badge">Welcome to the Future of Sharing</div>
          <h1 className="hero-title">
            Share More, <br />
            <span className="gradient-text">Own Less.</span>
          </h1>
          <p className="hero-subtitle">
            Rent items from your neighbors. Save money, reduce waste, and build a stronger community.
          </p>
          <div className="hero-actions">
            <Link to="/browse" className="btn-primary hero-btn">Browse Items</Link>
            <Link to="/create-listing" className="btn-outline hero-btn">List an Item</Link>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="features container animate-on-scroll">
        <h2 className="section-title text-center">Why choose NeighborLend?</h2>
        <div className="features-grid">
          <div className="feature-card glass">
            <div className="feature-icon-wrapper">
              <Camera className="feature-icon" />
            </div>
            <h3>AI-Powered</h3>
            <p>Our smart AI identifies your items instantly and suggests fair pricing, making listing a breeze.</p>
          </div>

          <div className="feature-card glass">
            <div className="feature-icon-wrapper">
              <Shield className="feature-icon" />
            </div>
            <h3>Secure Deals</h3>
            <p>Negotiate prices directly, pay securely through the platform, and rely on community reviews.</p>
          </div>

          <div className="feature-card glass">
            <div className="feature-icon-wrapper">
              <MapIcon className="feature-icon" />
            </div>
            <h3>Local First</h3>
            <p>Find items in your immediate neighborhood within walking distance. Zero shipping required.</p>
          </div>
        </div>
      </section>

      {/* How it Works Section */}
      <section className="how-it-works animate-on-scroll">
        <div className="container">
          <h2 className="section-title">How it works</h2>
          <div className="steps-container">
            <div className="step glass">
              <div className="step-number gradient-text">1</div>
              <h4>List</h4>
              <p>Snap a photo, let AI help you price it, and publish instantly.</p>
            </div>
            <div className="step-arrow"><ArrowRight /></div>
            <div className="step glass">
              <div className="step-number gradient-text">2</div>
              <h4>Connect</h4>
              <p>Neighbors browse, negotiate, and book your item.</p>
            </div>
            <div className="step-arrow"><ArrowRight /></div>
            <div className="step glass">
              <div className="step-number gradient-text">3</div>
              <h4>Share</h4>
              <p>Meet up, hand it over, and earn money. It's that simple.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Section */}
      <section className="stats container animate-on-scroll">
        <div className="stats-inner glass">
          <div className="stat-item">
            <div className="stat-number gradient-text">500+</div>
            <div className="stat-label">Active Items</div>
          </div>
          <div className="stat-item">
            <div className="stat-number gradient-text">2,000+</div>
            <div className="stat-label">Happy Neighbors</div>
          </div>
          <div className="stat-item">
            <div className="stat-number gradient-text">10,000+</div>
            <div className="stat-label">Successful Rentals</div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="cta-section container animate-on-scroll">
        <div className="cta-box glass">
          <h2>Ready to clear out the garage?</h2>
          <p>Turn your unused items into extra cash today.</p>
          <Link to="/register" className="btn-primary cta-btn">Join Now for Free</Link>
        </div>
      </section>
    </div>
  );
};

export default Landing;
