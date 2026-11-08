// Interface 7: your day (design C, "the sky"): the prayer tile is the sky at this hour with the sun or
// the moon on its arc; focus as a ring, water as a glass that fills; the next meeting; the prayer times
// page and the Qur'an radio page.
import { motion } from 'motion/react';
import { ArrowLeft, ArrowRight, Pause, Play, Plus, Radio, Search, Square, Timer, Video } from 'lucide-react';
import { useState } from 'react';
import { bridge } from '../bridge';
import { borrowKeyboard, showPage } from '../panel';
import { radioPlay, radioStop, radioVolume, radioVolumeNow } from '../radio';
import { useIsland, type IslandStore } from '../store';
import { spring } from '../motion';
import type { PrayerTimes } from '../types';
import { mmss, useNow } from './CompactIsland';
import { PRAYER, T, fmt, lang } from '../i18n';

const nf = { format: fmt.num };
const clockFmt = { format: fmt.clock };
const FIVE = ['fajr', 'dhuhr', 'asr', 'maghrib', 'isha'] as const;
const SIX = ['fajr', 'sunrise', 'dhuhr', 'asr', 'maghrib', 'isha'] as const;
const GOLD = 'var(--color-gold)', TEAL = 'var(--color-accent)', WATER = '#5AA9FF';
const tile = 'rounded-[18px] bg-white/[.04] ring-1 ring-white/5';
/** "in 1 h 20 min", "now" (in the island's language) */
export const until = fmt.until;

export function nextPrayer(times: PrayerTimes, t = Date.now()) {
  for (let i = 0; i < FIVE.length; i++) {
    if (times[FIVE[i]] > t) return { key: FIVE[i] as string, at: times[FIVE[i]] };
  }
  return { key: 'fajr', at: times.next_fajr };
}

/** the sky at time t: its colours, and the sun or moon's place on the arc (0 = rising, 1 = setting) */
export function skyAt(times: PrayerTimes, t = Date.now()) {
  const { fajr, sunrise, asr, maghrib, isha, next_fajr } = times;
  const frac = (a: number, b: number) => Math.max(0, Math.min(1, (t - a) / (b - a)));
  if (t >= sunrise && t < maghrib) return {
    body: 'sun' as const, pos: frac(sunrise, maghrib),
    sky: t < asr ? 'linear-gradient(180deg, #2B6CB0, #5BA3D9 60%, #A8D4F0)' : 'linear-gradient(180deg, #2E64A8, #6FA6D6 50%, #F6C177)',
  };
  if (t >= fajr && t < sunrise) return { body: 'sun' as const, pos: 0, sky: 'linear-gradient(180deg, #1B1F4B, #6B3F7A 55%, #F09A6B)' };
  const night = t >= maghrib ? frac(maghrib, next_fajr) : frac(maghrib - 864e5, fajr);
  return {
    body: 'moon' as const, pos: night,
    sky: t >= maghrib && t < isha ? 'linear-gradient(180deg, #1A1440, #5B2A6E 50%, #E06D4F)' : 'linear-gradient(180deg, #070B1F, #14204A 70%, #26305E)',
  };
}

/** a point on the arc (a quadratic curve from the start side to the end side), as % of the tile */
function arcPoint(p: number) {
  const x0 = 96, x1 = 50, x2 = 4, y0 = 92, y1 = -18, y2 = 92;   // in %: rises on the right (the start in Arabic)
  const q = 1 - p, x = q * q * x0 + 2 * q * p * x1 + p * p * x2;
  return { x: lang() === 'en' ? 100 - x : x, y: q * q * y0 + 2 * q * p * y1 + p * p * y2 };
}

/** the sky: the time, the date, the next prayer. Slim while music plays; tall on the prayer page. */
export function SkyTile({ size = 'normal' }: { size?: 'slim' | 'normal' | 'tall' }) {
  const now = useNow(30_000);
  const prayer = useIsland(s => s.prayer)!;
  const weather = useIsland(s => (s.prefs.weather !== false ? s.weather : null));
  const sky = skyAt(prayer.times, now), np = nextPrayer(prayer.times, now);
  const pt = arcPoint(sky.pos);
  const h = size === 'slim' ? 56 : size === 'tall' ? 150 : 112;
  const orb = sky.body === 'sun'
    ? { background: 'radial-gradient(#FFF6D5, #FFD36B 60%, transparent 72%)', boxShadow: '0 0 30px #FFD36B' }
    : { background: 'radial-gradient(#F4F6FF, #C9D3F5 55%, transparent 72%)', boxShadow: '0 0 22px #C9D3F588' };
  const next = <><b>{PRAYER(np.key)} {clockFmt.format(np.at)}</b> <span className="opacity-85">· {until(np.at - now)}</span></>;
  return (
    <motion.button type="button" onClick={() => showPage('prayer')} aria-label={`${T('مواقيت الصلاة، ', 'Prayer times, ')}${PRAYER(np.key)} ${until(np.at - now)}`}
                   variants={{ hide: { opacity: 0, y: -6 }, show: { opacity: 1, y: 0, transition: spring.content } }}
                   className="relative col-span-3 block w-full overflow-hidden rounded-[22px] text-start text-white ring-1 ring-white/10"
                   style={{ height: h, background: sky.sky, transition: 'background 2s' }}>
      {size !== 'slim' && (
        <svg className="absolute inset-0 size-full" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path d="M96 92 Q50 -18 4 92" fill="none" stroke="rgba(255,255,255,.4)" strokeWidth=".6" strokeDasharray="1.5 2" vectorEffect="non-scaling-stroke" />
        </svg>
      )}
      <span aria-hidden="true" className={`absolute -translate-x-1/2 -translate-y-1/2 rounded-full transition-all duration-1000 ${size === 'slim' ? 'size-5 opacity-60' : 'size-7'}`}
            style={{ ...orb, left: `${size === 'slim' ? (lang() === 'en' ? 4 + sky.pos * 92 : 100 - (4 + sky.pos * 92)) : pt.x}%`, top: size === 'slim' ? '50%' : `${Math.min(76, Math.max(14, pt.y))}%` }} />
      {size === 'slim' ? (
        <span className="absolute inset-0 flex items-center justify-between bg-black/25 px-4">
          <span className="font-display text-[22px] font-bold tabular-nums">{clockFmt.format(now)}</span>
          <span className="text-[12px]">{next}</span>
        </span>
      ) : (
        <>
          <span className="absolute top-2.5 start-4 flex flex-col">
            <span className="font-display text-[26px] font-bold leading-tight tabular-nums">{clockFmt.format(now)}</span>
            <span className="text-[11.5px] opacity-90">{fmt.date(now)} · {fmt.hijri(now)}</span>
          </span>
          {weather && <span className="absolute top-3 end-4 text-[12px] opacity-90">{nf.format(weather.temp)}°</span>}
          <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/50 to-transparent px-4 pt-6 pb-2.5 text-[12.5px]">
            {next}{size === 'tall' && prayer.city && <span className="opacity-85"> · {prayer.city}</span>}
          </span>
        </>
      )}
    </motion.button>
  );
}

function Ring({ v, color, children }: { v: number; color: string; children: React.ReactNode }) {
  const k = 2 * Math.PI * 15;
  return (
    <span className="relative grid size-9 shrink-0 place-items-center">
      <svg className="absolute inset-0 -rotate-90" viewBox="0 0 36 36" aria-hidden="true">
        <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="3" />
        <motion.circle cx="18" cy="18" r="15" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeDasharray={k}
                       initial={false} animate={{ strokeDashoffset: k * (1 - v) }} transition={{ duration: 0.9, ease: 'linear' }} />
      </svg>
      {children}
    </span>
  );
}
const Mini = ({ icon: I, label, color, solid, onClick }: { icon: typeof Play; label: string; color: string; solid?: boolean; onClick: () => void }) => (
  <motion.button type="button" aria-label={label} title={label} onClick={onClick} whileTap={{ scale: 0.88 }} transition={spring.micro}
                 className="grid size-7 shrink-0 place-items-center rounded-full"
                 style={solid ? { background: color, color: '#050507' } : { background: 'rgba(255,255,255,.07)', color }}>
    <I className="size-3.5" fill={I === Plus ? 'none' : 'currentColor'} />
  </motion.button>
);
const item = { hide: { opacity: 0, y: -6 }, show: { opacity: 1, y: 0, transition: spring.content } };

function FocusTile() {
  const f = useIsland(s => s.focus);
  const running = !!f.phase && !!f.ends_at;
  const now = useNow(running ? 1000 : 60_000);
  const cmd = (c: 'start' | 'pause' | 'resume' | 'stop') => () => bridge.send({ t: 'focus', cmd: c });
  const left = !f.phase ? 0 : f.ends_at ? Math.max(0, (f.ends_at - now) / 1000) : f.paused_left || 0;
  const rest = f.phase && f.phase !== 'focus', color = rest ? GOLD : TEAL;
  const name = !f.phase ? T('تركيز', 'Focus') : f.phase === 'focus' ? `${T('تركيز', 'Focus')} ${nf.format((f.round || 0) + 1)}` : f.phase === 'long' ? T('راحة طويلة', 'Long break') : T('راحة', 'Break');
  return (
    <motion.div variants={item} className={`${tile} flex items-center gap-2 px-2.5 py-2.5`} title={f.phase ? (running ? T('شغال', 'Running') : T('متوقف', 'Paused')) : undefined}>
      <Ring v={f.phase && f.total ? left / f.total : 0} color={color}>
        {f.phase ? <span className="text-[9.5px] font-bold tabular-nums">{mmss(left)}</span> : <Timer className="size-4" style={{ color: TEAL }} />}
      </Ring>
      <span className="min-w-0 flex-1 text-[12px] leading-tight">
        <b className="block whitespace-nowrap">{name}</b>
        {!f.phase ? <span className="text-ink-2">{nf.format(f.focus_min || 25)} {T('د', 'min')}</span> : !running && <span style={{ color }}>{T('متوقف', 'Paused')}</span>}
      </span>
      {!f.phase ? <Mini icon={Play} label={T('ابدأ جلسة تركيز', 'Start a focus session')} color={TEAL} solid onClick={cmd('start')} />
        : <span className="flex gap-1">
            {running ? <Mini icon={Pause} label={T('وقّف مؤقتًا', 'Pause')} color={color} onClick={cmd('pause')} /> : <Mini icon={Play} label={T('كمّل', 'Resume')} color={color} onClick={cmd('resume')} />}
            <Mini icon={Square} label={T('إنهاء الجلسة', 'End the session')} color={color} onClick={cmd('stop')} />
          </span>}
    </motion.div>
  );
}

function WaterTile() {
  const w = useIsland(s => s.water);
  if (!w) return null;
  const add = () => {
    const s = useIsland.getState(), cur = s.water!;
    const reached = cur.count < cur.goal && cur.count + 1 >= cur.goal && !!s.prefs.celebrate;
    useIsland.setState({ water: { ...cur, count: cur.count + 1 }, ...(reached ? { celebrateAt: Date.now() } : {}) });   // at once
    bridge.send({ t: 'water', cmd: 'add' });
  };
  const v = w.goal ? Math.min(1, w.count / w.goal) : 0;
  return (
    <motion.div variants={item} className={`${tile} flex items-center gap-3 px-3 py-2.5`}>
      <span className="relative h-10 w-7 shrink-0 overflow-hidden rounded-t-[3px] rounded-b-[8px] ring-2 ring-white/25" role="meter" aria-label={T('المياه', 'Water')}
            aria-valuemin={0} aria-valuemax={w.goal} aria-valuenow={w.count}>
        <motion.span className="absolute inset-x-0 bottom-0" style={{ background: `linear-gradient(${WATER}, #2F6FD0)` }}
                     initial={false} animate={{ height: `${v * 100}%` }} transition={spring.content} />
      </span>
      <span className="min-w-0 flex-1 text-[12px] leading-tight"><b className="block">{nf.format(w.count)} {T('من', 'of')} {nf.format(w.goal)}</b><span className="text-ink-2">{T('كوبايات', 'glasses')}</span></span>
      <Mini icon={Plus} label={T('شربت كوباية', 'I drank a glass')} color={WATER} solid onClick={add} />
    </motion.div>
  );
}

function nextMeeting(s: IslandStore, t: number) {
  return s.meetings.find(e => e.end > t && e.start - t < 3 * 3600e3) || null;
}
function MeetingRow() {
  const now = useNow(30_000);
  const mt = useIsland(s => nextMeeting(s, now));
  if (!mt) return null;
  const soon = mt.start - now;
  return (
    <motion.div variants={item} className={`${tile} col-span-3 flex items-center gap-3 px-3 py-2.5`}>
      <Video className="size-4 shrink-0" style={{ color: '#7FA8FF' }} aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate text-[12.5px]"><bdi>{mt.title}</bdi> — {soon > 0 ? <>{clockFmt.format(mt.start)} <span className="text-ink-3">({until(soon)})</span></> : T('شغال دلوقتي', 'happening now')}</span>
      {mt.has_link && soon < 15 * 60e3 && (
        <button type="button" onClick={() => bridge.send({ t: 'meeting_join', id: mt.id })}
                className="rounded-full bg-[#7FA8FF] px-3 py-1 text-[11.5px] font-semibold text-island">{T('انضم', 'Join')}</button>
      )}
    </motion.div>
  );
}

/** the day's tiles in the panel's home (the sky goes first, on its own) */
export function DayTiles() {
  const water = useIsland(s => !!s.water);
  return (
    <>
      <div className={`col-span-3 grid gap-2.5 ${water ? 'grid-cols-2' : 'grid-cols-1'}`}><FocusTile /><WaterTile /></div>
      <MeetingRow />
    </>
  );
}

const Back = ({ to }: { to: 'home' | 'prayer' }) => (
  <button type="button" onClick={() => useIsland.getState().setPanel({ page: to })} aria-label={T('رجوع', 'Back')} title={T('رجوع', 'Back')}
          className="grid size-8 place-items-center rounded-full bg-white/[.07] hover:bg-white/[.12]">{lang() === 'en' ? <ArrowLeft className="size-4" /> : <ArrowRight className="size-4" />}</button>
);

export function PrayerPage() {
  const now = useNow(30_000);
  const prayer = useIsland(s => s.prayer);
  if (!prayer) return null;
  const np = nextPrayer(prayer.times, now);
  return (
    <motion.div className="flex flex-col gap-3" variants={{ show: { transition: { staggerChildren: 0.03 } } }} initial="hide" animate="show">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2"><Back to="home" /><b className="font-display text-[15px]">{T('مواقيت الصلاة', 'Prayer times')}</b></span>
        <button type="button" onClick={() => showPage('radio')} className="flex items-center gap-1.5 rounded-full bg-white/[.07] px-3 py-1.5 text-[12px] hover:bg-white/[.12]">
          <Radio className="size-3.5 text-[#7BD88F]" />{T('إذاعة القرآن', 'Quran radio')}
        </button>
      </div>
      <SkyTile size="tall" />
      <div className="grid grid-cols-6 gap-1 text-center">
        {SIX.map(k => {
          const at = prayer.times[k], next = np.key === k && np.at === at, past = !next && at < now;
          return (
            <motion.span key={k} variants={item} className={`flex flex-col gap-0.5 rounded-[12px] py-2 ${past ? 'opacity-40' : ''}`}
                         style={next ? { background: 'color-mix(in srgb, var(--color-gold) 14%, transparent)', color: GOLD } : undefined}>
              <span className="text-[10.5px]">{PRAYER(k)}</span><b className="text-[11.5px]">{clockFmt.format(at)}</b>
              {next && <span className="text-[9.5px]">{until(at - now)}</span>}
            </motion.span>
          );
        })}
      </div>
    </motion.div>
  );
}

const GREEN = '#7BD88F';
export function RadioPage() {
  const r = useIsland(s => s.radio);
  const [q, setQ] = useState('');
  const [vol, setVol] = useState(radioVolumeNow);
  const list = r.stations.filter(s => !q.trim() || s.name.includes(q.trim())).slice(0, 60);
  const state = r.msg || (r.playing ? T('بث مباشر', 'Live') : r.url ? T('واقفة', 'Stopped') : '');
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2"><Back to="prayer" /><b className="font-display text-[15px]">{T('إذاعة القرآن', 'Quran radio')}</b></div>
      <div className="relative flex items-center gap-3 overflow-hidden rounded-[20px] p-3.5 ring-1 ring-[#7BD88F33]" style={{ background: 'linear-gradient(135deg, #0F3D2E, #1F6F50)' }}>
        <motion.button type="button" disabled={!r.url} onClick={() => (r.playing ? radioStop() : radioPlay())} whileTap={{ scale: 0.9 }} transition={spring.micro}
                       aria-label={r.playing ? T('وقّف الإذاعة', 'Stop the radio') : T('شغّل الإذاعة', 'Play the radio')} title={r.playing ? T('وقّف الإذاعة', 'Stop the radio') : T('شغّل الإذاعة', 'Play the radio')}
                       className="grid size-12 shrink-0 place-items-center rounded-full text-island disabled:opacity-40" style={{ background: GREEN, boxShadow: `0 6px 22px ${GREEN}66` }}>
          {r.playing ? <Pause className="size-5" fill="currentColor" /> : <Play className="size-5 translate-x-px" fill="currentColor" />}
        </motion.button>
        <span className="min-w-0 flex-1">
          <b className="block truncate text-[15px]"><bdi>{r.name || T('اختار قارئ من تحت', 'Pick a reciter below')}</bdi></b>
          <span className="flex items-center gap-1.5 text-[11.5px]" style={{ color: GREEN }} aria-live="polite">{r.playing && !r.msg && <i className="yobi-pulse size-1.5 rounded-full" style={{ background: GREEN }} />}{state}</span>
        </span>
        {r.playing && <span className="flex h-6 items-end gap-[3px]" aria-hidden="true">{[0.9, 0.6, 1.1, 0.75, 1, 0.65, 0.85].map((d, i) => (
          <i key={i} className="yobi-bar h-full w-[3px] rounded-full" style={{ background: GREEN, transformOrigin: 'bottom', animationDuration: `${d}s`, animationDelay: `${-i * 0.15}s` }} />
        ))}</span>}
      </div>
      <label className="flex items-center gap-3 px-1 text-[11.5px] text-ink-2">{T('الصوت', 'Volume')}
        <input type="range" min={0} max={100} value={vol} dir="ltr" aria-label={T('صوت الإذاعة', 'Radio volume')} className="flex-1 accent-[#7BD88F]"
               onChange={e => { setVol(+e.target.value); radioVolume(+e.target.value, false); }}
               onPointerUp={e => radioVolume(+(e.target as HTMLInputElement).value, true)} onKeyUp={e => radioVolume(+(e.target as HTMLInputElement).value, true)} />
      </label>
      <label className="flex items-center gap-2 rounded-full bg-white/[.06] px-3.5 py-2 text-[12.5px] focus-within:ring-1 focus-within:ring-[#7BD88F66]">
        <Search className="size-4 text-ink-3" aria-hidden="true" />
        <input dir="auto" value={q} onChange={e => setQ(e.target.value)} onPointerDown={borrowKeyboard} onFocus={borrowKeyboard}
               placeholder={T('دوّر على قارئ…', 'Find a reciter…')} aria-label={T('دوّر على قارئ', 'Find a reciter')} className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-3" />
      </label>
      <div className="grid max-h-[176px] gap-1 overflow-y-auto pe-0.5">
        {r.error && !r.stations.length ? <p className="m-0 px-3 py-2 text-[12.5px] text-ink-2">{T('مش قادر أجيب القرّاء دلوقتي، جرّب تاني بعد شوية', 'Can’t load the reciters right now, try again in a bit')}</p>
          : !r.stations.length ? <p className="m-0 px-3 py-2 text-[12.5px] text-ink-3">{T('بجيب القرّاء…', 'Loading reciters…')}</p>
          : list.map(s => {
            const cur = s.url === r.url;
            return (
              <button key={s.url} type="button" dir="auto" onClick={() => radioPlay(s)} aria-current={cur || undefined}
                      className="flex items-center justify-between rounded-[12px] px-3 py-2 text-start text-[13px] hover:bg-white/[.07]"
                      style={cur ? { background: `${GREEN}1a`, color: GREEN } : { background: 'rgba(255,255,255,.03)' }}>
                <bdi>{s.name}</bdi>{cur && <Radio className="size-4" aria-hidden="true" />}
              </button>
            );
          })}
      </div>
    </div>
  );
}

