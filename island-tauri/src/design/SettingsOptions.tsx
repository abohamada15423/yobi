// Design options for interface 9 (the settings window + themes). Review page only: ?settings_options
import { Bell, BookOpen, Calendar, ChevronLeft, Eye, Keyboard, MoonStar, Palette, Search, Sparkles, Timer } from 'lucide-react';
import type { ReactNode } from 'react';

type Variant = 'side' | 'tiles' | 'scroll';
const SECTIONS: [string, typeof Palette, string][] = [
  ['الشكل', Palette, '#C792EA'], ['الجزيرة بتعرض إيه', Eye, '#3CC2B4'], ['لحظات وإضافات', Sparkles, '#F0A43A'], ['الصلاة', MoonStar, '#E3B04B'],
  ['التركيز', Timer, '#5AA9FF'], ['الأذكار', BookOpen, '#7BD88F'], ['الاجتماعات', Calendar, '#7FA8FF'], ['الاختصار والشاشة', Keyboard, '#A1A1A6'],
];
const THEMES: [string, string, string][] = [['فيروزي', '#3CC2B4', '#E3B04B'], ['ليل', '#45D0C1', '#E3B04B'], ['بردي', '#D8B56A', '#E3B04B'], ['نيل', '#7FD6C2', '#E3B04B'], ['عقيق', '#E8A25B', '#E9C46A']];
const SHOWS: [string, boolean, string?][] = [['الساعة على الجزيرة وهي هادية', true], ['الأغنية اللي شغالة', true], ['اسم الأغنية لما تتغير', true], ['التحميلات', true], ['سجل الحافظة', true, 'في الذاكرة بس، وبيتجاهل كلمات السر'], ['نقطة المايك والكاميرا', true], ['تستخبى وقت الألعاب والأفلام', false, 'يوبي والأذان بيظهروا برضه']];

const win = (children: ReactNode) => (
  <div className="relative overflow-hidden rounded-[14px] bg-[#0c0c0f] ring-1 ring-white/10" style={{ width: 760, height: 520, boxShadow: '0 24px 60px rgba(0,0,0,.5)' }}>
    <div className="flex h-8 items-center justify-between bg-white/[.03] px-3 text-[11px] text-ink-3"><span>إعدادات يوبي</span><span className="flex gap-3"><i>—</i><i>□</i><i>✕</i></span></div>
    <div className="h-[488px]">{children}</div>
  </div>
);
const Switch = ({ on, color = 'var(--color-accent)' }: { on: boolean; color?: string }) => (
  <span className="flex h-[22px] w-[38px] shrink-0 items-center rounded-full p-[2px]" style={{ background: on ? color : 'rgba(255,255,255,.12)', justifyContent: on ? 'flex-end' : 'flex-start' }}><i className="size-[18px] rounded-full bg-white" /></span>
);
const Island = ({ accent, wide = false }: { accent: string; wide?: boolean }) => (
  <div className="flex items-center gap-3 rounded-full bg-black px-4 py-2.5 shadow-[0_8px_24px_rgba(0,0,0,.5)]" style={{ width: wide ? 300 : 250 }}>
    <span className="flex-1 text-[13px] font-semibold text-white">تمام، فتحت ديسكورد</span>
    <span className="flex h-4 items-center gap-[2px]">{[6, 12, 8, 14, 9].map((h, i) => <i key={i} className="w-[3px] rounded-full" style={{ height: h, background: accent }} />)}</span>
  </div>
);
const Themes = ({ big = false }: { big?: boolean }) => (
  <div className={`grid grid-cols-5 ${big ? 'gap-3' : 'gap-2'}`}>
    {THEMES.map(([n, a, g], i) => (
      <span key={n} className="flex flex-col items-center gap-1.5 rounded-[14px] p-2 text-[11.5px]" style={i === 0 ? { background: `${a}1f`, boxShadow: `inset 0 0 0 1.5px ${a}` } : { background: 'rgba(255,255,255,.04)' }}>
        <span className={`flex items-center gap-1 rounded-full bg-black px-2 ${big ? 'h-7 w-20' : 'h-6 w-16'}`}><i className="h-1 flex-1 rounded-full" style={{ background: a }} /><i className="size-1.5 rounded-full" style={{ background: g }} /></span>{n}
      </span>
    ))}
  </div>
);
const Rows = ({ color = 'var(--color-accent)' }: { color?: string }) => (
  <div className="divide-y divide-white/5 overflow-hidden rounded-[14px] bg-white/[.04]">
    {SHOWS.map(([t, on, sub]) => <div key={t} className="flex items-center gap-3 px-3.5 py-2.5"><span className="flex-1 text-[12.5px]">{t}{sub && <small className="block text-[10.5px] text-ink-3">{sub}</small>}</span><Switch on={on} color={color} /></div>)}
  </div>
);
const Try = ({ c }: { c: string }) => <span className="inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12px] font-semibold text-island" style={{ background: c }}><Bell className="size-3.5" />جرّب على الجزيرة</span>;

/* A: a side list with coloured icons, cards on the other side */
const Side = () => win(<div className="flex h-full">
  <nav className="flex w-52 flex-col gap-1 border-s border-white/5 bg-white/[.02] p-3">
    <span className="mb-2 flex items-center gap-2 rounded-[10px] bg-white/[.06] px-2.5 py-1.5 text-[12px] text-ink-3"><Search className="size-3.5" />دوّر في الإعدادات…</span>
    {SECTIONS.map(([n, I, c], i) => <span key={n} className={`flex items-center gap-2.5 rounded-[10px] px-2 py-1.5 text-[12.5px] ${i === 1 ? 'bg-white/[.08]' : ''}`}><span className="grid size-6 place-items-center rounded-[7px]" style={{ background: c }}><I className="size-3.5 text-white" /></span>{n}</span>)}
  </nav>
  <main className="flex-1 overflow-hidden p-5">
    <div className="mb-4 grid place-items-center rounded-[16px] py-5" style={{ background: 'radial-gradient(circle at 50% 120%, #3CC2B433, transparent 60%), rgba(255,255,255,.03)' }}><Island accent="#3CC2B4" /></div>
    <h2 className="m-0 mb-2.5 font-display text-[16px]">الجزيرة بتعرض إيه</h2>
    <Rows />
  </main>
</div>);

/* B: a home of big coloured tiles; each opens its own page */
const Tiles = () => win(<div className="flex h-full flex-col gap-4 p-5">
  <div className="flex items-center gap-3"><span className="flex flex-1 items-center gap-2 rounded-full bg-white/[.06] px-4 py-2 text-[12.5px] text-ink-3"><Search className="size-4" />دوّر في الإعدادات…</span><Island accent="#3CC2B4" /></div>
  <div className="grid grid-cols-4 gap-3">
    {SECTIONS.map(([n, I, c]) => (
      <span key={n} className="flex h-[118px] flex-col justify-between rounded-[18px] p-3.5" style={{ background: `linear-gradient(150deg, ${c}38, ${c}0d)`, boxShadow: `inset 0 0 0 1px ${c}33` }}>
        <span className="grid size-9 place-items-center rounded-[11px]" style={{ background: c }}><I className="size-5 text-white" /></span>
        <span className="flex items-center justify-between text-[13px] font-semibold">{n}<ChevronLeft className="size-4 text-ink-3" /></span>
      </span>
    ))}
  </div>
  <div className="flex items-center gap-3 rounded-[16px] bg-white/[.04] px-4 py-3"><Palette className="size-5 text-[#C792EA]" /><span className="flex-1 text-[12.5px]">الشكل: فيروزي</span><Themes /></div>
</div>);

/* C: one long page; a live island on top that changes with the theme, coloured section headers, chips to jump */
const Scroll = () => win(<div className="flex h-full flex-col">
  <div className="grid place-items-center gap-3 py-5" style={{ background: 'linear-gradient(180deg, #3CC2B426, transparent)' }}>
    <Island accent="#3CC2B4" wide />
    <div className="flex flex-wrap justify-center gap-1.5 px-4">{SECTIONS.map(([n, , c], i) => <span key={n} className="rounded-full px-2.5 py-1 text-[11px]" style={i === 0 ? { background: c, color: '#050507' } : { background: 'rgba(255,255,255,.06)' }}>{n}</span>)}</div>
  </div>
  <div className="flex-1 overflow-hidden px-8 pb-6">
    <h2 className="m-0 mb-2.5 flex items-center gap-2 font-display text-[16px]"><span className="grid size-7 place-items-center rounded-[8px] bg-[#C792EA]"><Palette className="size-4 text-white" /></span>الشكل</h2>
    <Themes big />
    <div className="mt-3 flex items-center justify-between rounded-[14px] bg-white/[.04] px-3.5 py-2.5 text-[12.5px]">حركة أقل<Switch on={false} /></div>
    <div className="mt-3"><Try c="#3CC2B4" /></div>
    <h2 className="m-0 mt-5 mb-2.5 flex items-center gap-2 font-display text-[16px]"><span className="grid size-7 place-items-center rounded-[8px] bg-[#3CC2B4]"><Eye className="size-4 text-white" /></span>الجزيرة بتعرض إيه</h2>
    <Rows />
  </div>
</div>);

const NAMES: Record<Variant, [string, string, () => ReactNode]> = {
  side: ['أ. القايمة الجانبية', 'زي إعدادات Windows 11 و macOS: أقسام بأيقونات ملوّنة على الجنب، وجزيرة حية فوق كل قسم بتتغير مع اختياراتك.', Side],
  tiles: ['ب. المربعات', 'الشاشة الأولى مربعات كبيرة ملوّنة لكل قسم، ودوسة بتفتح صفحته. زي إعدادات الموبايل.', Tiles],
  scroll: ['ج. الصفحة الواحدة', 'كل حاجة في صفحة واحدة بتنزل فيها، والجزيرة الحية ثابتة فوق، وأزرار سريعة للأقسام.', Scroll],
};

export function SettingsOptions() {
  return (
    <div dir="rtl" className="h-full overflow-auto bg-[#1b1b1e] p-7 font-ui text-ink">
      <div className="flex flex-wrap items-start gap-8">
        {(['side', 'tiles', 'scroll'] as Variant[]).map(v => {
          const [name, about, View] = NAMES[v];
          return (
            <section key={v} className="flex w-[760px] flex-col gap-2">
              <h2 className="m-0 font-display text-lg font-semibold">{name}</h2>
              <p className="m-0 mb-1 text-[12.5px] text-ink-2">{about}</p>
              <View />
            </section>
          );
        })}
      </div>
    </div>
  );
}
