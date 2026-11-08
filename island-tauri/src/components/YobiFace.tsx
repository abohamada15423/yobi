import { motion, useReducedMotion } from 'motion/react';
import { useEffect, useState } from 'react';
import { spring } from '../motion';

export type Look = 'neutral' | 'listening' | 'thinking' | 'talking' | 'happy' | 'sad' | 'question' | 'calm';

interface Props {
  look: Look;
  /** 0..1 mic level while listening: the mouth moves with your voice */
  level?: number;
  size?: number;
}

/**
 * Yobi: two eyes over a short line. The line is the mouth: it moves with your voice,
 * smiles when something worked and frowns when it didn't.
 */
export function YobiFace({ look, level = 0, size = 34 }: Props) {
  const reduce = useReducedMotion();
  const blinking = useBlink(!reduce && ['neutral', 'listening', 'question', 'talking'].includes(look));
  const t = useClock(!reduce && ['listening', 'talking', 'thinking'].includes(look));

  const eye = (side: -1 | 1) => {
    const base = { width: 6, height: 6, borderRadius: 6, x: 0, rotate: 0, scale: 1 };
    const shape =
      look === 'happy' ? { ...base, width: 8, height: 4, borderRadius: '8px 8px 2px 2px' }
      : look === 'sad' ? { ...base, width: 7, height: 2.5, rotate: side * -16 }
      : look === 'calm' ? { ...base, width: 7, height: 2.5 }
      : look === 'listening' ? { ...base, scale: 1.25 }
      : look === 'question' && side === 1 ? { ...base, scale: 1.4 }
      : look === 'thinking' ? { ...base, x: Math.sin(t * 2.4) * 2.5 }
      : base;
    return blinking && shape.height > 3 ? { ...shape, height: 1.2 } : shape;
  };

  // the mouth: a short path, shaped by the look
  const W = 22, MID = 5;
  const amp = look === 'listening' ? 1 + level * 3.5 : look === 'talking' ? 1.6 : 0;
  const curve = look === 'happy' ? 3.2 : look === 'sad' ? -2.6 : 0;
  const pts = Array.from({ length: 12 }, (_, i) => {
    const x = (i / 11) * W, u = i / 11, env = Math.sin(Math.PI * u);
    const y = MID + curve * env + amp * env * Math.sin(u * 14 + t * 9);
    return `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(2)}`;
  }).join(' ');
  const mouthColor = look === 'happy' ? 'var(--color-gold)' : look === 'sad' ? 'var(--color-alert)'
    : look === 'listening' || look === 'talking' ? 'var(--color-accent)' : 'var(--color-ink)';

  return (
    <div className="relative flex flex-col items-center" style={{ width: size }} aria-hidden="true">
      <div className="flex items-center gap-[7px]" style={{ height: 9 }}>
        {([-1, 1] as const).map(side => (
          <motion.span key={side} className={look === 'happy' ? 'border-[1.8px] border-b-0 border-gold' : 'bg-ink'}
                       style={look === 'happy' ? { background: 'transparent' } : undefined}
                       initial={false} animate={eye(side)} transition={spring.micro} />
        ))}
      </div>
      <svg width={W} height={11} viewBox={`0 0 ${W} 11`} className="overflow-visible">
        <path d={pts} fill="none" stroke={mouthColor} strokeWidth={1.8} strokeLinecap="round" />
      </svg>
    </div>
  );
}

function useBlink(on: boolean) {
  const [blink, setBlink] = useState(false);
  useEffect(() => {
    if (!on) return;
    let id: number;
    const next = () => {
      id = window.setTimeout(() => { setBlink(true); window.setTimeout(() => setBlink(false), 130); next(); }, 3200 + Math.random() * 3000);
    };
    next();
    return () => window.clearTimeout(id);
  }, [on]);
  return blink;
}

/** seconds, ticking every frame only while something on the face moves */
function useClock(on: boolean) {
  const [t, setT] = useState(0);
  useEffect(() => {
    if (!on) return;
    let raf = 0;
    const tick = (ms: number) => { setT(ms / 1000); raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [on]);
  return t;
}
