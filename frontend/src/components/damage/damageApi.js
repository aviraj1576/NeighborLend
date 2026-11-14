import { useCallback, useEffect, useRef, useState } from 'react';
import api from '../../api/client';

export const VIEWS = ['front', 'back', 'left', 'right', 'top', 'bottom'];
export const LABELS = {
  front: 'Front', back: 'Back', left: 'Left', right: 'Right', top: 'Top', bottom: 'Bottom',
};

export const apiError = (err, fallback) => err?.response?.data?.detail || err?.message || fallback;

export const getCheck = (checkId) =>
  api.get(`/damage-checks/${checkId}`, { headers: { 'Cache-Control': 'no-store' } }).then((r) => r.data);

export function uploadPhoto(checkId, phase, view, blob) {
  const form = new FormData();
  form.append('file', blob, `${view}.jpg`);
  return api.put(`/damage-checks/${checkId}/photos/${phase}/${view}`, form).then((r) => r.data);
}

export const userPhotoPath = (checkId, phase, view) => `/damage-checks/${checkId}/photos/${phase}/${view}`;
export const adminPhotoPath = (disputeId, phase, view) => `/admin/disputes/${disputeId}/photos/${phase}/${view}`;

/** Damage photos are private, so they need the Bearer header: fetch, then hand back a blob URL. */
export async function fetchPhotoUrl(path) {
  const res = await api.get(path, { responseType: 'blob' });
  return URL.createObjectURL(res.data);
}

/** Loads a set of photos as blob URLs. `pathFor(view)` returns the API path for one view. */
export function usePhotoUrls(pathFor, views) {
  const [urls, setUrls] = useState({});
  const cache = useRef({});

  const load = useCallback(async (view) => {
    try {
      const url = await fetchPhotoUrl(pathFor(view));
      if (cache.current[view]) URL.revokeObjectURL(cache.current[view]);
      cache.current[view] = url;
      setUrls({ ...cache.current });
    } catch {
      // the caller renders its own placeholder while a photo is missing
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathFor]);

  const key = views.join(',');
  useEffect(() => {
    views.filter((v) => !cache.current[v]).forEach(load);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, load]);

  useEffect(() => () => {
    Object.values(cache.current).forEach((u) => URL.revokeObjectURL(u));
  }, []);

  return { urls, reload: load };
}
