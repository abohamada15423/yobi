// Interface 6: a notice (design B, "the wave"): the kind's colour washes in from the start like the
// HUD's liquid, a big faint icon sits behind, and a thin line drains as the notice's time runs out.
import { AnimatePresence, motion } from 'motion/react';
import { useLayoutEffect, useRef } from 'react';
import { useIsland } from '../store';
import { noticeAction } from '../notices';
import { spring, stagger } from '../motion';
import { dir, towardEnd } from '../i18n';

const mix = (c: string, p: number) => `color-mix(in srgb, ${c} ${p}%, transparent)`;

/** time left: a line in the notice's colour that drains, and stops while the pointer holds it */
function Left() {
  const n = useIsland(s => s.notice)!;
  const left = n.paused ? n.left : Math.max(0, n.until - Date.now());
  const frac = Math.min(1, left / n.total);
  return (
    <span className="absolute inset-x-6 bottom-[5px] h-[2px] rounded-pill bg-white/8" aria-hidden="true">
      <motion.span key={`${n.at}-${n.paused}`} className="absolute inset-y-0 start-0 rounded-pill"
                   style={{ background: n.look.color, boxShadow: `0 0 8px ${n.look.color}` }}
                   initial={{ width: `${frac * 100}%` }} animate={{ width: n.paused ? `${frac * 100}%` : '0%' }}
                   transition={n.paused ? { duration: 0 } : { duration: left / 1000, ease: 'linear' }} />
    </span>
  );
}

function Body() {
  const n = useIsland(s => s.notice)!;
  const l = n.look;
  const item = { hide: { opacity: 0, y: -6 }, show: { opacity: 1, y: 0, transition: spring.content } };
  const center = l.ayah;
  return (
    <motion.div className={`relative flex flex-col gap-1.5 px-5 pt-4 pb-5 ${center ? 'items-center text-center' : ''}`}
                variants={{ show: { transition: stagger } }} initial="hide" animate="show">
      <motion.span variants={item} className="flex items-center gap-1.5 text-[11.5px] font-semibold" style={{ color: l.color }}>
        <l.icon className="size-4" aria-hidden="true" /><bdi>{l.kind}</bdi>
      </motion.span>
      {(l.text || l.swatch || l.thumb) && (
        <motion.div variants={item} className="flex items-center gap-3">
          {l.swatch && <span className="size-8 shrink-0 rounded-[10px] ring-1 ring-white/15" style={{ background: l.swatch }} />}
          {l.thumb && <img src={l.thumb} alt="" className="max-h-24 max-w-40 rounded-[10px] object-cover ring-1 ring-white/10" />}
          {l.text && <p className={`m-0 min-w-0 break-words ${l.ayah ? 'font-quran text-[24px] leading-[1.9]' : 'font-display text-[18px] font-bold leading-snug'}`}><bdi>{l.text}</bdi></p>}
        </motion.div>
      )}
      {l.sub && <motion.p variants={item} className="m-0 text-[12px] text-ink-2">{l.sub.split('\n').map((line, i) => <span key={i} className="block"><bdi>{line}</bdi></span>)}</motion.p>}
      {l.buttons.length > 0 && (
        <motion.div variants={item} className="mt-1.5 flex flex-wrap gap-2">
          {l.buttons.map(([label, action], i) => (
            <motion.button key={action} type="button" onClick={() => noticeAction(action)}
                           whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.94 }} transition={spring.micro}
                           className={`h-8 rounded-pill px-3.5 text-[12px] font-semibold ${action === 'dismiss' ? 'text-ink-2 hover:text-ink' : i === 0 ? 'text-island' : 'bg-white/[.07] hover:bg-white/[.12]'}`}
                           style={i === 0 && action !== 'dismiss' ? { background: l.color } : undefined}>{label}</motion.button>
          ))}
        </motion.div>
      )}
    </motion.div>
  );
}

/** the notice on screen. It measures itself and tells the island how big to be. */
export function Notice({ onSize }: { onSize: (w: number, h: number) => void }) {
  const n = useIsland(s => s.notice);
  const box = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => onSize(Math.ceil(el.offsetWidth), Math.ceil(el.offsetHeight)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [onSize]);
  if (!n) return null;
  const l = n.look;
  return (
    <div ref={box} dir={dir()} role="status" aria-live="polite" className="absolute top-0 left-1/2 w-[380px] -translate-x-1/2 overflow-hidden">
      <span className="pointer-events-none absolute inset-0" style={{ background: `linear-gradient(to ${towardEnd()}, ${mix(l.color, 26)}, transparent 70%)` }} />
      <l.icon className="pointer-events-none absolute -bottom-6 -left-4 size-32 opacity-[.07]" style={{ color: l.color }} aria-hidden="true" />
      {/* a notice replacing another drops in */}
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.div key={n.at} initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 8 }} transition={spring.content}>
          <Body />
        </motion.div>
      </AnimatePresence>
      <Left />
    </div>
  );
}
