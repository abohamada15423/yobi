// The island at rest, as in Nova: the time and date, the weather, CPU and RAM, and the next prayer
// with its countdown. A row in the top pill (Settings → What the island shows); a column on the
// side strip. Every piece shows only when its data is there.
import {
  Cloud, CloudDrizzle, CloudFog, CloudLightning, CloudMoon, CloudRain, CloudSnow, CloudSun, Moon, Sun, type LucideIcon,
} from 'lucide-react';
import { useIsland } from '../store';
import { nextPrayer } from './Day';
import { useNow } from './CompactIsland';
import { PRAYER, T, fmt, lang } from '../i18n';

export const WX_ICON = (c: number, day: boolean): LucideIcon => c === 0 ? (day ? Sun : Moon) : c <= 2 ? (day ? CloudSun : CloudMoon) : c === 3 ? Cloud
  : c <= 48 ? CloudFog : c <= 57 ? CloudDrizzle : c <= 67 ? CloudRain : c <= 77 ? CloudSnow : c <= 82 ? CloudRain : c <= 86 ? CloudSnow : CloudLightning;

/** time left, short: "12د" / "12m", "1:20" */
function short(ms: number) {
  const m = Math.max(0, Math.round(ms / 60000)), h = Math.floor(m / 60);
  return h ? `${fmt.num(h)}:${fmt.num2(m % 60)}` : `${fmt.num(m)}${T('د', 'm')}`;
}
/** a busy CPU or a full RAM shows in gold, then red */
const hot = (v: number) => (v >= 0.9 ? 'text-alert' : v >= 0.75 ? 'text-gold' : '');

function useInfo() {
  const now = useNow(10_000);
  const weather = useIsland(s => (s.prefs.weather !== false ? s.weather : null));
  const stats = useIsland(s => s.stats);
  const prayer = useIsland(s => s.prayer);
  const np = prayer ? nextPrayer(prayer.times, now) : null;
  const day = new Intl.DateTimeFormat(lang() === 'en' ? 'en-US' : 'ar-EG', { weekday: 'short', day: 'numeric' }).format(now);
  return { now, weather, stats, np, day, Icon: weather ? WX_ICON(weather.code, weather.is_day) : null };
}

/** the top pill: one row */
export function InfoRow() {
  const { now, weather, stats, np, day, Icon } = useInfo();
  const soft = 'text-[10.5px] text-ink-2', strong = 'font-display text-[12px] font-semibold tabular-nums';
  return (
    <span className="flex w-full items-center justify-between gap-2.5 whitespace-nowrap">
      <span className="flex items-baseline gap-1.5"><b className={strong}>{fmt.clock(now)}</b><span className={soft}>{day}</span></span>
      {weather && Icon && <span className="flex items-center gap-1"><Icon className="size-3.5 text-gold" aria-hidden="true" /><b className={strong}>{fmt.num(weather.temp)}°</b></span>}
      {stats && <span className="flex items-baseline gap-1"><span className={soft}>CPU</span><b className={`${strong} ${hot(stats.cpu)}`}>{fmt.pct(stats.cpu * 100)}</b></span>}
      {stats && <span className="flex items-baseline gap-1"><span className={soft}>RAM</span><b className={`${strong} ${hot(stats.ram)}`}>{fmt.pct(stats.ram * 100)}</b></span>}
      {np && <span className="flex items-baseline gap-1"><span className="text-[10.5px] text-gold">{PRAYER(np.key)}</span><b className={strong}>{short(np.at - now)}</b></span>}
    </span>
  );
}

/** the side strip: one column, top to bottom */
export function InfoColumn() {
  const { now, weather, stats, np, day, Icon } = useInfo();
  const soft = 'text-[10px] leading-tight text-ink-2', strong = 'font-display text-[12px] font-semibold leading-tight tabular-nums';
  const item = 'flex flex-col items-center gap-px';
  return (
    <span className="flex h-full w-full flex-col items-center justify-center gap-1.5 whitespace-nowrap">
      <b className={strong}>{fmt.clock(now).replace(/\s?(AM|PM|ص|م)$/, '')}</b>
      <span className={soft}>{day}</span>
      <i className="my-0.5 h-px w-5 bg-white/10" aria-hidden="true" />
      {weather && Icon && <span className={item}><Icon className="size-4 text-gold" aria-hidden="true" /><b className={strong}>{fmt.num(weather.temp)}°</b></span>}
      {stats && <span className={item}><span className={soft}>CPU</span><b className={`${strong} ${hot(stats.cpu)}`}>{fmt.pct(stats.cpu * 100)}</b></span>}
      {stats && <span className={item}><span className={soft}>RAM</span><b className={`${strong} ${hot(stats.ram)}`}>{fmt.pct(stats.ram * 100)}</b></span>}
      {np && <span className={item}><span className="text-[10px] leading-tight text-gold">{PRAYER(np.key)}</span><b className={strong}>{short(np.at - now)}</b></span>}
    </span>
  );
}
