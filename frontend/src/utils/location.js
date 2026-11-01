import api from '../api/client';

/**
 * Robust location detection utility:
 * 1. Attempts high-accuracy browser GPS with a 5s timeout.
 * 2. On GPS success, reverse geocodes to get a human-friendly address name.
 * 3. On GPS failure/denial/timeout, seamlessly falls back to IP-based location detection.
 * 4. Provides safe defaults if completely offline.
 */
export async function detectUserLocation() {
  // Step 1: Try browser GPS
  const gpsResult = await new Promise((resolve) => {
    if (!navigator.geolocation) {
      return resolve(null);
    }

    let resolved = false;
    const timer = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        resolve(null);
      }
    }, 5000);

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        if (!resolved) {
          resolved = true;
          clearTimeout(timer);
          resolve({
            latitude: pos.coords.latitude,
            longitude: pos.coords.longitude,
            method: 'gps'
          });
        }
      },
      (err) => {
        if (!resolved) {
          resolved = true;
          clearTimeout(timer);
          console.warn('GPS location attempt failed:', err?.message || err);
          resolve(null);
        }
      },
      {
        enableHighAccuracy: true,
        timeout: 5000,
        maximumAge: 30000
      }
    );
  });

  if (gpsResult) {
    // Try to reverse geocode coordinate to get street/city name
    try {
      const revRes = await fetch(
        `https://nominatim.openstreetmap.org/reverse?format=json&lat=${gpsResult.latitude}&lon=${gpsResult.longitude}&zoom=14`,
        { headers: { 'Accept-Language': 'en' }, signal: AbortSignal.timeout(3000) }
      );
      if (revRes.ok) {
        const revData = await revRes.json();
        const addr = revData.address || {};
        const placeName = addr.suburb || addr.neighbourhood || addr.residential || addr.city || addr.town || addr.village || addr.county;
        const stateName = addr.state || addr.country;
        const formattedAddress = placeName ? `${placeName}${stateName ? `, ${stateName}` : ''}` : revData.display_name?.split(',').slice(0, 2).join(',') || 'My Location';
        return {
          latitude: Number(gpsResult.latitude.toFixed(5)),
          longitude: Number(gpsResult.longitude.toFixed(5)),
          address: formattedAddress,
          city: placeName || 'Current Location',
          method: 'gps'
        };
      }
    } catch {
      // Ignore reverse geocode error and continue with coords
    }

    return {
      latitude: Number(gpsResult.latitude.toFixed(5)),
      longitude: Number(gpsResult.longitude.toFixed(5)),
      address: `Location (${gpsResult.latitude.toFixed(3)}°, ${gpsResult.longitude.toFixed(3)}°)`,
      city: 'Current Location',
      method: 'gps'
    };
  }

  // Step 2: Fallback to IP geolocation via backend or public IP service
  try {
    const res = await api.get('/listings/detect-location', { timeout: 4000 });
    if (res.data && res.data.latitude && res.data.longitude) {
      return {
        latitude: Number(res.data.latitude.toFixed(5)),
        longitude: Number(res.data.longitude.toFixed(5)),
        address: res.data.address || `${res.data.city}, ${res.data.region}`,
        city: res.data.city || 'Detected Location',
        method: 'ip'
      };
    }
  } catch (err) {
    console.warn('Backend detect-location error:', err);
  }

  // Step 3: Direct fallback to public IP lookup if backend was unreachable
  try {
    const directRes = await fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout(3000) });
    if (directRes.ok) {
      const data = await directRes.json();
      if (data.latitude && data.longitude) {
        const loc = `${data.city || ''}, ${data.region || ''}`.trim().replace(/^,|,$/g, '');
        return {
          latitude: Number(data.latitude.toFixed(5)),
          longitude: Number(data.longitude.toFixed(5)),
          address: loc || 'Detected Area',
          city: data.city || 'Detected Area',
          method: 'ip'
        };
      }
    }
  } catch {
    // Ignore fallback failure
  }

  // Step 4: Ultimate default fallback
  return {
    latitude: 28.6139,
    longitude: 77.2090,
    address: 'New Delhi, Delhi',
    city: 'New Delhi',
    method: 'default'
  };
}

export const POPULAR_LOCATIONS = [
  { name: 'New Delhi (Hub)', lat: 28.6139, lon: 77.2090 },
  { name: 'Gurgaon', lat: 28.4595, lon: 77.0266 },
  { name: 'Noida', lat: 28.5355, lon: 77.3910 },
  { name: 'Patiala / Punjab', lat: 30.3362, lon: 76.3922 },
  { name: 'Chandigarh', lat: 30.7333, lon: 76.7794 },
  { name: 'Mumbai', lat: 19.0760, lon: 72.8777 },
  { name: 'Bengaluru', lat: 12.9716, lon: 77.5946 }
];
