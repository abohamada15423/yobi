// Design options for interface 5 (the HUD: volume, brightness, Caps Lock, keyboard language,
// battery, internet). Review page only: ?hud
import { ArrowBigUp, BatteryCharging, BatteryLow, Sun, Volume2, VolumeX, Wifi, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

type Variant = 'split' | 'fill' | 'ticks';
type Item = { label: string; icon?: LucideIcon; badge?: string; value?: number; text: string; color: string; note?: string };
const ITEMS: Item[] = [
  { label: 'الصوت', icon: Volume2, value: 0.62, text: '٦٢٪', color: '#3CC2B4' },
  { label: 'مكتوم', icon: VolumeX, value: 0, text: 'مكتوم', color: '#6E6E73' },
  { label: 'الإضاءة', icon: Sun, value: 0.8, text: '٨٠٪', color: '#E3B04B' },
  { label: 'Caps Lock', icon: ArrowBigUp, text: 'شغال', color: '#7FA8FF', note: 'Caps Lock' },
  { label: 'لغة الكيبورد', badge: 'ع', text: 'العربية', color: '#C792EA', note: 'لغة الكيبورد' },
  { label: 'البطارية قربت تخلص', icon: BatteryLow, value: 0.14, text: '١٤٪', color: '#E5533D', note: 'البطارية قربت تخلص' },
  { label: 'بيشحن', icon: BatteryCharging, value: 0.57, text: '٥٧٪', color: '#7BD88F', note: 'بيشحن' },
  { label: 'النت رجع', icon: Wifi, text: 'بعد ٣ د', color: '#3CC2B4', note: 'النت رجع' },
];

const pill = (w: number, children: ReactNode, extra = '') => (
  <div className={`relative flex h-9 items-center overflow-hidden bg-island px-3 ${extra}`} style={{ width: w, borderRadius: 18, boxShadow: '0 8px 24px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.05)' }}>{children}</div>
);
const Icon = ({ it, color }: { it: Item; color?: string }) => it.badge
  ? <span className="grid size-6 place-items-center rounded-[7px] text-[12px] font-bold" style={{ background: `${it.color}33`, color: it.color }}>{it.badge}</span>
  : it.icon ? <it.icon className="size-[18px] shrink-0" style={{ color: color ?? it.color }} strokeWidth={2.2} /> : null;

/** A: icon at the start, a coloured meter in the middle, the number at the end */
function Split({ it }: { it: Item }) {
  return pill(250, <div className="flex w-full items-center gap-3">
    <Icon it={it} />
    {it.value !== undefined
      ? <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-white/10"><span className="absolute inset-y-0 start-0 rounded-full" style={{ width: `${it.value * 100}%`, background: it.color, boxShadow: `0 0 10px ${it.color}88` }} /></span>
      : <span className="flex-1 truncate text-[12px] text-ink-2">{it.note}</span>}
    <span className="text-[12.5px] font-semibold tabular-nums" style={{ color: it.value === undefined ? it.color : undefined }}>{it.text}</span>
  </div>);
}
/** B: the whole pill fills with the colour like a liquid, the words float on top */
function Fill({ it }: { it: Item }) {
  const v = it.value ?? 1;
  return pill(250, <>
    <span className="absolute inset-y-0 start-0" style={{ width: `${v * 100}%`, background: `linear-gradient(90deg, ${it.color}55, ${it.color}aa)`, opacity: it.value === undefined ? 0.35 : 1 }} />
    <span className="relative flex w-full items-center gap-2.5">
      <Icon it={it} color="#fff" />
      <span className="flex-1 truncate text-[12.5px] font-semibold">{it.value !== undefined ? it.label : it.note}</span>
      <span className="text-[12.5px] font-bold tabular-nums">{it.text}</span>
    </span>
  </>);
}
/** C: lit segments, like a level meter on a mixing desk */
function Ticks({ it }: { it: Item }) {
  const n = 16, lit = Math.round((it.value ?? 0) * n);
  return pill(270, <div className="flex w-full items-center gap-3">
    <Icon it={it} />
    {it.value !== undefined
      ? <span className="flex flex-1 items-center gap-[3px]">{Array.from({ length: n }, (_, i) => (
          <i key={i} className="h-3 flex-1 rounded-[2px]" style={{ background: i < lit ? it.color : 'rgba(255,255,255,.08)', boxShadow: i < lit ? `0 0 6px ${it.color}66` : undefined, opacity: i < lit ? 0.55 + 0.45 * (i / n) : 1 }} />
        ))}</span>
      : <span className="flex-1 truncate text-[12px] text-ink-2">{it.note}</span>}
    <span className="w-12 text-end text-[12.5px] font-semibold tabular-nums" style={{ color: it.value === undefined ? it.color : undefined }}>{it.text}</span>
  </div>);
}

const NAMES: Record<Variant, [string, string, (p: { it: Item }) => ReactNode]> = {
  split: ['أ. القسمين', 'أيقونة في الأول، عداد ملوّن منوّر في النص، والرقم في الآخر. نفس روح الكبسولة الهادية.', Split],
  fill: ['ب. السايل', 'الكبسولة كلها بتتملي باللون زي السايل وانت بتعلّي الصوت، والكلام فوقها. الأكتر حياة.', Fill],
  ticks: ['ج. اللمبات', 'شرايح بتنوّر واحدة ورا التانية زي عداد الصوت في الميكسر. شكل تقني.', Ticks],
};

export function HudOptions() {
  return (
    <div dir="rtl" className="h-full overflow-auto bg-[#1b1b1e] p-7 font-ui text-ink">
      <p className="mb-5 text-[13px] text-ink-2">كل نوع ليه لون: الصوت تركوازي، الإضاءة دهبي، Caps Lock أزرق، اللغة بنفسجي، البطارية أخضر (وأحمر لو قربت تخلص).</p>
      <div className="flex flex-wrap items-start gap-10">
        {(['split', 'fill', 'ticks'] as Variant[]).map(v => {
          const [name, about, View] = NAMES[v];
          return (
            <section key={v} className="flex w-[290px] flex-col gap-3">
              <h2 className="m-0 font-display text-lg font-semibold">{name}</h2>
              <p className="m-0 min-h-[40px] text-[12.5px] text-ink-2">{about}</p>
              {ITEMS.map(it => <View key={it.label} it={it} />)}
            </section>
          );
        })}
      </div>
    </div>
  );
}
