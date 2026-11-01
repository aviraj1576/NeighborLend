const LOCAL_UPLOAD_URL = /^https?:\/\/(?:localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?(?=\/uploads\/)/i;

export function resolvePhotoUrl(url) {
  return typeof url === 'string' ? url.replace(LOCAL_UPLOAD_URL, '') : '';
}
