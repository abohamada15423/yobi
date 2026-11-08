// Design options for interface 4 (music: the player tile in the panel, and the short card when the
// song changes). Review page only: ?music
import { Clipboard, Grid2x2, Inbox, Mic, MoreHorizontal, Pause, PenLine, SkipBack, SkipForward } from 'lucide-react';
import type { ReactNode } from 'react';
import { Meter } from '../components/Meter';
import { Bars } from '../components/CompactIsland';

type Variant = 'wide' | 'album' | 'tint';
const ART = 'linear-gradient(135deg, #3CC2B4, #1E5AA8 55%, #E3B04B)';
const T = { title: 'سورة الرحمن', artist: 'محمد صديق المنشاوي – Spotify', pos: '١:٢٤', dur: '٤:٣٠', v: 0.31 };

const shell = (children: ReactNode, w = 400) => (
  <div className="overflow-hidden bg-island p-4" style={{ width: w, borderRadius: 30, boxShadow: '0 18px 50px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.06)' }}>{children}</div>
);
const Art = ({ size, r = 12 }: { size: number; r?: number }) => <span className="block shrink-0" style={{ width: size, height: size, borderRadius: r, background: ART }} />;
function Controls({ big = false }: { big?: boolean }) {
  const s = big ? 'size-11' : 'size-9';
  return (
    <span dir="ltr" className="flex items-center gap-1.5">
      <span className={`grid ${s} place-items-center rounded-pill`}><SkipBack className="size-[18px]" fill="currentColor" /></span>
      <span className={`grid ${big ? 'size-12' : 'size-10'} place-items-center rounded-pill bg-ink text-island`}><Pause className="size-5" fill="currentColor" /></span>
      <span className={`grid ${s} place-items-center rounded-pill`}><SkipForward className="size-[18px]" fill="currentColor" /></span>
    </span>
  );
}
const Timeline = () => (
  <div dir="ltr" className="flex items-center gap-2 text-[10.5px] tabular-nums text-ink-3">
    <span>{T.pos}</span><Meter value={T.v} tone="ink" className="flex-1" /><span>{T.dur}</span>
  </div>
);
const Words = ({ center = false }: { center?: boolean }) => (
  <div className={`min-w-0 ${center ? 'text-center' : ''}`}>
    <p className="m-0 truncate font-display text-[14px] font-semibold">{T.title}</p>
    <p className="m-0 truncate text-[11.5px] text-ink-2">{T.artist}</p>
  </div>
);
const Clock = () => (
  <div className="col-span-3 rounded-[20px] bg-fill-1 px-4 py-3">
    <p className="m-0 font-display text-[34px] leading-none font-semibold">٤:٣٠ م</p>
    <p className="m-0 mt-1.5 text-[12.5px] text-ink-2">السبت، ٧ نوفمبر</p>
  </div>
);
const Stats = () => <>{[['المعالج', 0.12], ['الرامات', 0.63], ['البطارية', 0.81]].map(([n, v]) => (
  <div key={n} className="flex flex-col gap-2 rounded-[18px] bg-fill-1 px-3 py-2.5"><span className="text-[11px] text-ink-2">{n}</span><Meter value={v as number} heat /></div>
))}</>;
const Dock = () => (
  <div className="flex items-center justify-between">
    <span className="flex gap-2">{[Mic, PenLine, MoreHorizontal].map((I, i) => <span key={i} className={`grid h-10 place-items-center rounded-pill ${i === 0 ? 'w-20 bg-ink text-island' : i === 1 ? 'w-20 bg-fill-1' : 'w-10 bg-fill-1'}`}><I className="size-[17px]" /></span>)}</span>
    <span className="flex gap-2">{[Grid2x2, Inbox, Clipboard].map((I, i) => <span key={i} className="grid size-10 place-items-center rounded-pill bg-fill-1"><I className="size-[17px]" /></span>)}</span>
  </div>
);

/** A: one wide tile: art, words, controls in a row; the timeline under it */
const WideTile = () => (
  <div className="col-span-3 flex flex-col gap-2.5 rounded-[20px] bg-fill-1 p-3">
    <div className="flex items-center gap-3"><Art size={52} /><div className="flex-1 min-w-0"><Words /></div><Controls /></div>
    <Timeline />
  </div>
);
/** B: the art as its own square tile; words, controls and timeline beside it */
const AlbumTile = () => (
  <>
    <div className="row-span-1 overflow-hidden rounded-[18px]"><Art size={116} r={18} /></div>
    <div className="col-span-2 flex flex-col justify-between gap-2 rounded-[18px] bg-fill-1 p-3">
      <Words /><div className="flex justify-center"><Controls /></div><Timeline />
    </div>
  </>
);
/** C: the tile takes the art's colours (a soft blur of it behind), controls centred */
const TintTile = () => (
  <div className="relative col-span-3 overflow-hidden rounded-[20px] p-3.5">
    <span className="absolute inset-0 scale-150 opacity-45 blur-2xl" style={{ background: ART }} />
    <span className="absolute inset-0 bg-black/35" />
    <div className="relative flex flex-col gap-2.5">
      <div className="flex items-center gap-3"><Art size={56} /><div className="flex-1 min-w-0"><Words /></div></div>
      <div className="flex justify-center"><Controls big /></div>
      <Timeline />
    </div>
  </div>
);

/** the short card when the song changes (3.6 s), per option */
function Peek({ v }: { v: Variant }) {
  const inner = (
    <div className="flex items-center gap-3">
      <Art size={v === 'album' ? 44 : 38} r={v === 'album' ? 12 : 10} /><div className="flex-1 min-w-0"><Words /></div><Bars level={0.7} />
    </div>
  );
  return (
    <div className="relative overflow-hidden bg-island px-3 py-2.5" style={{ width: 330, borderRadius: 26, boxShadow: '0 12px 30px rgba(0,0,0,.45)' }}>
      {v === 'tint' && <><span className="absolute inset-0 scale-150 opacity-40 blur-2xl" style={{ background: ART }} /><span className="absolute inset-0 bg-black/40" /></>}
      <div className="relative">{inner}</div>
    </div>
  );
}

const NAMES: Record<Variant, [string, string, () => ReactNode]> = {
  wide: ['أ. المربع العريض', 'كل حاجة في سطر: الصورة، الاسم، والأزرار، والوقت تحتهم. صغير وما بياخدش مساحة.', WideTile],
  album: ['ب. صورة الألبوم', 'الصورة مربع لوحدها كبيرة، والاسم والأزرار في مربع جنبها. زي Control Center.', AlbumTile],
  tint: ['ج. بلون الأغنية', 'المربع بياخد ألوان صورة الأغنية (ضباب خفيف وراه)، والأزرار في النص أكبر. الأحلى بس أكبر.', TintTile],
};

export function MusicOptions() {
  return (
    <div dir="rtl" className="h-full overflow-auto bg-[#1b1b1e] p-7 font-ui text-ink">
      {(['wide', 'album', 'tint'] as Variant[]).map(v => {
        const [name, about, Tile] = NAMES[v];
        return (
          <section key={v} className="mb-7">
            <h2 className="font-display text-lg font-semibold">{name}</h2>
            <p className="mb-3 text-[13px] text-ink-2">{about}</p>
            <div className="flex flex-wrap items-start gap-6">
              <figure className="m-0 flex flex-col items-center gap-1.5">
                {shell(<div className="flex flex-col gap-3"><div className="grid grid-cols-3 gap-2.5"><Clock /><Tile /><Stats /></div><Dock /></div>)}
                <figcaption className="text-[11px] text-ink-3">اللوحة والأغنية شغالة</figcaption>
              </figure>
              <figure className="m-0 flex flex-col items-center gap-1.5"><Peek v={v} /><figcaption className="text-[11px] text-ink-3">أغنية جديدة (٣.٦ ثانية)</figcaption></figure>
            </div>
          </section>
        );
      })}
    </div>
  );
}
