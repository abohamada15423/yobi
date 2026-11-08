// Design options for interface 8 (work pages: apps, shelf, clipboard, history). Review page only: ?work
import { ArrowRight, Check, Copy, FileArchive, FileText, Film, FolderOpen, ImageIcon, Pencil, Trash2, X } from 'lucide-react';
import type { ReactNode } from 'react';

type Variant = 'grid' | 'rows' | 'stack';
const APPS: [string, string, boolean][] = [['Discord', '#5865F2', true], ['Google Chrome', '#EA4335', true], ['Visual Studio Code', '#2F80ED', false], ['Spotify', '#1DB954', true], ['Steam', '#1B2838', false], ['Telegram', '#2AABEE', false], ['OBS Studio', '#6B4FBB', false]];
const FILES: [string, typeof FileText, string][] = [['تقرير الشهر.pdf', FileText, '#E5533D'], ['notes.txt', FileText, '#A1A1A6'], ['صور الرحلة.zip', FileArchive, '#E3B04B'], ['screenshot.png', ImageIcon, '#3CC2B4'], ['intro.mp4', Film, '#C792EA']];
const CLIPS = ['اجتماع بكرة الساعة ١١ في المكتب', 'https://github.com/yobi/island/pull/42', 'npm run tauri build', 'شكراً جداً على المساعدة 🙏'];
const HIST: [string, string, string, string][] = [['١٠:٤٥ م', 'تمام', 'تمام، فتحت ديسكورد', '#E3B04B'], ['١٠:٣٠ م', 'الصلاة', 'حان الآن موعد صلاة العشاء', '#E3B04B'], ['١٠:١٢ م', 'اتحمّل', 'movie.mkv — ٧٣٤ م.ب', '#3CC2B4'], ['٩:٥٠ م', 'يوبي', 'الساعة ٩:٥٠، اشرب مياه 💧', '#A1A1A6'], ['٩:٢٠ م', 'خد بريك', 'بقالك ساعتين قدام الشاشة', '#7BD88F']];

const shell = (title: string, action: ReactNode, children: ReactNode) => (
  <div className="overflow-hidden bg-island p-4" style={{ width: 400, borderRadius: 30, boxShadow: '0 18px 50px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.06)' }}>
    <div className="mb-3 flex items-center justify-between">
      <span className="flex items-center gap-2"><span className="grid size-8 place-items-center rounded-full bg-white/[.07]"><ArrowRight className="size-4" /></span><b className="font-display text-[15px]">{title}</b></span>
      {action}
    </div>
    {children}
  </div>
);
const pill = (t: string, icon?: ReactNode, tone = 'bg-white/[.07]') => <span className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] ${tone}`}>{icon}{t}</span>;
const AppIcon = ({ name, color, size = 44 }: { name: string; color: string; size?: number }) => (
  <span className="grid place-items-center rounded-[13px] font-bold text-white" style={{ width: size, height: size, background: `linear-gradient(145deg, ${color}, ${color}aa)`, boxShadow: `0 6px 16px ${color}55`, fontSize: size * 0.4 }}>{name[0]}</span>
);
const Running = () => <i className="absolute -bottom-1 left-1/2 size-1.5 -translate-x-1/2 rounded-full bg-accent shadow-[0_0_6px_var(--color-accent)]" />;
const FileIcon = ({ I, color, size = 40 }: { I: typeof FileText; color: string; size?: number }) => (
  <span className="grid shrink-0 place-items-center rounded-[11px]" style={{ width: size, height: size, background: `${color}22`, color }}><I className="size-5" /></span>
);

/* ── A: a grid of icons and tiles ── */
const GridApps = () => shell('التطبيقات', pill('تعديل', <Pencil className="size-3.5" />), <div className="grid grid-cols-4 gap-x-2 gap-y-3">
  {APPS.map(([n, c, r]) => <span key={n} className="relative flex flex-col items-center gap-1.5"><span className="relative"><AppIcon name={n} color={c} />{r && <Running />}</span><span className="w-full truncate text-center text-[11px] text-ink-2">{n}</span></span>)}
  <span className="flex flex-col items-center gap-1.5"><span className="grid size-11 place-items-center rounded-[13px] border border-dashed border-white/20 text-xl text-ink-3">+</span><span className="text-[11px] text-ink-3">ضيف</span></span>
</div>);
const GridShelf = () => shell('الرف', pill('فضّي الرف', <Trash2 className="size-3.5" />), <div className="grid grid-cols-3 gap-2">
  {FILES.map(([n, I, c]) => <span key={n} className="relative flex flex-col items-center gap-2 rounded-[16px] bg-white/[.04] p-3 ring-1 ring-white/5"><FileIcon I={I} color={c} size={44} /><span className="w-full truncate text-center text-[11.5px]">{n}</span></span>)}
  <span className="grid place-items-center rounded-[16px] border border-dashed border-white/15 p-3 text-center text-[11px] text-ink-3">اسحب ملفات هنا</span>
</div>);
const GridClips = () => shell('الحافظة', pill('امسح', <Trash2 className="size-3.5" />), <div className="grid grid-cols-2 gap-2">
  {CLIPS.map((t, i) => <span key={t} className="relative flex min-h-[64px] flex-col justify-between gap-2 rounded-[16px] bg-white/[.04] p-3 text-[12px] ring-1 ring-white/5" style={i === 0 ? { boxShadow: 'inset 0 0 0 1px var(--color-accent)' } : undefined}><span className="line-clamp-2" dir="auto">{t}</span><span className="flex items-center gap-1 text-[10.5px]" style={{ color: i === 0 ? 'var(--color-accent)' : 'var(--color-ink-3)' }}>{i === 0 ? <><Check className="size-3" />اتنسخ</> : <><Copy className="size-3" />انسخ</>}</span></span>)}
</div>);
const GridHistory = () => shell('اللي فات', pill('امسح', <Trash2 className="size-3.5" />), <div className="relative flex flex-col gap-2.5 ps-4">
  <span className="absolute inset-y-1 start-[5px] w-px bg-white/10" />
  {HIST.map(([t, k, x, c]) => <span key={x} className="relative flex flex-col"><i className="absolute -start-4 top-1.5 size-2.5 rounded-full ring-2 ring-island" style={{ background: c }} /><span className="flex gap-2 text-[11px]"><b style={{ color: c }}>{k}</b><span className="text-ink-3">{t}</span></span><span className="text-[12.5px]">{x}</span></span>)}
</div>);

/* ── B: rows with coloured chips, like the notices ── */
const row = (lead: ReactNode, main: ReactNode, trail?: ReactNode, key?: string) => <span key={key} className="flex items-center gap-3 rounded-[14px] bg-white/[.03] px-2.5 py-2">{lead}<span className="min-w-0 flex-1">{main}</span>{trail}</span>;
const RowsApps = () => shell('التطبيقات', pill('تعديل', <Pencil className="size-3.5" />), <div className="grid grid-cols-2 gap-1.5">
  {APPS.slice(0, 6).map(([n, c, r]) => row(<AppIcon name={n} color={c} size={32} />, <><b className="block truncate text-[12.5px]">{n}</b><span className="text-[10.5px]" style={{ color: r ? 'var(--color-accent)' : 'var(--color-ink-3)' }}>{r ? 'مفتوح' : 'مقفول'}</span></>, undefined, n))}
</div>);
const RowsShelf = () => shell('الرف', pill('فضّي الرف', <Trash2 className="size-3.5" />), <div className="grid gap-1.5">
  {FILES.slice(0, 4).map(([n, I, c]) => row(<FileIcon I={I} color={c} size={34} />, <><b className="block truncate text-[12.5px]">{n}</b><span className="text-[10.5px] text-ink-3">اسحبه لأي برنامج</span></>, <span className="flex gap-1 text-ink-3"><FolderOpen className="size-4" /><X className="size-4" /></span>, n))}
</div>);
const RowsClips = () => shell('الحافظة', pill('امسح', <Trash2 className="size-3.5" />), <div className="grid gap-1.5">
  {CLIPS.map((t, i) => row(<span className="grid size-8 place-items-center rounded-[10px]" style={{ background: i === 0 ? 'color-mix(in srgb, var(--color-accent) 22%, transparent)' : 'rgba(255,255,255,.06)', color: i === 0 ? 'var(--color-accent)' : 'var(--color-ink-2)' }}>{i === 0 ? <Check className="size-4" /> : <Copy className="size-4" />}</span>, <span className="block truncate text-[12.5px]" dir="auto">{t}</span>, undefined, t))}
</div>);
const RowsHistory = () => shell('اللي فات', pill('امسح', <Trash2 className="size-3.5" />), <div className="grid gap-1.5">
  {HIST.map(([t, k, x, c]) => row(<span className="w-1 self-stretch rounded-full" style={{ background: c }} />, <><span className="flex gap-2 text-[10.5px]"><b style={{ color: c }}>{k}</b><span className="text-ink-3">{t}</span></span><span className="block truncate text-[12.5px]">{x}</span></>, undefined, x))}
</div>);

/* ── C: big tiles, each page its own colour ── */
const tint = (c: string) => ({ background: `linear-gradient(160deg, ${c}26, rgba(255,255,255,.03) 70%)`, boxShadow: `inset 0 0 0 1px ${c}33` });
const StackApps = () => shell('التطبيقات', pill('تعديل', <Pencil className="size-3.5" />), <div className="grid grid-cols-3 gap-2">
  {APPS.slice(0, 6).map(([n, c, r]) => <span key={n} className="relative flex flex-col items-center gap-2 rounded-[18px] px-2 py-3" style={tint(c)}><span className="relative"><AppIcon name={n} color={c} size={40} />{r && <Running />}</span><span className="w-full truncate text-center text-[11.5px]">{n}</span></span>)}
</div>);
const StackShelf = () => shell('الرف', pill('فضّي الرف', <Trash2 className="size-3.5" />), <div className="grid grid-cols-2 gap-2">
  {FILES.slice(0, 4).map(([n, I, c]) => <span key={n} className="flex items-center gap-2.5 rounded-[18px] p-2.5" style={tint(c)}><FileIcon I={I} color={c} size={38} /><span className="min-w-0 truncate text-[12px]">{n}</span></span>)}
</div>);
const StackClips = () => shell('الحافظة', pill('امسح', <Trash2 className="size-3.5" />), <div className="flex flex-col gap-2">
  {CLIPS.map((t, i) => <span key={t} className="rounded-[18px] px-3.5 py-2.5 text-[12.5px]" dir="auto" style={i === 0 ? tint('#3CC2B4') : { background: 'rgba(255,255,255,.04)' }}>{t}</span>)}
</div>);
const StackHistory = () => shell('اللي فات', pill('امسح', <Trash2 className="size-3.5" />), <div className="flex flex-col gap-2">
  {HIST.slice(0, 4).map(([t, k, x, c]) => <span key={x} className="rounded-[18px] px-3.5 py-2.5" style={tint(c)}><span className="flex justify-between text-[10.5px]"><b style={{ color: c }}>{k}</b><span className="text-ink-3">{t}</span></span><span className="text-[12.5px]">{x}</span></span>)}
</div>);

const NAMES: Record<Variant, [string, string, (() => ReactNode)[]]> = {
  grid: ['أ. الشبكة', 'التطبيقات أيقونات زي الموبايل بنقطة منوّرة لو مفتوح، والرف ملفات كبيرة، والحافظة كروت، واللي فات خط زمني ملوّن.', [GridApps, GridShelf, GridClips, GridHistory]],
  rows: ['ب. الصفوف', 'كل حاجة صفوف منظمة بشريحة ملوّنة في الأول، زي الإشعارات. الأكتر معلومات في أقل مساحة.', [RowsApps, RowsShelf, RowsClips, RowsHistory]],
  stack: ['ج. الكروت الملوّنة', 'كل عنصر كارت بياخد لون بتاعه (لون التطبيق، نوع الملف، نوع الحدث). الأكتر حياة.', [StackApps, StackShelf, StackClips, StackHistory]],
};

export function WorkOptions() {
  return (
    <div dir="rtl" className="h-full overflow-auto bg-[#1b1b1e] p-7 font-ui text-ink">
      {(['grid', 'rows', 'stack'] as Variant[]).map(v => {
        const [name, about, pages] = NAMES[v];
        return (
          <section key={v} className="mb-8">
            <h2 className="m-0 font-display text-lg font-semibold">{name}</h2>
            <p className="m-0 mb-3 text-[12.5px] text-ink-2">{about}</p>
            <div className="flex flex-wrap items-start gap-5">{pages.map((P, i) => <P key={i} />)}</div>
          </section>
        );
      })}
    </div>
  );
}
