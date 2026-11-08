// The song's colour, picked from its cover: the most present lively hue, brightened so it reads on
// the island's black. Worked out once per cover (a 24x24 copy), then cached.
import { useEffect, useState } from 'react';

export interface SongColor { c: string; dark: string }
const cache = new Map<string, SongColor>();

function rgbToHsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min;
  if (!d) return [0, 0, l];
  const s = d / (1 - Math.abs(2 * l - 1));
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [(h * 60 + 360) % 360, s, l];
}

/** pixels as [r, g, b, a, ...] → the colour; null for a grey cover */
export function pickColor(px: Uint8ClampedArray): SongColor | null {
  const BINS = 12, weight = new Array(BINS).fill(0), hue = new Array(BINS).fill(0);
  for (let i = 0; i < px.length; i += 4) {
    if (px[i + 3] < 128) continue;
    const [h, s, l] = rgbToHsl(px[i], px[i + 1], px[i + 2]);
    if (s < 0.25 || l < 0.12 || l > 0.9) continue;          // greys, near-black and near-white say nothing
    const w = s * (l > 0.25 && l < 0.75 ? 1 : 0.4), b = Math.floor(h / (360 / BINS)) % BINS;
    weight[b] += w; hue[b] += h * w;
  }
  const best = weight.indexOf(Math.max(...weight));
  if (!weight[best]) return null;
  const h = Math.round(hue[best] / weight[best]);
  return { c: `hsl(${h} 80% 62%)`, dark: `hsl(${h} 65% 30%)` };
}

const FALLBACK: SongColor = { c: 'var(--color-accent)', dark: 'color-mix(in srgb, var(--color-accent) 45%, black)' };

/** the colour of a cover (a data: URL), or the theme's accent while it's worked out or when there's none */
export function useSongColor(art?: string | null): SongColor {
  const [col, setCol] = useState<SongColor>(() => (art && cache.get(art)) || FALLBACK);
  useEffect(() => {
    if (!art) { setCol(FALLBACK); return; }
    const hit = cache.get(art);
    if (hit) { setCol(hit); return; }
    let live = true;
    const img = new Image();
    img.onload = () => {
      try {
        const cv = document.createElement('canvas');
        cv.width = cv.height = 24;
        const g = cv.getContext('2d', { willReadFrequently: true })!;
        g.drawImage(img, 0, 0, 24, 24);
        const got = pickColor(g.getImageData(0, 0, 24, 24).data) ?? FALLBACK;
        if (cache.size > 50) cache.clear();
        cache.set(art, got);
        if (live) setCol(got);
      } catch { /* an unreadable cover: keep the accent */ }
    };
    img.src = art;
    return () => { live = false; };
  }, [art]);
  return col;
}

/** the colour as CSS variables for a subtree: --song and --song-dark */
export const songVars = (c: SongColor) => ({ '--song': c.c, '--song-dark': c.dark }) as React.CSSProperties;
