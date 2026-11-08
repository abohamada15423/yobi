// Interface 2: Yobi's turn (design A, "the line"): the words first, a small sign at the end
// (your voice, thinking, progress, done, failed). A question adds its buttons.
// Yobi's face is left out for now at the user's request; YobiFace.tsx stays for later.
import { motion, useAnimationControls, useReducedMotionConfig } from 'motion/react';
import { Check, X } from 'lucide-react';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useIsland } from '../store';
import { answer } from '../turn';
import { spring, stagger } from '../motion';
import { Bars } from './CompactIsland';
import { T, dir, fmt } from '../i18n';

/** the reply appears letter by letter; a longer version of the same reply (streaming) carries on */
function Typed({ text }: { text: string }) {
  const typing = useIsland(s => s.typing);
  const doneTyping = useIsland(s => s.doneTyping);
  const reduce = useReducedMotionConfig();
  const shown = useRef(0);
  const [n, setN] = useState(typing ? 0 : text.length);
  useEffect(() => {
    if (!typing || reduce) { shown.current = text.length; setN(text.length); if (typing) doneTyping(); return; }
    let last = performance.now(), raf = 0;
    const step = (t: number) => {
      const rate = Math.max(30, text.length / 3.5);                 // characters per second
      shown.current = Math.min(text.length, shown.current + (t - last) / 1000 * rate);
      last = t;
      setN(Math.floor(shown.current));
      if (shown.current >= text.length) doneTyping(); else raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [text, typing, reduce, doneTyping]);
  // the whole reply, invisible, sizes the island once, so it doesn't grow letter by letter
  return (
    <p dir="auto" className="relative m-0 font-display text-[14px] font-semibold leading-snug">
      <span className="invisible">{text}</span>
      <span className="absolute inset-0" aria-hidden="true">{text.slice(0, n)}</span>
    </p>
  );
}

function Dots() {
  return (
    <span className="flex gap-1" aria-hidden="true">
      {[0, 1, 2].map(i => <i key={i} className="yobi-pulse size-1.5 rounded-pill bg-ink-2" style={{ animationDuration: '1.2s', animationDelay: `${i * 0.2}s` }} />)}
    </span>
  );
}

/** progress 0..1 fills a ring; above 1 means "working, length unknown": a turning arc */
function Ring({ v }: { v: number }) {
  const c = 2 * Math.PI * 7, known = v <= 1;
  return (
    <svg className={`size-4 -rotate-90 ${known ? '' : 'yobi-spin'}`} viewBox="0 0 18 18" role="img" aria-label={known ? fmt.pct(v * 100) : T('شغال', 'Working')}>
      <circle cx="9" cy="9" r="7" fill="none" stroke="var(--color-line)" strokeWidth="2.2" />
      <circle cx="9" cy="9" r="7" fill="none" stroke="var(--color-accent)" strokeWidth="2.2" strokeLinecap="round"
        strokeDasharray={`${c * (known ? v : 0.3)} ${c}`} style={{ transition: 'stroke-dasharray .3s ease-out' }} />
    </svg>
  );
}

function Tail() {
  const state = useIsland(s => s.state);
  const level = useIsland(s => s.level);
  const progress = useIsland(s => s.progress);
  const sign =
    state === 'listening' || state === 'recording' || state === 'speaking' ? <Bars level={level} />
    : state === 'executing' && progress >= 0 ? <Ring v={progress} />
    : state === 'thinking' || state === 'account' || state === 'executing' ? <Dots />
    : state === 'success' ? <Check className="size-4 text-gold" strokeWidth={2.6} />
    : state === 'error' ? <X className="size-4 text-alert" strokeWidth={2.6} />
    : null;
  return sign && <motion.span key={state} className="flex shrink-0" initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={spring.micro}>{sign}</motion.span>;
}

function Choices() {
  const q = useIsland(s => s.question);
  const kbOpenAt = useIsland(s => s.kbOpenAt);
  const box = useRef<HTMLDivElement>(null);
  // the keyboard shortcut during a question puts the keyboard on its buttons
  useEffect(() => { if (kbOpenAt) box.current?.querySelector('button')?.focus(); }, [kbOpenAt]);
  if (!q) return null;
  return (
    <motion.div ref={box} className="flex flex-wrap gap-2" variants={{ show: { transition: stagger } }} initial="hide" animate="show">
      {q.options.map(([label, value], i) => {
        const decline = i > 0 && /^(no|none|cancel)$/i.test(String(value));
        return (
          <motion.button key={i} type="button" dir="auto"
            variants={{ hide: { opacity: 0, y: -4 }, show: { opacity: 1, y: 0, transition: spring.content } }}
            whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.94 }}
            onClick={() => answer(q.id, value)}
            className={`h-8 rounded-pill px-3.5 text-[12px] font-semibold ${i === 0 ? 'bg-gold text-island' : decline ? 'text-ink-2 hover:text-ink' : 'bg-fill-1 text-ink hover:bg-fill-2'}`}>
            {label}
          </motion.button>
        );
      })}
    </motion.div>
  );
}

/** Yobi's turn. It measures itself and tells the island how big to be. */
export function Turn({ onSize }: { onSize: (w: number, h: number) => void }) {
  const status = useIsland(s => s.status);
  const words = useIsland(s => s.words);
  const seq = useIsland(s => s.seq);
  const shakeAt = useIsland(s => s.shakeAt);
  const asking = useIsland(s => !!s.question);
  const reduce = useReducedMotionConfig();
  const shake = useAnimationControls();
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {          // something went wrong: a short shake, like a head saying no
    if (shakeAt && !reduce && Date.now() - shakeAt < 1000) void shake.start({ x: [0, -6, 6, -4, 4, -2, 0], transition: { duration: 0.45 } });
  }, [shakeAt, reduce, shake]);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => onSize(Math.ceil(el.offsetWidth), Math.ceil(el.offsetHeight)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [onSize]);

  return (
    <div ref={box} dir={dir()} className={`absolute top-0 left-1/2 flex w-max max-w-[460px] -translate-x-1/2 flex-col gap-2.5 px-4 py-2 ${asking ? 'min-w-[340px] pb-3' : 'min-w-[280px]'}`}>
      <motion.div animate={shake} className="flex min-h-7 items-center gap-3">
        <motion.div key={seq} className="min-w-0 flex-1" initial={{ opacity: 0, filter: 'blur(3px)' }} animate={{ opacity: 1, filter: 'blur(0px)' }} transition={spring.content}>
          {words ? <Typed text={words} /> : <p dir="auto" className="m-0 truncate text-[13px] text-ink-2">{status}</p>}
        </motion.div>
        <Tail />
      </motion.div>
      <Choices />
    </div>
  );
}
