// Interface 5: the HUD (design B, "the liquid"): the whole pill fills with the reading's colour,
// the words float on top. Volume, brightness, Caps Lock, keyboard language, battery, internet.
import { motion } from 'motion/react';
import { ArrowBigUp, Battery, BatteryCharging, BatteryLow, Sun, Volume2, VolumeX, Wifi, WifiOff, type LucideIcon } from 'lucide-react';
import { useIsland } from '../store';
import { spring } from '../motion';
import type { HudMsg } from '../types';
import { T, dir, fmt, towardEnd } from '../i18n';

export const HUD_SIZE: [number, number] = [250, 36];
const pct = fmt.pct;
/** how long the internet was gone: "3 min", "1 h 20 min" */
const gone = (s: number) => fmt.span(s / 60);

interface Look { icon?: LucideIcon; badge?: string; label: string; text: string; value: number | null; color: string }
/** what each reading shows; value null = no amount (the pill glows softly instead of filling) */
function look(m: HudMsg): Look {
  switch (m.kind) {
    case 'volume': {
      const off = m.muted || m.value === 0;
      return { icon: off ? VolumeX : Volume2, label: T('الصوت', 'Volume'), text: m.muted ? T('مكتوم', 'Muted') : pct(m.value), value: m.muted ? 0 : m.value / 100, color: off ? 'var(--color-ink-3)' : 'var(--color-accent)' };
    }
    case 'brightness': return { icon: Sun, label: T('الإضاءة', 'Brightness'), text: pct(m.value), value: m.value / 100, color: 'var(--color-gold)' };
    case 'caps': return { icon: ArrowBigUp, label: 'Caps Lock', text: m.on ? T('شغال', 'On') : T('مقفول', 'Off'), value: null, color: m.on ? '#7FA8FF' : 'var(--color-ink-3)' };
    case 'kbd': return { badge: m.badge || '⌨', label: T('لغة الكيبورد', 'Keyboard'), text: m.name || '', value: null, color: '#C792EA' };
    case 'battery': return {
      icon: m.plugged ? BatteryCharging : m.low ? BatteryLow : Battery,
      label: m.low ? T('البطارية قربت تخلص', 'Battery low') : m.plugged ? T('بيشحن', 'Charging') : T('على البطارية', 'On battery'),
      text: pct(m.value), value: m.value / 100, color: m.low ? 'var(--color-alert)' : '#7BD88F',
    };
    case 'net': return {
      icon: m.online ? Wifi : WifiOff, label: m.online ? T('النت رجع', 'Back online') : T('النت فصل', 'Offline'),
      text: m.online && m.gone_s >= 60 ? T(`بعد ${gone(m.gone_s)}`, `after ${gone(m.gone_s)}`) : '', value: null, color: m.online ? 'var(--color-accent)' : 'var(--color-alert)',
    };
  }
}

export function Hud() {
  const hud = useIsland(s => s.hud);
  if (!hud) return null;
  const l = look(hud);
  const mix = (p: number) => `color-mix(in srgb, ${l.color} ${p}%, transparent)`;
  return (
    <motion.div dir={dir()} className="absolute inset-0 flex items-center overflow-hidden px-3" role="status" aria-live="polite"
                initial={{ opacity: 0 }} animate={{ opacity: 1, transition: { duration: 0.12 } }}>
      {/* the liquid: keyed by kind, so a new kind starts at its own level and the same kind flows to the new one */}
      <motion.span key={hud.kind} className="absolute inset-y-0 start-0"
                   style={{ background: `linear-gradient(to ${towardEnd()}, ${mix(35)}, ${mix(70)})` }}
                   initial={{ width: `${(l.value ?? 1) * 100}%`, opacity: l.value === null ? 0.35 : 1 }}
                   animate={{ width: `${(l.value ?? 1) * 100}%`, opacity: l.value === null ? 0.35 : 1 }} transition={spring.content} />
      <span className="relative flex w-full items-center gap-2.5">
        {l.badge
          ? <span className="grid size-6 place-items-center rounded-[7px] bg-white/15 text-[12px] font-bold">{l.badge}</span>
          : l.icon && <l.icon className="size-[18px] shrink-0" strokeWidth={2.2} aria-hidden="true" />}
        <span className="min-w-0 flex-1 truncate text-[12.5px] font-semibold"><bdi>{l.label}</bdi></span>
        <span className="text-[12.5px] font-bold tabular-nums"><bdi>{l.text}</bdi></span>
      </span>
    </motion.div>
  );
}
