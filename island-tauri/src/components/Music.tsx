// Interface 4: music (design A of the second round, "the pulse"): the tile takes the song's colour,
// picked from its cover (the play button, the timeline, the cover's glow, the wave), and a live wave
// moves with the sound. A new song while you're not looking shows a short card in the island.
import { motion } from 'motion/react';
import { Music2, Pause, Play, SkipBack, SkipForward } from 'lucide-react';
import type { KeyboardEvent, MouseEvent } from 'react';
import { bridge } from '../bridge';
import { mediaPos, useIsland } from '../store';
import { spring } from '../motion';
import { songVars, useSongColor } from '../songColor';
import { Bars, mmss, useNow } from './CompactIsland';
import { T, dir } from '../i18n';

const get = () => useIsland.getState();
const glow = (pct: number) => `color-mix(in srgb, var(--song) ${pct}%, transparent)`;

/** send a command; the button answers at once, Python's next update corrects it if needed */
export function mediaCmd(cmd: 'toggle' | 'next' | 'prev' | 'seek', pos?: number) {
  bridge.send(pos === undefined ? { t: 'media', cmd } : { t: 'media', cmd, pos });
  const s = get();
  if (cmd === 'toggle') useIsland.setState({ media: { ...s.media, pos: mediaPos(s), playing: !s.media.playing }, mediaAt: Date.now() });
  if (cmd === 'seek' && pos !== undefined) useIsland.setState({ media: { ...s.media, pos }, mediaAt: Date.now() });
}

/** the cover blurred big behind, washed with the song's colour and darkened so the words read */
function Backdrop({ art }: { art?: string | null }) {
  return (
    <>
      {art && <img src={art} alt="" aria-hidden="true" className="pointer-events-none absolute inset-0 size-full scale-150 object-cover opacity-50 blur-2xl" />}
      <span className="pointer-events-none absolute inset-0"
            style={{ background: `linear-gradient(160deg, ${glow(art ? 22 : 16)}, rgba(0,0,0,${art ? 0.55 : 0.2}) 62%)` }} />
    </>
  );
}

function Cover({ art, size }: { art?: string | null; size: number }) {
  const shadow = `0 8px 28px ${glow(40)}, 0 0 0 1px rgba(255,255,255,.08)`;
  return art
    ? <img src={art} alt="" className="shrink-0 rounded-[14px] object-cover" style={{ width: size, height: size, boxShadow: shadow }} />
    : <span className="grid shrink-0 place-items-center rounded-[14px] bg-fill-2" style={{ width: size, height: size, boxShadow: shadow }}><Music2 className="size-5" style={{ color: 'var(--song)' }} /></span>;
}

function Words() {
  const m = useIsland(s => s.media);
  return (
    <div className="min-w-0 flex-1">
      <p dir="auto" className="m-0 truncate font-display text-[15px] font-bold">{m.title || T('من غير اسم', 'Untitled')}</p>
      <p dir="auto" className="m-0 truncate text-[12px]" style={{ color: 'color-mix(in srgb, var(--song) 75%, white)' }}>
        {[m.artist, m.app].filter(Boolean).join(' – ')}
      </p>
    </div>
  );
}

const WAVE = Array.from({ length: 28 }, (_, i) => 0.3 + 0.7 * Math.abs(Math.sin(i * 1.7) * Math.cos(i * 0.45)));
/** the live wave: thin bars in the song's colour, their height following the loudness; still when paused */
function Spectrum() {
  const level = useIsland(s => s.musicLevel);
  const playing = useIsland(s => !!s.media.playing);
  return (
    <span className="flex h-[26px] items-end justify-between transition-transform duration-150 ease-out" aria-hidden="true"
          style={{ transform: `scaleY(${playing ? 0.6 + 0.4 * level : 0.22})`, transformOrigin: 'bottom' }}>
      {WAVE.map((v, i) => (
        <i key={i} className="yobi-bar w-[3px] rounded-pill"
           style={{ height: `${v * 100}%`, transformOrigin: 'bottom', opacity: 0.55 + v * 0.45,
                    background: 'linear-gradient(var(--song), var(--song-dark))',
                    animationDuration: `${0.55 + (i % 5) * 0.13}s`, animationDelay: `${-i * 0.09}s`,
                    animationPlayState: playing ? 'running' : 'paused' }} />
      ))}
    </span>
  );
}

function Timeline() {
  const m = useIsland(s => s.media);
  useNow(m.playing ? 1000 : 60_000);                       // only ticks while playing
  const pos = mediaPos(get()), dur = m.dur || 0;
  if (!(dur > 0)) return null;
  const v = Math.min(1, pos / dur);
  const click = (e: MouseEvent<HTMLDivElement>) => {
    if (!m.seek) return;
    const r = e.currentTarget.getBoundingClientRect();
    mediaCmd('seek', Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * dur);
  };
  const keys = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!m.seek || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return;
    e.preventDefault();
    mediaCmd('seek', Math.max(0, Math.min(dur, pos + (e.key === 'ArrowRight' ? 10 : -10))));
  };
  const run = { duration: 0.95, ease: 'linear' } as const;
  return (
    <div dir="ltr" className="flex items-center gap-2 text-[10.5px] tabular-nums text-ink-2">
      <span>{mmss(pos)}</span>
      <div role="slider" tabIndex={m.seek ? 0 : -1} aria-label={T('مكان الأغنية', 'Position in the song')} aria-valuemin={0} aria-valuemax={100}
           aria-valuenow={Math.round(v * 100)} aria-disabled={!m.seek} onClick={click} onKeyDown={keys}
           className={`relative h-4 flex-1 ${m.seek ? 'cursor-pointer' : ''}`}>
        <span className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 rounded-pill bg-white/12">
          <motion.span className="absolute inset-y-0 left-0 rounded-pill" style={{ background: 'linear-gradient(90deg, var(--song-dark), var(--song))' }}
                       initial={false} animate={{ width: `${v * 100}%` }} transition={run} />
        </span>
        {m.seek && <motion.span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white shadow"
                                initial={false} animate={{ left: `${v * 100}%` }} transition={run} />}
      </div>
      <span>{mmss(dur)}</span>
    </div>
  );
}

function Controls() {
  const playing = useIsland(s => !!s.media.playing);
  const side = 'grid size-10 place-items-center rounded-pill hover:bg-white/10';
  return (
    <span dir="ltr" className="flex items-center justify-center gap-4">
      <motion.button type="button" aria-label={T('الأغنية اللي فاتت', 'Previous song')} title={T('الأغنية اللي فاتت', 'Previous song')} whileTap={{ scale: 0.88 }} transition={spring.micro}
                     className={side} onClick={() => mediaCmd('prev')}><SkipBack className="size-5" fill="currentColor" /></motion.button>
      <motion.button type="button" aria-label={playing ? T('وقّف', 'Pause') : T('شغّل', 'Play')} title={playing ? T('وقّف', 'Pause') : T('شغّل', 'Play')} whileHover={{ scale: 1.06 }} whileTap={{ scale: 0.9 }} transition={spring.micro}
                     className="grid size-12 place-items-center rounded-pill text-island"
                     style={{ background: 'var(--song)', boxShadow: `0 6px 22px ${glow(45)}` }} onClick={() => mediaCmd('toggle')}>
        {playing ? <Pause className="size-6" fill="currentColor" /> : <Play className="size-6 translate-x-px" fill="currentColor" />}
      </motion.button>
      <motion.button type="button" aria-label={T('الأغنية الجاية', 'Next song')} title={T('الأغنية الجاية', 'Next song')} whileTap={{ scale: 0.88 }} transition={spring.micro}
                     className={side} onClick={() => mediaCmd('next')}><SkipForward className="size-5" fill="currentColor" /></motion.button>
    </span>
  );
}

/** the player tile in the panel's home (only while something is playing or paused) */
export function MusicTile() {
  const has = useIsland(s => s.media.has);
  const art = useIsland(s => s.media.art);
  const col = useSongColor(art);
  if (!has) return null;
  return (
    <motion.div variants={{ hide: { opacity: 0, y: -6, scale: 0.97 }, show: { opacity: 1, y: 0, scale: 1, transition: spring.content } }}
                className="relative col-span-3 overflow-hidden rounded-[22px] bg-fill-1 p-3.5 ring-1 ring-white/10" style={songVars(col)}>
      <Backdrop art={art} />
      <div className="relative flex flex-col gap-3">
        <div className="flex items-center gap-3"><Cover art={art} size={64} /><Words /></div>
        <Spectrum />
        <Controls />
        <Timeline />
      </div>
    </motion.div>
  );
}

export const PEEK_SIZE: [number, number] = [330, 60];

/** the short card when the song changes */
export function TrackPeek() {
  const art = useIsland(s => s.media.art);
  const level = useIsland(s => s.musicLevel);
  const col = useSongColor(art);
  return (
    <motion.div dir={dir()} className="absolute inset-0 flex items-center gap-3 px-3" style={songVars(col)}
                initial={{ opacity: 0, filter: 'blur(3px)' }} animate={{ opacity: 1, filter: 'blur(0px)', transition: spring.content }}>
      <Backdrop art={art} />
      <span className="relative"><Cover art={art} size={40} /></span>
      <span className="relative flex min-w-0 flex-1"><Words /></span>
      <span className="relative"><Bars level={level} color={col.c} /></span>
    </motion.div>
  );
}
