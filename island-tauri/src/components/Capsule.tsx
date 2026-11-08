import { motion, useReducedMotionConfig } from 'motion/react';
import { useEffect, useRef, type ReactNode } from 'react';
import { bridge } from '../bridge';
import { spring } from '../motion';

export const TOP = 8; // the capsule floats this far under the top of the screen

interface Props {
  width: number;
  height: number;
  /** compact sizes are pills; tall ones become cards */
  expanded?: boolean;
  /** shrinks away (a fullscreen game or video); clicks then pass everywhere */
  hidden?: boolean;
  children?: ReactNode;
  onPointerEnter?: () => void;
  onPointerLeave?: () => void;
  /** a strip on the screen's right or left edge: flush against it, centred top to bottom, growing inward */
  edge?: 'left' | 'right' | null;
}

/**
 * The island's body. It morphs between sizes with a spring, rounds its corners to its height
 * (a pill when short, a card when tall), and tells the window where it is so clicks outside
 * it pass through to the apps underneath.
 */
export function Capsule({ width, height, expanded = false, hidden = false, children, onPointerEnter, onPointerLeave, edge = null }: Props) {
  const reduce = useReducedMotionConfig();   // Windows' setting, or the user's own via <MotionConfig>
  const radius = Math.min((edge ? Math.min(width, height) : height) / 2, 30);
  const last = useRef('');

  useEffect(() => {
    const r = hidden ? { x: -9999, y: -9999, w: 0, h: 0 }
      : edge ? { x: edge === 'right' ? window.innerWidth - width : 0, y: Math.round((window.innerHeight - height) / 2), w: width, h: height }
      : { x: Math.round((window.innerWidth - width) / 2), y: 0, w: width, h: height + TOP };
    const key = JSON.stringify(r);
    if (key !== last.current) { last.current = key; bridge.rect(r); }
  }, [width, height, hidden, edge]);
  // on a side, the corners against the screen's edge are square
  const corners = {
    borderTopLeftRadius: edge === 'left' ? 0 : radius, borderBottomLeftRadius: edge === 'left' ? 0 : radius,
    borderTopRightRadius: edge === 'right' ? 0 : radius, borderBottomRightRadius: edge === 'right' ? 0 : radius,
  };

  return (
    <motion.div
      className={`absolute overflow-hidden bg-island ${edge === 'right' ? 'right-0 top-1/2' : edge === 'left' ? 'left-0 top-1/2' : 'left-1/2'}`}
      style={{
        ...(edge ? { y: '-50%', originX: edge === 'right' ? 1 : 0 } : { top: TOP, x: '-50%', originY: 0 }),
        boxShadow: expanded
          ? '0 18px 50px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.06)'
          : '0 8px 24px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.04)',
      }}
      initial={false}
      animate={{ width, height, ...corners, opacity: hidden ? 0 : 1, scale: hidden ? 0.6 : 1 }}
      transition={reduce ? { duration: 0 } : expanded ? spring.open : spring.close}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
    >
      {/* a faint sheen along the top edge when open: glass, without blurring what's behind */}
      {expanded && (
        <div className="pointer-events-none absolute inset-x-0 top-0 h-16"
             style={{ background: 'linear-gradient(to bottom, rgba(255,255,255,.035), transparent)' }} />
      )}
      {children}
    </motion.div>
  );
}
