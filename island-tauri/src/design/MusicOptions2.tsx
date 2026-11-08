// Second round for interface 4: livelier directions after "too plain and boring". Review page only: ?music2
// Motion can't show in a picture: each option says what moves.
import { Battery, Cpu, MemoryStick, Clipboard, Grid2x2, Inbox, Mic, MoreHorizontal, Pause, PenLine, SkipBack, SkipForward, CloudSun } from 'lucide-react';
import type { ReactNode } from 'react';

type Variant = 'pulse' | 'hero' | 'vinyl';
const C = '#F0A43A';                                   // the colour picked from the cover
const C2 = '#7A3A12';
const COVER = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="#1d1408"/><circle cx="60" cy="72" r="38" fill="#F0A43A"/><rect x="18" y="16" width="84" height="26" rx="6" fill="#fff3d6"/><circle cx="34" cy="96" r="12" fill="#C2410C"/><circle cx="90" cy="98" r="10" fill="#2E7D32"/></svg>');
const SONG = { title: 'الزئبق | محمد إيشا | مع كامل احتياطي', artist: 'مع كامل احتياطي – Brave', pos: '٤٩:٢٣', dur: '١١٥:٣١', v: 0.43 };

const shell = (children: ReactNode, tint = false) => (
  <div className="relative overflow-hidden bg-island p-4" style={{ width: 400, borderRadius: 30, boxShadow: '0 18px 50px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.06)' }}>
    {tint && <span className="pointer-events-none absolute -top-24 -left-16 size-80 rounded-full opacity-30 blur-3xl" style={{ background: `radial-gradient(${C}, transparent 70%)` }} />}
    <div className="relative">{children}</div>
  </div>
);
const Cover = ({ size, r = 14, glow = false }: { size: number; r?: number; glow?: boolean }) => (
  <img src={COVER} alt="" className="shrink-0 object-cover" style={{ width: size, height: size, borderRadius: r, boxShadow: glow ? `0 8px 28px ${C}66, 0 0 0 1px rgba(255,255,255,.08)` : '0 6px 18px rgba(0,0,0,.4)' }} />
);
const Words = ({ big = false }: { big?: boolean }) => (
  <div className="min-w-0 flex-1">
    <p className={`m-0 truncate font-display font-bold ${big ? 'text-[17px]' : 'text-[15px]'}`}>{SONG.title}</p>
    <p className="m-0 truncate text-[12px]" style={{ color: `${C}cc` }}>{SONG.artist}</p>
  </div>
);
function Controls({ big = false }: { big?: boolean }) {
  return (
    <span dir="ltr" className="flex items-center justify-center gap-4">
      <SkipBack className="size-5" fill="currentColor" />
      <span className={`grid ${big ? 'size-14' : 'size-12'} place-items-center rounded-full text-island`} style={{ background: C, boxShadow: `0 6px 22px ${C}77` }}><Pause className="size-6" fill="currentColor" /></span>
      <SkipForward className="size-5" fill="currentColor" />
    </span>
  );
}
const Progress = () => (
  <div dir="ltr" className="flex items-center gap-2 text-[10.5px] tabular-nums text-ink-2">
    <span>{SONG.pos}</span>
    <span className="relative h-1.5 flex-1 rounded-full bg-white/12">
      <span className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${SONG.v * 100}%`, background: `linear-gradient(90deg, ${C2}, ${C})` }} />
      <span className="absolute top-1/2 size-3 -translate-y-1/2 rounded-full bg-white shadow" style={{ left: `calc(${SONG.v * 100}% - 6px)` }} />
    </span>
    <span>{SONG.dur}</span>
  </div>
);
/** a live spectrum: many thin bars in the song's colour (they dance with the sound) */
const Spectrum = ({ n = 28, h = 26 }: { n?: number; h?: number }) => (
  <span className="flex items-end justify-between" style={{ height: h }}>
    {Array.from({ length: n }, (_, i) => {
      const v = 0.25 + 0.75 * Math.abs(Math.sin(i * 1.7) * Math.cos(i * 0.45));
      return <i key={i} className="w-[3px] rounded-full" style={{ height: `${v * 100}%`, background: `linear-gradient(${C}, ${C2})`, opacity: 0.55 + v * 0.45 }} />;
    })}
  </span>
);
/** the machine, refreshed: an icon and a ring each, instead of grey lines */
function Rings() {
  const items: [typeof Cpu, string, number, string][] = [[Cpu, 'المعالج', 0.27, '#3CC2B4'], [MemoryStick, 'الرامات', 0.77, '#E3B04B'], [Battery, 'البطارية', 0.81, '#7BD88F']];
  return (
    <div className="grid grid-cols-3 gap-2.5">
      {items.map(([I, n, v, c]) => {
        const k = 2 * Math.PI * 15;
        return (
          <div key={n} className="flex items-center gap-2.5 rounded-[18px] bg-white/[.04] px-3 py-2.5 ring-1 ring-white/5">
            <span className="relative grid size-9 place-items-center">
              <svg className="absolute inset-0 -rotate-90" viewBox="0 0 36 36"><circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="3.5" />
                <circle cx="18" cy="18" r="15" fill="none" stroke={c} strokeWidth="3.5" strokeLinecap="round" strokeDasharray={`${k * v} ${k}`} /></svg>
              <I className="size-3.5" style={{ color: c }} />
            </span>
            <span className="flex flex-col leading-tight"><b className="text-[13px] tabular-nums">{Math.round(v * 100)}٪</b><span className="text-[10.5px] text-ink-3">{n}</span></span>
          </div>
        );
      })}
    </div>
  );
}
const Dock = () => (
  <div className="flex items-center justify-between">
    <span className="flex gap-2">
      <span className="flex h-10 items-center gap-1.5 rounded-full bg-ink px-4 text-[13px] font-semibold text-island"><Mic className="size-4" />اتكلم</span>
      <span className="flex h-10 items-center gap-1.5 rounded-full bg-white/[.06] px-4 text-[13px] font-semibold"><PenLine className="size-4" />اكتب</span>
      <span className="grid size-10 place-items-center rounded-full bg-white/[.06]"><MoreHorizontal className="size-4" /></span>
    </span>
    <span className="flex gap-2">{[Grid2x2, Inbox, Clipboard].map((I, i) => <span key={i} className="grid size-10 place-items-center rounded-full bg-white/[.06]"><I className="size-4" /></span>)}</span>
  </div>
);
/** the time shrinks to one line while music plays, so the song gets the room */
const ClockLine = () => (
  <div className="flex items-baseline justify-between px-1">
    <span className="font-display text-[26px] font-bold tabular-nums">٩:١٢ م</span>
    <span className="flex items-center gap-1.5 text-[12px] text-ink-2"><span>السبت ٧ نوفمبر · ٢٧ جمادى الأولى</span><CloudSun className="size-4 text-gold" /><span>١٨°</span></span>
  </div>
);
const Backdrop = ({ strong = false }: { strong?: boolean }) => (
  <>
    <img src={COVER} alt="" className={`pointer-events-none absolute inset-0 size-full scale-150 object-cover blur-2xl ${strong ? 'opacity-70' : 'opacity-50'}`} />
    <span className="pointer-events-none absolute inset-0" style={{ background: `linear-gradient(160deg, ${C}33, rgba(0,0,0,.55) 60%)` }} />
  </>
);

/** A: the song's colour everywhere, a live spectrum under the words, the clock one line */
const Pulse = () => shell(<div className="flex flex-col gap-3">
  <ClockLine />
  <div className="relative overflow-hidden rounded-[22px] p-3.5 ring-1 ring-white/10">
    <Backdrop />
    <div className="relative flex flex-col gap-3">
      <div className="flex items-center gap-3"><Cover size={64} glow /><Words /></div>
      <Spectrum />
      <Controls />
      <Progress />
    </div>
  </div>
  <Rings /><Dock />
</div>, true);

/** B: the cover big beside the words and controls; the panel glows in the song's colour */
const Hero = () => shell(<div className="flex flex-col gap-3">
  <ClockLine />
  <div className="relative overflow-hidden rounded-[24px] p-3.5 ring-1 ring-white/10">
    <Backdrop strong />
    <div className="relative flex gap-3.5">
      <Cover size={112} r={18} glow />
      <div className="flex min-w-0 flex-1 flex-col justify-between">
        <Words big />
        <Controls />
      </div>
    </div>
    <div className="relative mt-3"><Progress /></div>
  </div>
  <Rings /><Dock />
</div>, true);

/** C: the cover as a record that turns while it plays (and stops when paused) */
const Vinyl = () => shell(<div className="flex flex-col gap-3">
  <ClockLine />
  <div className="relative overflow-hidden rounded-[22px] p-3.5 ring-1 ring-white/10">
    <Backdrop />
    <div className="relative flex items-center gap-4">
      <span className="relative grid size-[104px] shrink-0 place-items-center rounded-full"
            style={{ background: 'repeating-radial-gradient(circle, #111 0 2px, #1c1c1c 2px 4px)', boxShadow: `0 8px 30px ${C}55, inset 0 0 0 2px rgba(255,255,255,.06)` }}>
        <span className="overflow-hidden rounded-full ring-2 ring-black/60"><Cover size={52} r={999} /></span>
        <i className="absolute size-2 rounded-full bg-black" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-3"><Words /><Controls /></div>
    </div>
    <div className="relative mt-3"><Spectrum n={36} h={14} /></div>
    <div className="relative mt-2"><Progress /></div>
  </div>
  <Rings /><Dock />
</div>, true);

const NAMES: Record<Variant, [string, string, () => ReactNode]> = {
  pulse: ['أ. النبض', 'لون الأغنية في كل حتة (الزرار، الشريط، توهج الغلاف)، وموجة صوت حية بتتحرك مع الصوت تحت الاسم. الساعة بقت سطر واحد علشان الأغنية تاخد المساحة.', Pulse],
  hero: ['ب. الغلاف الكبير', 'الغلاف كبير قوي جنب الاسم والأزرار، والخلفية أقوى بلون الأغنية، واللوحة كلها منوّرة بلونها من فوق.', Hero],
  vinyl: ['ج. الأسطوانة', 'الغلاف جوه أسطوانة بتلف وانت سامع وبتقف لما توقف، وموجة رفيعة تحتها. الأكثر شخصية.', Vinyl],
};

export function MusicOptions2() {
  return (
    <div dir="rtl" className="h-full overflow-auto bg-[#1b1b1e] p-7 font-ui text-ink">
      <p className="mb-5 text-[13px] text-ink-2">في التلاتة: لون بيتاخد من غلاف الأغنية نفسه، والجهاز بقى حلقات ملوّنة بأيقونات بدل الخطوط الرمادي.</p>
      <div className="flex flex-wrap items-start gap-8">
        {(['pulse', 'hero', 'vinyl'] as Variant[]).map(v => {
          const [name, about, View] = NAMES[v];
          return (
            <section key={v} className="flex w-[400px] flex-col gap-2">
              <h2 className="m-0 font-display text-lg font-semibold">{name}</h2>
              <p className="m-0 mb-1 min-h-[54px] text-[12.5px] text-ink-2">{about}</p>
              <View />
            </section>
          );
        })}
      </div>
    </div>
  );
}
