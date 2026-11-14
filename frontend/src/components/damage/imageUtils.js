// Shared image helpers. Plain browser APIs only, no dependencies.

/**
 * Centre-crop a source (video, image, bitmap) to `aspect` (width / height),
 * downscale so the longest side is at most `maxSide`, and encode as JPEG.
 * The crop matches CSS `object-fit: cover`, so what the person saw in the
 * frame is what gets saved.
 */
export function cropToBlob(source, srcW, srcH, aspect, maxSide = 1024, quality = 0.85) {
  let cw, ch;
  if (srcW / srcH > aspect) {
    ch = srcH;
    cw = srcH * aspect;
  } else {
    cw = srcW;
    ch = srcW / aspect;
  }
  const sx = (srcW - cw) / 2;
  const sy = (srcH - ch) / 2;
  const scale = Math.min(1, maxSide / Math.max(cw, ch));
  const width = Math.round(cw * scale);
  const height = Math.round(ch * scale);

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  canvas.getContext("2d").drawImage(source, sx, sy, cw, ch, 0, 0, width, height);

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve({ blob, width, height }) : reject(new Error("Could not encode the photo."))),
      "image/jpeg",
      quality
    );
  });
}

/** Decode an uploaded file, respecting EXIF rotation. */
export async function decodeFile(file) {
  const bitmap = await createImageBitmap(file);
  return { source: bitmap, width: bitmap.width, height: bitmap.height };
}

/** Turn a getUserMedia error into a message the person can act on. */
export function describeCameraError(err) {
  if (!window.isSecureContext) {
    return "The camera needs a secure (HTTPS) page. Open the deployed app, or run the dev server with HTTPS.";
  }
  switch (err && err.name) {
    case "NotAllowedError":
    case "SecurityError":
      return "Camera access is blocked. Allow the camera in your browser settings, then try again.";
    case "NotFoundError":
    case "OverconstrainedError":
      return "No camera was found on this device.";
    case "NotReadableError":
      return "The camera is in use by another app. Close it and try again.";
    default:
      return "The camera could not start.";
  }
}
