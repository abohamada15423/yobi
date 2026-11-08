// The island's motion vocabulary. Every animation uses one of these, so the whole island moves
// with one character: a lively open, a calm close, quick small reactions.
import type { Transition } from 'motion/react';

export const spring = {
  /** compact → expanded: a little overshoot, like the capsule stretching open */
  open: { type: 'spring', stiffness: 380, damping: 30, mass: 0.9 } as Transition,
  /** expanded → compact: no overshoot */
  close: { type: 'spring', stiffness: 460, damping: 42 } as Transition,
  /** buttons, toggles, small things */
  micro: { type: 'spring', stiffness: 700, damping: 34 } as Transition,
  /** content entering after the shape has started to grow */
  content: { type: 'spring', stiffness: 300, damping: 28, delay: 0.08 } as Transition,
};

/** children of an opening island arrive one after another */
export const stagger = { staggerChildren: 0.035, delayChildren: 0.1 };
