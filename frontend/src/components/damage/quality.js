// Quick blur and brightness check on a small copy of the photo.
// The thresholds are first guesses, not tuned on real photos yet, so the
// UI only warns and always lets the person use the photo anyway.
export async function checkQuality(blob) {
  const bmp = await createImageBitmap(blob);
  const w = 160;
  const h = Math.max(8, Math.round((160 * bmp.height) / bmp.width));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(bmp, 0, 0, w, h);
  const d = ctx.getImageData(0, 0, w, h).data;

  const g = new Float32Array(w * h);
  let sum = 0;
  for (let i = 0; i < g.length; i++) {
    g[i] = 0.299 * d[i * 4] + 0.587 * d[i * 4 + 1] + 0.114 * d[i * 4 + 2];
    sum += g[i];
  }
  const brightness = sum / g.length;

  let n = 0, s = 0, s2 = 0;
  for (let y = 1; y < h - 1; y++) {
    for (let x = 1; x < w - 1; x++) {
      const c = y * w + x;
      const l = 4 * g[c] - g[c - 1] - g[c + 1] - g[c - w] - g[c + w];
      s += l; s2 += l * l; n++;
    }
  }
  const sharpness = s2 / n - (s / n) ** 2;

  const issues = [];
  if (brightness < 50) issues.push("The photo is very dark. Move to a brighter spot.");
  if (brightness > 215) issues.push("The photo is overexposed. Avoid direct light or glare.");
  if (sharpness < 40) issues.push("The photo looks blurry. Hold the phone steady and tap to focus.");
  return { ok: issues.length === 0, issues, brightness, sharpness };
}
