import { motion } from 'motion/react';
import type { LucideIcon } from 'lucide-react';
import { spring } from '../motion';

interface Props {
  icon: LucideIcon;
  label: string;                // what it does, for the tooltip and screen readers
  onClick?: () => void;
  size?: 'sm' | 'md' | 'lg';
  tone?: 'plain' | 'solid' | 'accent';
  pressed?: boolean;
  disabled?: boolean;
  text?: string;                // optional words next to the icon
}

const SIZES = { sm: 'h-8 min-w-8 [&_svg]:size-4', md: 'h-10 min-w-10 [&_svg]:size-[18px]', lg: 'h-12 min-w-12 [&_svg]:size-5' };
const TONES = {
  plain: 'bg-fill-1 text-ink hover:bg-fill-2',
  solid: 'bg-ink text-island',
  accent: 'bg-gold text-island',
};

export function IconButton({ icon: Icon, label, onClick, size = 'md', tone = 'plain', pressed, disabled, text }: Props) {
  return (
    <motion.button
      type="button"
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      whileHover={disabled ? undefined : { scale: 1.06 }}
      whileTap={disabled ? undefined : { scale: 0.92 }}
      transition={spring.micro}
      className={`inline-flex items-center justify-center gap-2 rounded-pill px-2.5 font-ui text-[13px] font-semibold
        transition-colors disabled:opacity-40 ${SIZES[size]} ${TONES[tone]} ${pressed ? 'ring-1 ring-accent/60' : ''}`}
    >
      <Icon strokeWidth={2} />
      {text && <span className="pe-1">{text}</span>}
    </motion.button>
  );
}
