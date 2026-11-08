// Design options for interface 6 (notices: prayer, reminders, meetings, downloads, smart copy,
// morning brief…). Review page only: ?notice
import { BookOpen, Calculator, CheckCircle2, MoonStar, Sunrise, Video, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

type Variant = 'chip' | 'band' | 'spot';
interface N { icon: LucideIcon; color: string; kind: string; text: string; sub?: string; ayah?: boolean; buttons?: string[]; left?: number }
const NS: N[] = [
  { icon: MoonStar, color: '#E3B04B', kind: 'الصلاة', text: 'حان الآن موعد صلاة العصر', sub: '٣:٢٠ م · القاهرة', left: 0.7 },
  { icon: BookOpen, color: '#7BD88F', kind: 'آية', text: '﴿ أَلَا بِذِكْرِ ٱللَّهِ تَطْمَئِنُّ ٱلْقُلُوبُ ﴾', sub: 'الرعد ٢٨', ayah: true, left: 0.45 },
  { icon: CheckCircle2, color: '#3CC2B4', kind: 'اتحمّل', text: 'movie.mkv', sub: '٧٣٤ م.ب', buttons: ['افتح', 'وريني مكانه', 'تمام'], left: 0.8 },
  { icon: Video, color: '#7FA8FF', kind: 'اجتماع', text: 'مراجعة المشروع', sub: 'الساعة ٤:٠٠ م — بعد ٥ دقايق', buttons: ['انضم', 'تمام'], left: 0.9 },
  { icon: Calculator, color: '#C792EA', kind: 'حسبتها', text: '= ١٬٢٤٥', sub: '٣٥ × ٣٥ + ٢٠', buttons: ['انسخ الناتج', 'تمام'], left: 0.5 },
  { icon: Sunrise, color: '#F0A43A', kind: '٢٧ جمادى الأولى ١٤٤٨ هـ', text: 'صباح الفل', sub: 'الجو ٢٣° غائم جزئيًا، والعظمى ٢٧°\nالعصر الساعة ٣:٢٠ م', left: 0.6 },
];

const card = (children: ReactNode, extra = '') => (
  <div className={`relative overflow-hidden bg-island ${extra}`} style={{ width: 380, borderRadius: 28, boxShadow: '0 14px 40px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.06)' }}>{children}</div>
);
const mix = (c: string, p: number) => `color-mix(in srgb, ${c} ${p}%, transparent)`;
const Text = ({ n, center = false }: { n: N; center?: boolean }) => (
  <>
    <p className={`m-0 ${n.ayah ? 'font-quran text-[24px] leading-[1.9]' : 'font-display text-[18px] font-bold leading-snug'} ${center || n.ayah ? 'text-center' : ''}`}>{n.text}</p>
    {n.sub && <p className={`m-0 whitespace-pre-line text-[12px] text-ink-2 ${center || n.ayah ? 'text-center' : ''}`}>{n.sub}</p>}
  </>
);
const Buttons = ({ n, wide = false }: { n: N; wide?: boolean }) => n.buttons ? (
  <div className={`flex gap-2 ${wide ? '' : 'flex-wrap'}`}>
    {n.buttons.map((b, i) => (
      <span key={b} className={`grid h-8 place-items-center rounded-full px-3.5 text-[12px] font-semibold ${wide ? 'flex-1' : ''}`}
            style={i === 0 ? { background: n.color, color: '#050507' } : i === n.buttons!.length - 1 ? { color: 'var(--color-ink-2)' } : { background: 'rgba(255,255,255,.07)' }}>{b}</span>
    ))}
  </div>
) : null;
/** time left: a thin line in the notice's colour that drains */
const Left = ({ n }: { n: N }) => (
  <span className="absolute inset-x-6 bottom-[5px] h-[2px] rounded-full bg-white/8">
    <span className="absolute inset-y-0 start-0 rounded-full" style={{ width: `${(n.left ?? 0) * 100}%`, background: n.color, boxShadow: `0 0 8px ${n.color}` }} />
  </span>
);

/** A: a glowing icon chip at the start, the kind in its colour, then the words and buttons */
const Chip = ({ n }: { n: N }) => card(<div className="flex gap-3.5 px-4 pt-4 pb-5">
  <span className="grid size-10 shrink-0 place-items-center rounded-full" style={{ background: mix(n.color, 18), boxShadow: `0 0 18px ${mix(n.color, 35)}` }}>
    <n.icon className="size-5" style={{ color: n.color }} />
  </span>
  <div className="flex min-w-0 flex-1 flex-col gap-1.5">
    <span className="text-[11.5px] font-semibold" style={{ color: n.color }}>{n.kind}</span>
    <Text n={n} />
    <div className="mt-1"><Buttons n={n} /></div>
  </div>
  <Left n={n} />
</div>);

/** B: the notice's colour washes in from the start like the HUD's liquid, a big faint icon behind */
const Band = ({ n }: { n: N }) => card(<>
  <span className="absolute inset-0" style={{ background: `linear-gradient(to left, ${mix(n.color, 26)}, transparent 70%)` }} />
  <n.icon className="absolute -bottom-6 -left-4 size-32 opacity-[.07]" style={{ color: n.color }} />
  <div className="relative flex flex-col gap-1.5 px-5 pt-4 pb-5">
    <span className="flex items-center gap-1.5 text-[11.5px] font-semibold" style={{ color: n.color }}><n.icon className="size-4" />{n.kind}</span>
    <Text n={n} />
    <div className="mt-1.5"><Buttons n={n} /></div>
  </div>
  <Left n={n} />
</>);

/** C: a big glowing icon on top, everything centred, buttons across the width (like a phone alert) */
const Spot = ({ n }: { n: N }) => card(<>
  <span className="absolute -top-20 left-1/2 size-56 -translate-x-1/2 rounded-full blur-3xl" style={{ background: mix(n.color, 30) }} />
  <div className="relative flex flex-col items-center gap-1.5 px-5 pt-4 pb-5 text-center">
    <span className="mb-1 grid size-12 place-items-center rounded-2xl" style={{ background: mix(n.color, 22), boxShadow: `0 6px 24px ${mix(n.color, 45)}` }}><n.icon className="size-6" style={{ color: n.color }} /></span>
    <span className="text-[11.5px] font-semibold" style={{ color: n.color }}>{n.kind}</span>
    <Text n={n} center />
    {n.buttons && <div className="mt-2 w-full"><Buttons n={n} wide /></div>}
  </div>
  <Left n={n} />
</>);

const NAMES: Record<Variant, [string, string, (p: { n: N }) => ReactNode]> = {
  chip: ['أ. الأيقونة المنوّرة', 'أيقونة منوّرة بلون النوع في الأول، والكلام جنبها. منظم وسهل يتقري بسرعة.', Chip],
  band: ['ب. الموجة', 'لون النوع بيدخل من الجنب زي سايل الـ HUD، وأيقونة كبيرة باهتة ورا. ماشي مع الـ HUD.', Band],
  spot: ['ج. الضوء', 'أيقونة كبيرة منوّرة فوق، وكل حاجة في النص، والأزرار بعرض الكارت. أوضح بس أطول.', Spot],
};

export function NoticeOptions() {
  return (
    <div dir="rtl" className="h-full overflow-auto bg-[#1b1b1e] p-7 font-ui text-ink">
      <p className="mb-5 text-[13px] text-ink-2">كل نوع ليه لون وأيقونة. الخط المنوّر تحت بيقول فاضل قد إيه قبل ما الإشعار يمشي (وبيقف لو وقفت عليه بالماوس).</p>
      <div className="flex flex-wrap items-start gap-8">
        {(['chip', 'band', 'spot'] as Variant[]).map(v => {
          const [name, about, View] = NAMES[v];
          return (
            <section key={v} className="flex w-[380px] flex-col gap-3">
              <h2 className="m-0 font-display text-lg font-semibold">{name}</h2>
              <p className="m-0 min-h-[40px] text-[12.5px] text-ink-2">{about}</p>
              {NS.map(n => <View key={n.kind} n={n} />)}
            </section>
          );
        })}
      </div>
    </div>
  );
}
