import api from '../api/client';

/**
 * Robust location detection utility:
 * 1. Attempts high-accuracy browser GPS with a 5s timeout.
 * 2. On GPS success, reverse geocodes to get a human-friendly address name.
 * 3. On GPS failure/denial/timeout, seamlessly falls back to IP-based location detection.
 * 4. Provides safe defaults if completely offline.
 */
export async function detectUserLocation() {
  // Step 1: Try browser Geolocation (high accuracy first, fallback to standard accuracy)
  const getPosition = (enableHighAccuracy, timeoutMs) =>
    new Promise((resolve) => {
      if (!navigator.geolocation) return resolve(null);
      let done = false;
      const timer = setTimeout(() => {
        if (!done) {
          done = true;
          resolve(null);
        }
      }, timeoutMs);

      navigator.geolocation.getCurrentPosition(
        (pos) => {
          if (!done) {
            done = true;
            clearTimeout(timer);
            resolve({
              latitude: pos.coords.latitude,
              longitude: pos.coords.longitude,
              method: 'gps',
            });
          }
        },
        (err) => {
          if (!done) {
            done = true;
            clearTimeout(timer);
            console.warn('Geolocation attempt warning:', err?.message || err);
            resolve(null);
          }
        },
        {
          enableHighAccuracy,
          timeout: timeoutMs,
          maximumAge: 60000,
        }
      );
    });

  let gpsResult = await getPosition(true, 6000);
  if (!gpsResult) {
    // Retry with standard accuracy (instant on laptops/desktops without hardware GPS)
    gpsResult = await getPosition(false, 4000);
  }

  if (gpsResult) {
    // Reverse geocode coordinate using BigDataCloud (CORS-enabled, fast, free, no auth)
    try {
      const revRes = await fetch(
        `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${gpsResult.latitude}&longitude=${gpsResult.longitude}&localityLanguage=en`,
        { signal: AbortSignal.timeout(3500) }
      );
      if (revRes.ok) {
        const data = await revRes.json();
        const locality = data.locality || data.city || data.principalSubdivision;
        const region = data.principalSubdivision || data.countryName;
        const formattedAddress = locality
          ? `${locality}${region && region !== locality ? `, ${region}` : ''}`
          : 'Detected Location';
        return {
          latitude: Number(gpsResult.latitude.toFixed(5)),
          longitude: Number(gpsResult.longitude.toFixed(5)),
          address: formattedAddress,
          city: locality || 'Current Location',
          method: 'gps',
        };
      }
    } catch {
      // Ignore reverse geocode network error
    }

    return {
      latitude: Number(gpsResult.latitude.toFixed(5)),
      longitude: Number(gpsResult.longitude.toFixed(5)),
      address: `Location (${gpsResult.latitude.toFixed(3)}°, ${gpsResult.longitude.toFixed(3)}°)`,
      city: 'Current Location',
      method: 'gps',
    };
  }

  // Step 2: Client-side IP lookup via ipwho.is (CORS-enabled, detects user's ISP city directly)
  try {
    const directRes = await fetch('https://ipwho.is/', { signal: AbortSignal.timeout(3500) });
    if (directRes.ok) {
      const data = await directRes.json();
      if (data.success && data.latitude && data.longitude) {
        const loc = `${data.city || ''}, ${data.region || ''}`.trim().replace(/^,|,$/g, '');
        return {
          latitude: Number(data.latitude.toFixed(5)),
          longitude: Number(data.longitude.toFixed(5)),
          address: loc || 'Patiala, Punjab',
          city: data.city || 'Patiala',
          method: 'ip',
        };
      }
    }
  } catch {
    // Ignore direct IP lookup failure
  }

  // Step 3: Fallback to IP geolocation via backend
  try {
    const res = await api.get('/listings/detect-location', { timeout: 4000 });
    if (res.data && res.data.latitude && res.data.longitude) {
      return {
        latitude: Number(res.data.latitude.toFixed(5)),
        longitude: Number(res.data.longitude.toFixed(5)),
        address: res.data.address || `${res.data.city}, ${res.data.region}`,
        city: res.data.city || 'Patiala',
        method: 'ip',
      };
    }
  } catch (err) {
    console.warn('Backend detect-location error:', err);
  }

  // Step 4: Ultimate default fallback to Patiala, Punjab
  return {
    latitude: 30.3362,
    longitude: 76.3922,
    address: 'Patiala, Punjab',
    city: 'Patiala',
    method: 'default',
  };
}

export const POPULAR_LOCATIONS = [
  { name: 'Patiala, Punjab (Hub)', lat: 30.3362, lon: 76.3922 },
  { name: 'Chandigarh', lat: 30.7333, lon: 76.7794 },
  { name: 'New Delhi', lat: 28.6139, lon: 77.2090 },
  { name: 'Gurgaon', lat: 28.4595, lon: 77.0266 },
  { name: 'Noida', lat: 28.5355, lon: 77.3910 },
  { name: 'Mumbai', lat: 19.0760, lon: 72.8777 },
  { name: 'Bengaluru', lat: 12.9716, lon: 77.5946 }
];
