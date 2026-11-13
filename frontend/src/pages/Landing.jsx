import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { MapPin, Star, Send, ShieldCheck, Smartphone, Clock } from 'lucide-react';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import './Landing.css';

const LANDING_COPY = {
  notice: 'Now live in Connaught Place · Delhi',
  kicker: 'Borrow what you need, from next door.',
  h1: 'Neighborhood lending, finally simple.',
  lead:
    'List the things you own and borrow what you need from neighbors nearby. Fair rates, no fees, and a community that looks out for each other.',
  primary: 'Browse items nearby',
  secondary: 'List an item to lend',
  fact1Label: 'Listings live',
  fact1Value: '1,200+',
  fact2Label: 'Rates from',
  fact2Value: '₹49 / day',
  fact3Label: 'Neighbors served',
  fact3Value: '8,400+',
};

const features = [
  {
    kicker: 'Listing',
    title: 'List in under a minute',
    body: 'Snap a photo, set your price, and publish. AI suggests a fair rate so you do not have to guess.',
    icon: Smartphone,
  },
  {
    kicker: 'Borrowing',
    title: 'Borrow by the day or week',
    body: 'Find tools, gear and appliances within walking distance. No shipping, no waiting, no deposit games.',
    icon: MapPin,
  },
  {
    kicker: 'Trust',
    title: 'Secure, community-backed',
    body: 'Pay through the platform, read neighbor reviews, and hand items over in person. Trust built locally.',
    icon: ShieldCheck,
  },
  {
    kicker: 'Earning',
    title: 'Earn from what you own',
    body: 'Things sitting in your closet can earn you money every weekend. You set the terms; we handle the rest.',
    icon: Send,
  },
];

const steps = [
  {
    number: '01',
    title: 'List your item',
    body: 'Add a photo and a price. Your listing goes live to neighbors nearby right away.',
  },
  {
    number: '02',
    title: 'A neighbor requests it',
    body: 'Borrowers browse and send a request. You chat, agree on a time, and accept.',
  },
  {
    number: '03',
    title: 'Hand it over, get paid',
    body: 'Meet at a local spot, hand over the item, and receive payment through the platform.',
  },
];

const TABS = ['Details', 'Reviews', 'Owner'];

const Landing = () => {
  const navigate = useNavigate();
  const [tab, setTab] = useState('Details');

  useEffect(() => {
    const els = document.querySelectorAll('[data-enter]');
    els.forEach((el) => el.classList.add('entered'));
  }, []);

  return (
    <>
      {/* ===== 1. Hero — asymmetric split: words left, product mockup right ===== */}
      <section className="hero section" style={{ '--h': '1' }} data-enter>
        <div className="wrap">
          <div className="hero-text hero-split">
            <div className="hero-copy">
              <div className="hero-notice">
                <b>{LANDING_COPY.notice}</b>
              </div>
              <h1 className="t-h1">{LANDING_COPY.h1}</h1>
              <p className="t-lead measure">{LANDING_COPY.lead}</p>
              <div className="btn-row">
                <Button variant="primary" asChild>
                  <Link to="/browse">{LANDING_COPY.primary}</Link>
                </Button>
                <Button variant="secondary" asChild>
                  <Link to="/create-listing">{LANDING_COPY.secondary}</Link>
                </Button>
              </div>
              <dl className="hero-facts">
                <div>
                  <dt>{LANDING_COPY.fact1Label}</dt>
                  <dd className="t-stat">{LANDING_COPY.fact1Value}</dd>
                </div>
                <div>
                  <dt>{LANDING_COPY.fact2Label}</dt>
                  <dd className="t-stat">{LANDING_COPY.fact2Value}</dd>
                </div>
                <div>
                  <dt>{LANDING_COPY.fact3Label}</dt>
                  <dd className="t-stat">{LANDING_COPY.fact3Value}</dd>
                </div>
              </dl>
            </div>
            <div className="hero-visual">
              <div className="frame frame--split frame--fill hero-frame entered">
                <div className="phone-mockup">
                  <div className="phone">
                    <div className="phone__screen">
                      <div className="app-bar">
                        <div className="app-bar__left">
                          <span className="app-bar__mark">N</span>
                          <span className="app-bar__title">NeighborLend</span>
                        </div>
                        <div className="app-bar__right">
                          <span className="pill app-pill">For rent</span>
                        </div>
                      </div>
                      <div className="app-hero">
                        <div className="app-photo" aria-hidden="true"></div>
                        <div className="app-info">
                          <h4 className="app-title">Cordless drill kit</h4>
                          <div className="app-meta">
                            <MapPin size={12} className="app-icon" />
                            <span>Connaught Place</span>
                          </div>
                          <div className="app-price">
                            <span className="app-rate">₹180</span>
                            <span className="app-per">/ day</span>
                          </div>
                          <Button
                            variant="primary"
                            size="sm"
                            className="app-borrow-btn"
                            onClick={() => navigate('/browse')}
                          >
                            Borrow
                          </Button>
                        </div>
                      </div>
                      <div className="app-tabs" role="tablist" aria-label="Listing preview">
                        {TABS.map((name) => (
                          <button
                            key={name}
                            type="button"
                            role="tab"
                            aria-selected={tab === name}
                            className={tab === name ? 'app-tab active' : 'app-tab'}
                            onClick={() => setTab(name)}
                          >
                            {name}
                          </button>
                        ))}
                      </div>
                      {tab === 'Details' && (
                        <div className="app-panel" role="tabpanel">
                          <ul className="app-spec">
                            <li>Drill body, 2 batteries and a 40-bit set</li>
                            <li>Pickup near Connaught Place metro</li>
                            <li>Owner verifies ID before handover</li>
                          </ul>
                        </div>
                      )}
                      {tab === 'Reviews' && (
                        <div className="app-panel" role="tabpanel">
                          <div className="app-review">
                            <span className="app-stars">★★★★★</span>
                            <p>“Returned it charged and cleaned. Seamless.”</p>
                            <span className="app-who">Rohan · 2 blocks away</span>
                          </div>
                          <div className="app-review">
                            <span className="app-stars">★★★★★</span>
                            <p>“Cheaper than buying for a one-day job.”</p>
                            <span className="app-who">Meera · 0.8 km away</span>
                          </div>
                        </div>
                      )}
                      {tab === 'Owner' && (
                        <div className="app-panel app-owner" role="tabpanel">
                          <span className="app-avatar" aria-hidden="true">P</span>
                          <div className="app-owner-meta">
                            <b>Priya S.</b>
                            <span>4.9 ★ · 23 loans · 1.2 km away</span>
                          </div>
                          <span className="app-ghost">Message</span>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="phone__glow" aria-hidden="true"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== 2. Bento feature grid ===== */}
      <section className="section" style={{ '--h': '1' }}>
        <div className="wrap grid grid--top">
          <div className="section-head span-5">
            <h2 className="t-h2">Built for neighbors, by neighbors</h2>
            <p>Everything about NeighborLend is designed to keep lending local, safe and effortless.</p>
          </div>
          <div className="span-7 start-6">
            <div className="grid grid--bento">
              {features.map((f, i) => (
                <Card key={f.title} variant="default">
                  <div className="feature-head">
                    <div className="feature-icon">
                      <f.icon size={20} />
                    </div>
                    <span className="feature-kicker">{f.kicker}</span>
                  </div>
                  <h3>{f.title}</h3>
                  <p>{f.body}</p>
                </Card>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ===== 3. Social proof strip ===== */}
      <section className="section section--strip" style={{ '--h': '1' }}>
        <div className="wrap">
          <div className="strip-inner">
            <div className="strip-words">
              <h2 className="t-h2">Trusted on every block</h2>
              <p>Listings are rated by the people who actually borrow them — no anonymous reviews, no algorithms between you and your neighbor.</p>
            </div>
            <div className="strip-proof">
              <div className="proof-item">
                <span className="proof-number t-stat">4.9 ★</span>
                <span className="proof-label">average owner rating</span>
              </div>
              <div className="proof-divider" aria-hidden="true"></div>
              <div className="proof-item">
                <span className="proof-number t-stat">98%</span>
                <span className="proof-label">items returned on time</span>
              </div>
              <div className="proof-divider" aria-hidden="true"></div>
              <div className="proof-item">
                <span className="proof-number t-stat">0%</span>
                <span className="proof-label">platform fees on loans</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== 4. How it works — one screen ===== */}
      <section className="section" style={{ '--h': '1' }}>
        <div className="wrap">
          <div className="section-head">
            <h2 className="t-h2">How a borrow works</h2>
            <p>Three steps from listing to handover, all within a few blocks.</p>
          </div>
          <div className="steps-row">
            {steps.map((step) => (
              <Card key={step.number} variant="default" className="step-card">
                <div className="step-head">
                  <span className="step-number">{step.number}</span>
                </div>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* ===== 5. CTA band ===== */}
      <section className="section section--cta" style={{ '--h': '1' }}>
        <div className="wrap frame frame--cta">
          <div className="cta-copy">
            <h2 className="t-h2">Ready to list your first item?</h2>
            <p>Publish in under a minute and start earning from things already in your home.</p>
            <div className="btn-row" style={{ marginTop: 'var(--s-6)' }}>
              <Button variant="primary" asChild>
                <Link to="/create-listing">List an item to lend</Link>
              </Button>
              <Button variant="secondary" asChild style={{ marginLeft: 'var(--s-3)' }}>
                <Link to="/browse">Browse what is available</Link>
              </Button>
            </div>
          </div>
        </div>
      </section>
    </>
  );
};

export default Landing;
