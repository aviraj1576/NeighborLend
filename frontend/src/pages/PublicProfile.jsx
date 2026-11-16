import React from 'react';
import { Link, useParams } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import TrustScorePanel from '../components/TrustScorePanel';
import './PublicProfile.css';

export default function PublicProfile() {
  const { userId } = useParams();
  return <div className="public-profile-page app-page"><div className="wrap public-profile-wrap">
    <Link className="link public-profile-back" to="/browse"><ChevronLeft size={17} /> Back to browse</Link>
    <h1 className="t-h2">Neighbor profile</h1>
    <p className="t-lead measure">Trust and rental history from completed NeighborLend transactions.</p>
    <TrustScorePanel userId={userId} showIdentity />
  </div></div>;
}
