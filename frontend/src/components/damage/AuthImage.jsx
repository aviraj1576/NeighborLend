import './Damage.css';
import React, { useEffect, useState } from 'react';
import { fetchPhotoUrl } from './damageApi';

/**
 * <img> for a private damage-check photo. A plain <img src> cannot send the Bearer header,
 * so the photo is fetched through the API client and shown from a blob URL.
 * Props: path (API path such as /damage-checks/{id}/photos/before/front), alt, className.
 */
export default function AuthImage({ path, alt, className = '' }) {
  const [src, setSrc] = useState('');
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let revoked = false;
    let objectUrl = '';
    setSrc('');
    setFailed(false);
    if (!path) return undefined;
    fetchPhotoUrl(path)
      .then((url) => {
        if (revoked) URL.revokeObjectURL(url);
        else { objectUrl = url; setSrc(url); }
      })
      .catch(() => { if (!revoked) setFailed(true); });
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (failed) return <div className={`dmg-img-missing ${className}`} role="img" aria-label={alt}>Photo unavailable</div>;
  if (!src) return <div className={`dmg-img-loading ${className}`} aria-busy="true" aria-label={`Loading ${alt}`} />;
  return <img className={className} src={src} alt={alt} />;
}
