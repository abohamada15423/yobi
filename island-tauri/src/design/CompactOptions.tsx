// Design options for interface 1 (the compact island). A review page only: ?options
import { Download, Timer } from 'lucide-react';
import type { ReactNode } from 'react';

type Variant = 'split' | 'ring' | 'glow';

const ART = 'linear-gradient(135deg, #3CC2B4, #1E5AA8 55%, #E3B04B)';

/** a few bars that read as sound; Apple-sized */
function Wave({ color = 'var(--color-accent)' }: { color?: string }) {
  return (
    <span className="flex h-4 items-center gap-[2px]" aria-hidden="true">
      {[6, 12, 8, 14, 9].map((h, i) => <i key={i} className="w-[3px] rounded-pill" style={{ height: h, background: color }} />)}
    </span>
  );
}
function Dots() {
  return <span className="flex gap-1"><i className="size-1.5 rounded-pill bg-gold" /><i className="size-1.5 rounded-pill bg-accent" /></span>;
}
function Ring({ value, children, color = 'var(--color-accent)' }: { value: number; children: ReactNode; color?: string }) {
  const r = 10, c = 2 * Math.PI * r;
  return (
    <span className="relative grid size-6 place-items-center">
      <svg className="absolute inset-0 -rotate-90" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r={r} fill="none" stroke="var(--color-line)" strokeWidth="2.2" />
        <circle cx="12" cy="12" r={r} fill="none" stroke={color} strokeWidth="2.2" strokeLinecap="round" strokeDasharray={`${c * value} ${c}`} />
      </svg>
      {children}
    </span>
  );
}

function Pill({ w, h = 32, children, glow }: { w: number; h?: number; children?: ReactNode; glow?: number }) {
  return (
    <div className="relative flex items-center justify-between overflow-hidden bg-island px-2.5"
         style={{ width: w, height: h, borderRadius: h / 2, boxShadow: '0 8px 22px rgba(0,0,0,.4), inset 0 1px 0 rgba(255,255,255,.05)' }}>
      {children}
      {glow !== undefined && (
        <span className="absolute inset-x-5 bottom-[3px] h-[2px] rounded-pill bg-line">
          <span className="absolute inset-y-0 start-0 rounded-pill bg-accent" style={{ width: `${glow * 100}%`, boxShadow: '0 0 8px var(--color-accent)' }} />
        </span>
      )}
    </div>
  );
}

function states(v: Variant): [string, ReactNode][] {
  const time = <span className="font-display text-[12.5px] font-semibold tabular-nums">٣:١٠ م</span>;
  return [
    ['هادية', <Pill w={v === 'glow' ? 90 : 96} h={28} />],
    ['هادية بالساعة', <Pill w={112} h={28}><span className="w-full text-center">{time}</span></Pill>],
    ['مزيكا', v === 'ring'
      ? <Pill w={196}><span className="size-6 rounded-[8px]" style={{ background: ART }} /><Ring value={0.42}><Wave color="var(--color-ink)" /></Ring></Pill>
      : <Pill w={196} glow={v === 'glow' ? 0.42 : undefined}><span className="size-6 rounded-[8px]" style={{ background: ART }} /><Wave /></Pill>],
    ['تركيز', v === 'ring'
      ? <Pill w={176}><Ring value={0.72}><Timer className="size-3 text-accent" /></Ring><span className="font-display text-[13px] font-semibold tabular-nums">١٨:٠٤</span></Pill>
      : <Pill w={176} glow={v === 'glow' ? 0.72 : undefined}><span className="flex items-center gap-1.5"><Timer className="size-4 text-accent" />{v === 'split' && <span className="text-[11px] text-ink-2">تركيز</span>}</span><span className="font-display text-[13px] font-semibold tabular-nums">١٨:٠٤</span></Pill>],
    ['تحميل', v === 'ring'
      ? <Pill w={196}><Ring value={0.35}><Download className="size-3 text-accent" /></Ring><span className="text-[12px] tabular-nums text-ink-2">٤٫٢ م.ب/ث</span></Pill>
      : <Pill w={196} glow={v === 'glow' ? 0.35 : undefined}><Download className="size-4 text-accent" /><span className="text-[12px] tabular-nums text-ink-2">٤٫٢ م.ب/ث</span></Pill>],
    ['المايك شغال', <Pill w={v === 'glow' ? 90 : 96} h={28}><span className="w-full" /><Dots /></Pill>],
  ];
}

const NAMES: Record<Variant, [string, string]> = {
  split: ['أ. القسمين', 'حاجة في أول الكبسولة وحاجة في آخرها، زي Apple بالظبط. أهدى وأوضح.'],
  ring: ['ب. الحلقة', 'التقدّم (التركيز، التحميل، الأغنية) حلقة صغيرة حوالين الأيقونة. بيبان كام فاضل من غير أرقام.'],
  glow: ['ج. الخط المضيء', 'خط يوبي رفيع منوّر في قاع الكبسولة بيبيّن التقدّم. أقرب لهوية يوبي القديمة.'],
};

export function CompactOptions() {
  return (
    <div dir="rtl" className="h-full overflow-auto bg-[#1b1b1e] p-7 font-ui text-ink">
      {(['split', 'ring', 'glow'] as Variant[]).map(v => (
        <section key={v} className="mb-7">
          <h2 className="font-display text-lg font-semibold">{NAMES[v][0]}</h2>
          <p className="mb-3 text-[13px] text-ink-2">{NAMES[v][1]}</p>
          <div className="flex flex-wrap items-end gap-5">
            {states(v).map(([label, el]) => (
              <figure key={label} className="m-0 flex flex-col items-center gap-2">
                {el}<figcaption className="text-[11px] text-ink-3">{label}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
