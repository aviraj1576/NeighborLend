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

// Six thumbnails firing at once exhaust the backend's small database pool and
// come back as 500s, so photo downloads go through a tiny queue and retry.
const MAX_PARALLEL_PHOTOS = 2;
let activePhotoLoads = 0;
const photoQueue = [];

function nextPhoto() {
  if (activePhotoLoads >= MAX_PARALLEL_PHOTOS || photoQueue.length === 0) return;
  activePhotoLoads += 1;
  const { run, resolve, reject } = photoQueue.shift();
  run().then(resolve, reject).finally(() => {
    activePhotoLoads -= 1;
    nextPhoto();
  });
}

function queuePhoto(run) {
  return new Promise((resolve, reject) => {
    photoQueue.push({ run, resolve, reject });
    nextPhoto();
  });
}

const wait = (ms) => new Promise((r) => { window.setTimeout(r, ms); });

/** Damage photos are private, so they need the Bearer header: fetch, then hand back a blob URL. */
export function fetchPhotoUrl(path) {
  return queuePhoto(async () => {
    let lastError;
    for (let attempt = 0; attempt < 4; attempt += 1) {
      try {
        const res = await api.get(path, { responseType: 'blob' });
        return URL.createObjectURL(res.data);
      } catch (err) {
        lastError = err;
        const status = err?.response?.status;
        if (status && status < 500) break; // 403/404 will not fix themselves
        await wait(600 * (attempt + 1));
      }
    }
    throw lastError;
  });
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
