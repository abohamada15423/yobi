// The island's language (Settings → الشكل/Look): Arabic (right to left, Arabic digits) or English.
// Every visible word goes through T('عربي', 'English'); numbers, times and dates through `fmt`.
// App remounts everything when the language changes, so plain calls are enough (no hooks).
import { useIsland } from './store';

export type Lang = 'ar' | 'en';
export const lang = (): Lang => (useIsland.getState().prefs.lang === 'en' ? 'en' : 'ar');
export const T = (ar: string, en: string) => (lang() === 'en' ? en : ar);
export const dir = (): 'rtl' | 'ltr' => (lang() === 'en' ? 'ltr' : 'rtl');
/** CSS direction words for gradients that run from the start of the line */
export const towardEnd = () => (lang() === 'en' ? 'right' : 'left');

const cache = new Map<string, Intl.NumberFormat | Intl.DateTimeFormat>();
function num(opts: Intl.NumberFormatOptions = {}) {
  const k = `n${lang()}${JSON.stringify(opts)}`;
  if (!cache.has(k)) cache.set(k, new Intl.NumberFormat(lang() === 'en' ? 'en-US' : 'ar-EG', opts));
  return cache.get(k) as Intl.NumberFormat;
}
function date(opts: Intl.DateTimeFormatOptions, calendar = '') {
  const k = `d${lang()}${calendar}${JSON.stringify(opts)}`;
  const loc = (lang() === 'en' ? 'en-US' : 'ar-EG') + (calendar ? `-u-ca-${calendar}` : '');
  if (!cache.has(k)) cache.set(k, new Intl.DateTimeFormat(loc, opts));
  return cache.get(k) as Intl.DateTimeFormat;
}

export const fmt = {
  num: (n: number) => num().format(n),
  num2: (n: number) => num({ minimumIntegerDigits: 2 }).format(n),
  pct: (n: number) => (lang() === 'en' ? `${num().format(Math.round(n))}%` : `${num().format(Math.round(n))}٪`),
  clock: (t: number | Date) => date({ hour: 'numeric', minute: '2-digit' }).format(t),
  /** "Saturday, November 7" */
  date: (t: number | Date) => date({ weekday: 'long', day: 'numeric', month: 'long' }).format(t),
  hijri: (t: number | Date, year = false) => date(year ? { day: 'numeric', month: 'long', year: 'numeric' } : { day: 'numeric', month: 'long' }, 'islamic-umalqura').format(t),
  /** 3:05 (minutes:seconds) */
  mmss: (s: number) => { s = Math.max(0, Math.floor(s || 0)); return `${num().format(Math.floor(s / 60))}:${num({ minimumIntegerDigits: 2 }).format(s % 60)}`; },
  bytes: (b: number) => {
    const [g, m, k] = lang() === 'en' ? ['GB', 'MB', 'KB'] : ['ج.ب', 'م.ب', 'ك.ب'];
    return b >= 1e9 ? `${num().format(+(b / 1e9).toFixed(1))} ${g}` : b >= 1e6 ? `${num().format(+(b / 1e6).toFixed(1))} ${m}` : `${num().format(Math.round(b / 1e3))} ${k}`;
  },
  /** a speed: "4.2 MB/s" */
  speed: (b: number) => `${fmt.bytes(b)}${lang() === 'en' ? '/s' : '/ث'}`,
  /** time until something: "in 1 h 20 min", "now" */
  until: (ms: number) => {
    const m = Math.max(0, Math.round(ms / 60000));
    if (m < 1) return T('دلوقتي', 'now');
    const h = Math.floor(m / 60), r = m % 60;
    const span = h ? `${num().format(h)} ${T('س', 'h')}` + (r ? ` ${num().format(r)} ${T('د', 'min')}` : '') : `${num().format(r)} ${T('د', 'min')}`;
    return T(`بعد ${span}`, `in ${span}`);
  },
  /** a length of time: "1 h 20 min" */
  span: (min: number) => {
    const m = Math.max(1, Math.round(min)), h = Math.floor(m / 60), r = m % 60;
    return h ? `${num().format(h)} ${T('س', 'h')}` + (r ? ` ${num().format(r)} ${T('د', 'min')}` : '') : `${num().format(r)} ${T('د', 'min')}`;
  },
};

export const PRAYER = (k: string) => ({
  fajr: T('الفجر', 'Fajr'), sunrise: T('الشروق', 'Sunrise'), dhuhr: T('الظهر', 'Dhuhr'),
  asr: T('العصر', 'Asr'), maghrib: T('المغرب', 'Maghrib'), isha: T('العشاء', 'Isha'),
} as Record<string, string>)[k] || '';

export const WEATHER = (c: number) => c === 0 ? T('صافي', 'Clear') : c <= 2 ? T('غائم جزئيًا', 'Partly cloudy') : c === 3 ? T('غائم', 'Cloudy')
  : c <= 48 ? T('شبورة', 'Fog') : c <= 57 ? T('رذاذ', 'Drizzle') : c <= 67 ? T('مطر', 'Rain') : c <= 77 ? T('تلج', 'Snow')
  : c <= 82 ? T('زخات مطر', 'Showers') : c <= 86 ? T('زخات تلج', 'Snow showers') : T('عاصفة رعدية', 'Thunderstorm');
