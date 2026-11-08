// Design options for interface 7 (your day: prayer, focus, water, meetings, Qur'an radio). Review page only: ?day
import { CupSoda, Droplet, MoonStar, Pause, Play, Plus, Radio, Search, Square, Sunrise, Video } from 'lucide-react';
import type { ReactNode } from 'react';

type Variant = 'rings' | 'line' | 'sky';
const GOLD = '#E3B04B', TEAL = '#3CC2B4', BLUE = '#5AA9FF', GREEN = '#7BD88F';
const PR: [string, string, 'past' | 'next' | ''][] = [['الفجر', '٤:٤٥ ص', 'past'], ['الشروق', '٦:١٠ ص', 'past'], ['الظهر', '١١:٤٢ ص', 'past'], ['العصر', '٢:٥٠ م', 'next'], ['المغرب', '٥:١٥ م', ''], ['العشاء', '٦:٣٥ م', '']];
const STATIONS = ['محمد صديق المنشاوي', 'عبد الباسط عبد الصمد', 'محمود خليل الحصري', 'ماهر المعيقلي'];

const shell = (children: ReactNode) => (
  <div className="relative overflow-hidden bg-island p-4" style={{ width: 400, borderRadius: 30, boxShadow: '0 18px 50px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.06)' }}>{children}</div>
);
const tile = 'rounded-[18px] bg-white/[.04] ring-1 ring-white/5';
function Ring({ v, color, size = 44, children }: { v: number; color: string; size?: number; children: ReactNode }) {
  const k = 2 * Math.PI * 15;
  return (
    <span className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg className="absolute inset-0 -rotate-90" viewBox="0 0 36 36"><circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="3" />
        <circle cx="18" cy="18" r="15" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeDasharray={`${k * v} ${k}`} style={{ filter: `drop-shadow(0 0 4px ${color})` }} /></svg>
      {children}
    </span>
  );
}
const Btn = ({ icon: I, color, solid = false }: { icon: typeof Play; color: string; solid?: boolean }) => (
  <span className="grid size-8 place-items-center rounded-full" style={solid ? { background: color, color: '#050507' } : { background: 'rgba(255,255,255,.07)', color }}><I className="size-4" fill={I === Plus ? 'none' : 'currentColor'} /></span>
);
const Meeting = () => (
  <div className={`${tile} flex items-center gap-3 px-3 py-2.5`}>
    <Video className="size-4 shrink-0" style={{ color: BLUE }} /><span className="flex-1 truncate text-[12.5px]">مراجعة المشروع — ٤:٠٠ م <span className="text-ink-3">(بعد ١٢ د)</span></span>
    <span className="rounded-full px-3 py-1 text-[11.5px] font-semibold text-island" style={{ background: BLUE }}>انضم</span>
  </div>
);
const Clock = () => <div className="flex items-baseline justify-between px-1"><span className="font-display text-[26px] font-bold">٢:٢٠ م</span><span className="text-[12px] text-ink-2">السبت ٧ نوفمبر · ٢٧ جمادى الأولى</span></div>;

/* ── A: three rings, like the machine's ── */
const RingsHome = () => shell(<div className="flex flex-col gap-2.5">
  <Clock />
  <div className="grid grid-cols-3 gap-2.5">
    <div className={`${tile} flex flex-col items-center gap-1.5 py-3`}><Ring v={0.78} color={GOLD}><MoonStar className="size-4" style={{ color: GOLD }} /></Ring><b className="text-[13px]">العصر</b><span className="text-[11px] text-ink-2">بعد ٣٠ د</span></div>
    <div className={`${tile} flex flex-col items-center gap-1.5 py-3`}><Ring v={0.72} color={TEAL}><span className="text-[10px] font-bold">١٨:٠٤</span></Ring><b className="text-[13px]">تركيز ٢</b><span className="flex gap-1.5"><Btn icon={Pause} color={TEAL} /><Btn icon={Square} color={TEAL} /></span></div>
    <div className={`${tile} flex flex-col items-center gap-1.5 py-3`}><Ring v={3 / 8} color={BLUE}><Droplet className="size-4" style={{ color: BLUE }} /></Ring><b className="text-[13px]">٣ من ٨</b><Btn icon={Plus} color={BLUE} solid /></div>
  </div>
  <Meeting />
</div>);
const RingsPrayer = () => shell(<div className="flex flex-col gap-3">
  <div className="flex items-center justify-between"><b className="font-display text-[15px]">مواقيت الصلاة <span className="text-[12px] font-normal text-ink-3">القاهرة</span></b><span className="flex items-center gap-1.5 rounded-full bg-white/[.07] px-3 py-1.5 text-[12px]"><Radio className="size-3.5" style={{ color: GREEN }} />إذاعة القرآن</span></div>
  <div className="grid grid-cols-6 gap-1.5">{PR.map(([n, t, st]) => (
    <div key={n} className={`flex flex-col items-center gap-1 rounded-[14px] py-2.5 ${st === 'next' ? '' : st === 'past' ? 'opacity-40' : ''}`}
         style={st === 'next' ? { background: `${GOLD}22`, boxShadow: `inset 0 0 0 1px ${GOLD}66` } : { background: 'rgba(255,255,255,.04)' }}>
      <span className="text-[11px] text-ink-2">{n}</span><b className="text-[12px]" style={st === 'next' ? { color: GOLD } : undefined}>{t}</b>
      {st === 'next' && <span className="text-[10px]" style={{ color: GOLD }}>بعد ٣٠ د</span>}
    </div>))}</div>
</div>);

/* ── B: the day as one line ── */
function DayLine({ big = false }: { big?: boolean }) {
  const pos = [0.05, 0.2, 0.42, 0.62, 0.8, 0.92], now = 0.55;
  return (
    <div className={`relative ${big ? 'h-16' : 'h-10'}`}>
      <span className="absolute inset-x-1 top-1/2 h-1 -translate-y-1/2 rounded-full bg-white/8" />
      <span className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full" style={{ right: 4, width: `${now * 100}%`, background: `linear-gradient(to left, ${GOLD}33, ${GOLD})` }} />
      {pos.map((p, i) => (
        <span key={i} className="absolute top-1/2 flex -translate-y-1/2 translate-x-1/2 flex-col items-center" style={{ right: `${p * 100}%` }}>
          <i className="size-2.5 rounded-full ring-2 ring-island" style={{ background: i === 3 ? GOLD : p < now ? '#8a7440' : 'rgba(255,255,255,.25)' }} />
          {big && <span className={`absolute top-3 whitespace-nowrap text-[10.5px] ${i === 3 ? 'font-bold' : 'text-ink-3'}`} style={i === 3 ? { color: GOLD } : undefined}>{PR[i][0]}</span>}
        </span>
      ))}
      <span className="absolute top-1/2 size-3.5 -translate-y-1/2 translate-x-1/2 rounded-full bg-white shadow-[0_0_12px_#fff8]" style={{ right: `${now * 100}%` }} />
    </div>
  );
}
const LineHome = () => shell(<div className="flex flex-col gap-2.5">
  <Clock />
  <div className={`${tile} px-3.5 py-3`}>
    <div className="flex items-baseline justify-between"><b className="text-[13px]" style={{ color: GOLD }}>العصر ٢:٥٠ م</b><span className="text-[11.5px] text-ink-2">بعد ٣٠ دقيقة</span></div>
    <DayLine />
  </div>
  <div className="grid grid-cols-2 gap-2.5">
    <div className={`${tile} flex items-center gap-2.5 px-3 py-2.5`}><span className="flex-1"><b className="block text-[16px] tabular-nums">١٨:٠٤</b><span className="text-[11px]" style={{ color: TEAL }}>تركيز ٢ من ٤</span></span><Btn icon={Pause} color={TEAL} /></div>
    <div className={`${tile} flex items-center gap-2.5 px-3 py-2.5`}><span className="flex-1"><span className="flex gap-0.5">{Array.from({ length: 8 }, (_, i) => <CupSoda key={i} className="size-3.5" style={{ color: i < 3 ? BLUE : 'rgba(255,255,255,.18)' }} />)}</span><span className="text-[11px] text-ink-2">٣ من ٨ كوبايات</span></span><Btn icon={Plus} color={BLUE} solid /></div>
  </div>
  <Meeting />
</div>);
const LinePrayer = () => shell(<div className="flex flex-col gap-3">
  <div className="flex items-center justify-between"><b className="font-display text-[15px]">مواقيت الصلاة <span className="text-[12px] font-normal text-ink-3">القاهرة</span></b><span className="flex items-center gap-1.5 rounded-full bg-white/[.07] px-3 py-1.5 text-[12px]"><Radio className="size-3.5" style={{ color: GREEN }} />إذاعة القرآن</span></div>
  <div className={`${tile} px-4 pt-3 pb-7`}><DayLine big /></div>
  <div className="grid grid-cols-3 gap-1.5 text-[12px]">{PR.map(([n, t, st]) => <span key={n} className={`flex justify-between rounded-[12px] bg-white/[.04] px-3 py-2 ${st === 'past' ? 'opacity-40' : ''}`} style={st === 'next' ? { color: GOLD, boxShadow: `inset 0 0 0 1px ${GOLD}66` } : undefined}><span>{n}</span><b>{t}</b></span>)}</div>
</div>);

/* ── C: the sky at this hour ── */
const SKY = 'linear-gradient(180deg, #2B6CB0 0%, #5BA3D9 55%, #F6C177 100%)';
const SkyTile = ({ tall = false }: { tall?: boolean }) => (
  <div className={`relative overflow-hidden rounded-[22px] ${tall ? 'h-36' : 'h-[92px]'}`} style={{ background: SKY }}>
    <svg className="absolute inset-0 size-full" viewBox="0 0 368 100" preserveAspectRatio="none"><path d="M10 95 Q184 -20 358 95" fill="none" stroke="rgba(255,255,255,.45)" strokeWidth="1.5" strokeDasharray="4 5" /></svg>
    <span className="absolute size-7 rounded-full" style={{ left: '38%', top: tall ? '18%' : '14%', background: 'radial-gradient(#FFF6D5, #FFD36B 60%, #FFB43400 72%)', boxShadow: '0 0 30px #FFD36B' }} />
    <div className="absolute inset-x-0 bottom-0 flex items-end justify-between bg-gradient-to-t from-black/45 to-transparent px-3.5 pb-2.5 pt-6 text-white">
      <span><b className="block text-[15px]">العصر ٢:٥٠ م</b><span className="text-[11.5px] opacity-85">بعد ٣٠ دقيقة · القاهرة</span></span>
      <Sunrise className="size-5 opacity-80" />
    </div>
  </div>
);
const SkyHome = () => shell(<div className="flex flex-col gap-2.5">
  <Clock />
  <SkyTile />
  <div className="grid grid-cols-2 gap-2.5">
    <div className={`${tile} flex items-center gap-3 px-3 py-2.5`}><Ring v={0.72} color={TEAL} size={40}><span className="text-[9.5px] font-bold">١٨:٠٤</span></Ring><span className="flex-1 text-[12px]"><b className="block">تركيز ٢</b><span style={{ color: TEAL }}>شغال</span></span><Btn icon={Pause} color={TEAL} /></div>
    <div className={`${tile} flex items-center gap-3 px-3 py-2.5`}>
      <span className="relative h-10 w-7 overflow-hidden rounded-b-[8px] rounded-t-[3px] ring-2 ring-white/25"><span className="absolute inset-x-0 bottom-0" style={{ height: '37%', background: `linear-gradient(${BLUE}, #2F6FD0)` }} /></span>
      <span className="flex-1 text-[12px]"><b className="block">٣ من ٨</b><span className="text-ink-2">كوبايات</span></span><Btn icon={Plus} color={BLUE} solid />
    </div>
  </div>
  <Meeting />
</div>);
const SkyPrayer = () => shell(<div className="flex flex-col gap-3">
  <SkyTile tall />
  <div className="grid grid-cols-6 gap-1 text-center">{PR.map(([n, t, st]) => <span key={n} className={`flex flex-col gap-0.5 rounded-[12px] py-2 ${st === 'past' ? 'opacity-40' : ''}`} style={st === 'next' ? { background: `${GOLD}22`, color: GOLD } : undefined}><span className="text-[10.5px]">{n}</span><b className="text-[11.5px]">{t}</b></span>)}</div>
  <span className="flex items-center justify-center gap-1.5 rounded-full bg-white/[.07] py-2 text-[12.5px]"><Radio className="size-4" style={{ color: GREEN }} />إذاعة القرآن</span>
</div>);

/* the radio page, in each option's spirit */
function RadioPage({ v }: { v: Variant }) {
  const big = v === 'sky';
  return shell(<div className="flex flex-col gap-3">
    <div className={`relative flex items-center gap-3 overflow-hidden rounded-[20px] p-3.5 ${big ? 'min-h-[96px]' : ''}`} style={{ background: v === 'sky' ? 'linear-gradient(135deg, #0F3D2E, #1F6F50)' : 'rgba(123,216,143,.08)', boxShadow: `inset 0 0 0 1px ${GREEN}33` }}>
      <span className="grid size-12 shrink-0 place-items-center rounded-full text-island" style={{ background: GREEN, boxShadow: `0 6px 22px ${GREEN}66` }}><Pause className="size-5" fill="currentColor" /></span>
      <span className="flex-1"><b className="block text-[15px]">محمد صديق المنشاوي</b><span className="flex items-center gap-1.5 text-[11.5px]" style={{ color: GREEN }}><i className="size-1.5 rounded-full" style={{ background: GREEN }} />بث مباشر</span></span>
      {v !== 'rings' && <span className="flex h-6 items-end gap-[3px]">{[8, 16, 11, 20, 13, 18, 9].map((h, i) => <i key={i} className="w-[3px] rounded-full" style={{ height: h, background: GREEN }} />)}</span>}
    </div>
    <div className="flex items-center gap-2 rounded-full bg-white/[.06] px-3.5 py-2 text-[12.5px] text-ink-3"><Search className="size-4" />دوّر على قارئ…</div>
    <div className="grid gap-1">{STATIONS.map((s, i) => <span key={s} className="flex items-center justify-between rounded-[12px] px-3 py-2 text-[13px]" style={i === 0 ? { background: `${GREEN}1a`, color: GREEN } : { background: 'rgba(255,255,255,.03)' }}>{s}{i === 0 && <Radio className="size-4" />}</span>)}</div>
  </div>);
}

const NAMES: Record<Variant, [string, string, () => ReactNode, () => ReactNode]> = {
  rings: ['أ. الحلقات', 'الصلاة والتركيز والمياه ٣ حلقات منوّرة جنب بعض، زي حلقات الجهاز. المواقيت مربعات والجاية بالدهبي.', RingsHome, RingsPrayer],
  line: ['ب. خط اليوم', 'يومك خط واحد: الصلوات نقط، ونقطة بيضا منوّرة هي "دلوقتي". المياه كوبايات بتتملي.', LineHome, LinePrayer],
  sky: ['ج. السما', 'مربع الصلاة شكل السما دلوقتي (الفجر، الضهر، المغرب، الليل) والشمس أو القمر ماشيين على قوس. المياه كوباية بتتملي.', SkyHome, SkyPrayer],
};

export function DayOptions() {
  return (
    <div dir="rtl" className="h-full overflow-auto bg-[#1b1b1e] p-7 font-ui text-ink">
      <div className="flex flex-wrap items-start gap-8">
        {(['rings', 'line', 'sky'] as Variant[]).map(v => {
          const [name, about, Home, Prayer] = NAMES[v];
          return (
            <section key={v} className="flex w-[400px] flex-col gap-3">
              <h2 className="m-0 font-display text-lg font-semibold">{name}</h2>
              <p className="m-0 min-h-[56px] text-[12.5px] text-ink-2">{about}</p>
              <Home /><Prayer /><RadioPage v={v} />
            </section>
          );
        })}
      </div>
    </div>
  );
}
