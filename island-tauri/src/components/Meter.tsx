import { motion } from 'motion/react';
import { spring } from '../motion';

interface Props {
  value: number;               // 0..1
  tone?: 'accent' | 'gold' | 'alert' | 'ink';
  /** warm above 70%, alert above 90% (CPU, RAM) */
  heat?: boolean;
  className?: string;
}

const COLORS = { accent: 'bg-accent', gold: 'bg-gold', alert: 'bg-alert', ink: 'bg-ink' };

/** A thin rounded meter. In Arabic it fills from the right. */
export function Meter({ value, tone = 'accent', heat = false, className = '' }: Props) {
  const v = Math.max(0, Math.min(1, value || 0));
  const color = heat ? (v >= 0.9 ? 'bg-alert' : v >= 0.7 ? 'bg-gold' : COLORS[tone]) : COLORS[tone];
  return (
    <div className={`relative h-1 overflow-hidden rounded-pill bg-line ${className}`} role="meter"
         aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)}>
      <motion.div className={`absolute inset-y-0 start-0 rounded-pill ${color}`}
                  initial={false} animate={{ width: `${v * 100}%` }} transition={spring.content} />
    </div>
  );
}
