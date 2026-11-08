// Interface 1: the compact island and its live activities (design A, "two parts"):
// one thing at the leading edge, one at the trailing edge, like a phone's island.
import { AnimatePresence, motion, useReducedMotionConfig } from 'motion/react';
import { Download, Music, Pause, Timer } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { compactView, hasDots, useIsland, type Compact } from '../store';
import { spring } from '../motion';
import { useSongColor } from '../songColor';
import { T, dir, fmt } from '../i18n';
import { InfoRow } from './IdleInfo';

/** each compact view's size; the privacy dots add a little room at the trailing edge */
const SIZE: Record<Compact, [number, number]> = {
  thin: [64, 6], idle: [96, 28], clock: [112, 28], info: [360, 28], focus: [176, 32], music: [196, 32], download: [212, 32],
};
const DOTS_W = 18;
export function compactSize(view: Compact, dots: boolean): [number, number] {
  const [w, h] = SIZE[view];
  return [w + (dots && view !== 'thin' ? DOTS_W : 0), h];
}

export const mmss = fmt.mmss;
export const fmtBytes = fmt.bytes;

/** re-render every `ms` while mounted; nothing ticks when the view that needs it is gone */
export function useNow(ms: number) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => { const id = setInterval(() => setNow(Date.now()), ms); return () => clearInterval(id); }, [ms]);
  return now;
}

function Clock() {
  const now = useNow(10_000);
  return <span className="w-full text-center font-display text-[12.5px] font-semibold tabular-nums">{fmt.clock(now)}</span>;
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

function DownloadLive() {
  const dl = useIsland(s => s.downloads);
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
  if (!mic.length && !cam.length) return null;
  const sep = T('، ', ', ');
  const who = [mic.length ? `${T('المايك', 'Microphone')}: ${mic.join(sep)}` : '', cam.length ? `${T('الكاميرا', 'Camera')}: ${cam.join(sep)}` : ''].filter(Boolean).join('\n');
  return (
    <span className="absolute inset-y-0 end-2.5 flex items-center gap-1" title={who} role="img" aria-label={who}>
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
