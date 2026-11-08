// Interface 1: the compact island and its live activities (design A, "two parts"):
// one thing at the leading edge, one at the trailing edge, like a phone's island.
import { AnimatePresence, motion, useReducedMotionConfig } from 'motion/react';
import { Download, Music, Pause, Timer } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { compactView, edgeOf, hasDots, useIsland, type Compact } from '../store';
import { spring } from '../motion';
import { useSongColor } from '../songColor';
import { T, dir, fmt } from '../i18n';
import { InfoColumn, InfoRow } from './IdleInfo';

/** each compact view's size; the privacy dots add a little room at the trailing edge */
const SIZE: Record<Compact, [number, number]> = {
  thin: [64, 6], idle: [96, 28], clock: [112, 28], info: [360, 28], focus: [176, 32], music: [196, 32], download: [212, 32],
};
/** the same views as a strip on a side edge of the screen (Nova's vertical island): narrow and tall */
const SIDE: Record<Compact, [number, number]> = {
  thin: [6, 64], idle: [40, 40], clock: [52, 50], info: [56, 236], focus: [56, 84], music: [56, 84], download: [56, 84],
};
const DOTS_W = 18;
export function compactSize(view: Compact, dots: boolean, edge: 'left' | 'right' | null = null): [number, number] {
  const more = dots && view !== 'thin' ? DOTS_W : 0;
  if (edge) { const [w, h] = SIDE[view]; return [w, h + more]; }
  const [w, h] = SIZE[view];
  return [w + more, h];
}

export const mmss = fmt.mmss;
export const fmtBytes = fmt.bytes;

/** re-render every `ms` while mounted; nothing ticks when the view that needs it is gone */
export function useNow(ms: number) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(id); }, [ms]);
  return now;
}

/** short: without AM/PM, for the narrow side strip */
function Clock({ short = false }: { short?: boolean }) {
  const now = useNow(10_000);
  const t = fmt.clock(now);
  return <span className="w-full text-center font-display text-[12.5px] font-semibold tabular-nums">{short ? t.replace(/\s?(AM|PM|ص|م)$/, '') : t}</span>;
}

function FocusLive() {
  const focus = useIsland(s => s.focus);
  const now = useNow(1000);
  const left = focus.ends_at ? Math.max(0, (focus.ends_at - now) / 1000) : focus.paused_left || 0;
  const paused = !focus.ends_at;
  const rest = focus.phase !== 'focus';
  const Icon = paused ? Pause : Timer;
  return (
    <>
      <span className="flex items-center gap-1.5">
        <Icon className={`size-4 ${rest ? 'text-gold' : 'text-accent'}`} strokeWidth={2.2} />
        <span className="text-[11px] text-ink-2">{paused ? T('متوقف', 'Paused') : rest ? T('راحة', 'Break') : T('تركيز', 'Focus')}</span>
      </span>
      <span className={`font-display text-[13px] font-semibold tabular-nums ${paused ? 'text-ink-2' : ''}`}>{mmss(left)}</span>
    </>
  );
}

/** five bars that dance; their height follows a loudness (the music's, or your voice) */
export function Bars({ level, color = 'var(--color-accent)' }: { level: number; color?: string }) {
  return (
    <span className="flex h-4 items-center gap-[2px] transition-transform duration-150 ease-out"
          style={{ transform: `scaleY(${0.5 + 0.5 * level})` }} aria-hidden="true">
      {[0.9, 0.7, 1.05, 0.8, 0.95].map((d, i) => (
        <i key={i} className="yobi-bar h-full w-[3px] rounded-pill"
           style={{ background: color, animationDuration: `${d}s`, animationDelay: `${-i * 0.17}s` }} />
      ))}
    </span>
  );
}
/** the music pill's wave takes the song's colour */
function Wave() {
  const level = useIsland(s => s.musicLevel);
  const art = useIsland(s => s.media.art);
  return <Bars level={level} color={useSongColor(art).c} />;
}

function MusicLive() {
  const media = useIsland(s => s.media);
  return (
    <>
      {media.art
        ? <img src={media.art} alt="" className="size-6 rounded-[8px] object-cover" />
        : <span className="grid size-6 place-items-center rounded-[8px] bg-fill-2"><Music className="size-3.5 text-ink-2" /></span>}
      <span className="sr-only">{[media.title, media.artist].filter(Boolean).join(' — ')}</span>
      <Wave />
    </>
  );
}

function DownloadLive({ side = false }: { side?: boolean }) {
  const dl = useIsland(s => s.downloads);
  if (side) {                                   // the narrow strip: the speed's number over its unit
    const [n, ...unit] = fmt.speed(dl[0]?.speed ?? 0).split(' ');
    return (
      <>
        <Download className="yobi-pulse size-4 text-accent" strokeWidth={2.2} />
        <span className="flex flex-col text-[10.5px] leading-tight tabular-nums text-ink-2"><b className="text-[12px] text-ink">{n}</b>{unit.join(' ')}</span>
      </>
    );
  }
  return (
    <>
      <span className="flex items-center gap-1">
        <Download className="yobi-pulse size-4 text-accent" strokeWidth={2.2} />
        {dl.length > 1 && <span className="text-[11px] tabular-nums text-ink-2">{fmt.num(dl.length)}</span>}
      </span>
      <span className="text-[12px] tabular-nums text-ink-2">{fmt.speed(dl[0]?.speed ?? 0)}</span>
    </>
  );
}

function Dots() {
  const { mic, cam } = useIsland(s => s.privacy);
  const edge = useIsland(edgeOf);
  if (!mic.length && !cam.length) return null;
  const sep = T('، ', ', ');
  const who = [mic.length ? `${T('المايك', 'Microphone')}: ${mic.join(sep)}` : '', cam.length ? `${T('الكاميرا', 'Camera')}: ${cam.join(sep)}` : ''].filter(Boolean).join('\n');
  return (
    <span className={`absolute flex items-center gap-1 ${edge ? 'inset-x-0 bottom-2 justify-center' : 'inset-y-0 end-2.5'}`} title={who} role="img" aria-label={who}>
      {mic.length > 0 && <i className="size-1.5 rounded-pill bg-gold" />}
      {cam.length > 0 && <i className="size-1.5 rounded-pill bg-accent" />}
    </span>
  );
}

/** a goal reached: one gold crest runs along the bottom edge, from the leading side */
export function Celebrate() {
  const at = useIsland(s => s.celebrateAt);
  const idle = useIsland(s => s.state === 'idle');
  const reduce = useReducedMotionConfig();
  const [run, setRun] = useState(0);
  useEffect(() => { if (at && idle && !reduce && Date.now() - at < 1500) setRun(at); }, [at]);   // only a new goal starts it
  return (
    <AnimatePresence>
      {run > 0 && (
        <motion.span key={run} className="pointer-events-none absolute bottom-0 h-[2px] w-1/3 rounded-pill"
          style={{ insetInlineStart: 0, background: 'linear-gradient(to right, transparent, var(--color-gold), transparent)', boxShadow: '0 0 10px var(--color-gold)' }}
          initial={{ x: dir() === 'rtl' ? '50%' : '-50%', opacity: 0 }} animate={{ x: dir() === 'rtl' ? '-250%' : '250%', opacity: [0, 1, 1, 0] }}
          transition={{ duration: 0.9, ease: 'easeInOut' }} onAnimationComplete={() => setRun(0)} />
      )}
    </AnimatePresence>
  );
}

const CONTENT: Record<Compact, () => ReactNode> = {
  thin: () => null, idle: () => null, clock: () => <Clock />, info: () => <InfoRow />,
  focus: () => <FocusLive />, music: () => <MusicLive />, download: () => <DownloadLive />,
};

/** the compact island's contents; the Capsule around it handles the size */
export function CompactIsland() {
  const view = useIsland(compactView);
  const dots = useIsland(hasDots);
  const edge = useIsland(edgeOf);
  if (edge) return (
    <div className="relative h-full" dir={dir()}>
      <AnimatePresence initial={false}>
        <motion.div key={view}
          className="absolute inset-x-0 top-0 flex flex-col items-center justify-center gap-1.5 text-center"
          style={{ bottom: dots ? DOTS_W : 0 }}
          initial={{ opacity: 0, scale: 0.9, filter: 'blur(3px)' }}
          animate={{ opacity: 1, scale: 1, filter: 'blur(0px)', transition: spring.content }}
          exit={{ opacity: 0, scale: 0.95, filter: 'blur(3px)', transition: { duration: 0.12 } }}>
          {view === 'info' ? <InfoColumn /> : view === 'clock' ? <Clock short /> : view === 'download' ? <DownloadLive side /> : CONTENT[view]()}
        </motion.div>
      </AnimatePresence>
      {view !== 'thin' && <Dots />}
    </div>
  );
  return (
    <div className="relative h-full" dir={dir()}>
      <AnimatePresence initial={false}>
        <motion.div key={view}
          className="absolute inset-0 flex items-center justify-between ps-2.5"
          style={{ paddingInlineEnd: dots ? 10 + DOTS_W : 10 }}
          initial={{ opacity: 0, scale: 0.9, filter: 'blur(3px)' }}
          animate={{ opacity: 1, scale: 1, filter: 'blur(0px)', transition: spring.content }}
          exit={{ opacity: 0, scale: 0.95, filter: 'blur(3px)', transition: { duration: 0.12 } }}>
          {CONTENT[view]()}
        </motion.div>
      </AnimatePresence>
      {view !== 'thin' && <Dots />}
    </div>
  );
}
