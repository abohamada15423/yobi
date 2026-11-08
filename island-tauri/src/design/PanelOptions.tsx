// Design options for interface 3 (the open panel: glance, dock, menu, write to Yobi). Review page only: ?panel
import { Clipboard, Grid2x2, Inbox, Mic, MoreHorizontal, PenLine, SendHorizontal } from 'lucide-react';
import type { ReactNode } from 'react';
import { Meter } from '../components/Meter';

type Variant = 'stack' | 'split' | 'tiles';
const STATS = [['المعالج', 0.12], ['الرامات', 0.63], ['البطارية', 0.81]] as const;
const nf = new Intl.NumberFormat('ar-EG');
const pct = (v: number) => `${nf.format(Math.round(v * 100))}٪`;

const shell = (children: ReactNode, w = 400) => (
  <div className="overflow-hidden bg-island p-4" style={{ width: w, borderRadius: 30, boxShadow: '0 18px 50px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.06)' }}>{children}</div>
);
function Btn({ icon: I, text, solid }: { icon: typeof Mic; text?: string; solid?: boolean }) {
  return (
    <span className={`flex h-10 items-center justify-center gap-1.5 rounded-pill text-[13px] font-semibold ${text ? 'px-4' : 'w-10'} ${solid ? 'bg-ink text-island' : 'bg-fill-1 text-ink'}`}>
      <I className="size-[17px]" strokeWidth={2.2} />{text}
    </span>
  );
}
function Ring({ v, label }: { v: number; label: string }) {
  const c = 2 * Math.PI * 15;
  return (
    <span className="flex flex-col items-center gap-1">
      <span className="relative grid size-11 place-items-center">
        <svg className="absolute inset-0 -rotate-90" viewBox="0 0 36 36"><circle cx="18" cy="18" r="15" fill="none" stroke="var(--color-line)" strokeWidth="3" />
          <circle cx="18" cy="18" r="15" fill="none" stroke={v > 0.85 ? 'var(--color-alert)' : 'var(--color-accent)'} strokeWidth="3" strokeLinecap="round" strokeDasharray={`${c * v} ${c}`} /></svg>
        <span className="text-[11px] font-semibold tabular-nums">{pct(v)}</span>
      </span>
      <span className="text-[10.5px] text-ink-3">{label}</span>
    </span>
  );
}
const Clock = ({ big = 40 }: { big?: number }) => (
  <div className="flex flex-col">
    <span className="font-display font-semibold leading-none tabular-nums" style={{ fontSize: big }}>٤:٣٠ م</span>
    <span className="mt-1.5 text-[12.5px] text-ink-2">السبت، ٧ نوفمبر</span>
    <span className="text-[12px] text-ink-3">٢٧ جمادى الأولى ١٤٤٨ هـ · ٢٣° غائم جزئيًا</span>
  </div>
);
const Dock = ({ writing }: { writing?: boolean }) => writing ? (
  <div className="flex items-center gap-2">
    <span className="flex h-10 flex-1 items-center rounded-pill bg-fill-1 px-4 text-[13px] text-ink-3">اكتب ليوبي…</span>
    <Btn icon={SendHorizontal} solid />
  </div>
) : (
  <div className="flex items-center justify-between">
    <span className="flex gap-2"><Btn icon={Mic} text="اتكلم" solid /><Btn icon={PenLine} text="اكتب" /><Btn icon={MoreHorizontal} /></span>
    <span className="flex gap-2"><Btn icon={Grid2x2} /><Btn icon={Inbox} /><Btn icon={Clipboard} /></span>
  </div>
);

/** A: the clock big at the top, the machine as three small rings beside it, the dock under. */
const Stack = ({ writing }: { writing?: boolean }) => shell(<div className="flex flex-col gap-4">
  <div className="flex items-start justify-between"><Clock big={44} /><span className="flex gap-3">{STATS.map(([n, v]) => <Ring key={n} v={v} label={n} />)}</span></div>
  <Dock writing={writing} />
</div>);

/** B: the Electron island's layout, made calmer: clock on one side, meters as lines on the other. */
const Split = ({ writing }: { writing?: boolean }) => shell(<div className="flex flex-col gap-4">
  <div className="flex items-center justify-between gap-6">
    <Clock />
    <div className="grid w-40 gap-2.5">{STATS.map(([n, v]) => (
      <div key={n} className="grid grid-cols-[52px_1fr_32px] items-center gap-2 text-[11.5px]"><span className="text-ink-2">{n}</span><Meter value={v} heat /><span className="text-end tabular-nums">{pct(v)}</span></div>
    ))}</div>
  </div>
  <Dock writing={writing} />
</div>);

/** C: tiles, like a control centre: one wide tile for the time, small tiles for the machine. */
const Tiles = ({ writing }: { writing?: boolean }) => shell(<div className="flex flex-col gap-2.5">
  <div className="grid grid-cols-3 gap-2.5">
    <div className="col-span-3 rounded-[20px] bg-fill-1 px-4 py-3"><Clock big={34} /></div>
    {STATS.map(([n, v]) => (
      <div key={n} className="flex flex-col gap-2 rounded-[18px] bg-fill-1 px-3 py-2.5">
        <span className="flex justify-between text-[11px]"><span className="text-ink-2">{n}</span><span className="tabular-nums">{pct(v)}</span></span><Meter value={v} heat />
      </div>
    ))}
  </div>
  <div className="mt-1.5"><Dock writing={writing} /></div>
</div>);

const MENU = [['الاستماع', true], ['الرد بالصوت', false], ['أسئلة يوبي', true]] as const;
const Menu = () => shell(<div className="flex flex-col gap-3">
  <div className="grid gap-1 rounded-[20px] bg-fill-1 p-1.5">
    {MENU.map(([t, on]) => (
      <span key={t} className="flex h-10 items-center justify-between rounded-[14px] px-3 text-[13px]">{t}
        <span className={`flex h-[22px] w-[38px] items-center rounded-pill p-[2px] ${on ? 'justify-start bg-accent' : 'justify-end bg-line'}`}><i className="size-[18px] rounded-pill bg-ink" /></span>
      </span>
    ))}
  </div>
  <div className="grid grid-cols-3 gap-2 text-[12.5px]">
    {['اللي فات', 'الإعدادات', 'جرّب الحالات'].map(t => <span key={t} className="grid h-10 place-items-center rounded-[14px] bg-fill-1">{t}</span>)}
  </div>
  <span className="grid h-10 place-items-center rounded-[14px] bg-alert/15 text-[13px] font-semibold text-alert">اقفل يوبي</span>
</div>);

const NAMES: Record<Variant, [string, string, (p: { writing?: boolean }) => ReactNode]> = {
  stack: ['أ. الساعة الكبيرة', 'الساعة كبيرة في الأول، والجهاز ٣ حلقات صغيرة جنبها، والأزرار تحت. نظيف وفيه هوا.', Stack],
  split: ['ب. النصّين', 'نفس ترتيب الجزيرة القديمة بس أهدى: الساعة في جنب، وعدادات خطية في الجنب التاني.', Split],
  tiles: ['ج. المربعات', 'مربعات زي Control Center: مربع عريض للوقت، ومربعات صغيرة للجهاز. منظم وبيتوسع بسهولة لما المزيكا ويومك ييجوا.', Tiles],
};

export function PanelOptions() {
  return (
    <div dir="rtl" className="h-full overflow-auto bg-[#1b1b1e] p-7 font-ui text-ink">
      {(['stack', 'split', 'tiles'] as Variant[]).map(v => {
        const [name, about, View] = NAMES[v];
        return (
          <section key={v} className="mb-7">
            <h2 className="font-display text-lg font-semibold">{name}</h2>
            <p className="mb-3 text-[13px] text-ink-2">{about}</p>
            <div className="flex flex-wrap items-start gap-6">
              <figure className="m-0 flex flex-col items-center gap-1.5"><View /><figcaption className="text-[11px] text-ink-3">الرئيسية</figcaption></figure>
              <figure className="m-0 flex flex-col items-center gap-1.5"><View writing /><figcaption className="text-[11px] text-ink-3">اكتب ليوبي</figcaption></figure>
            </div>
          </section>
        );
      })}
      <section>
        <h2 className="font-display text-lg font-semibold">القائمة (واحدة للتلاتة)</h2>
        <p className="mb-3 text-[13px] text-ink-2">مفاتيح بدل النقط، والقفل لوحده تحت علشان ما يتضغطش بالغلط.</p>
        <Menu />
      </section>
    </div>
  );
}
