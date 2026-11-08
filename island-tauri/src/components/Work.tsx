// Interface 8: the work pages (design C, "coloured cards"): every item is a card in its own colour —
// an app's (picked from its icon), a file type's, a moment's. Apps, shelf, clipboard, history,
// and the downloads row on the home page.
import { motion } from 'motion/react';
import {
  AppWindow, ArrowRight, Check, Copy, Download, File, FileArchive, FileText, Film, Folder, FolderOpen, ImageIcon, Music2,
  Pencil, Plus, Search, Trash2, X, type LucideIcon,
} from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { bridge } from '../bridge';
import { borrowKeyboard, closePanel } from '../panel';
import { useIsland } from '../store';
import { spring } from '../motion';
import { useSongColor } from '../songColor';
import type { PinnedApp, ShelfItem } from '../types';
import { fmtBytes } from './CompactIsland';

const nf = new Intl.NumberFormat('ar-EG');
const clockFmt = new Intl.DateTimeFormat('ar-EG', { hour: 'numeric', minute: '2-digit' });
const tint = (c: string) => ({ background: `linear-gradient(160deg, color-mix(in srgb, ${c} 16%, transparent), rgba(255,255,255,.03) 70%)`, boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${c} 22%, transparent)` });
const item = { hide: { opacity: 0, y: -6, scale: 0.97 }, show: { opacity: 1, y: 0, scale: 1, transition: spring.content } };
const list = { show: { transition: { staggerChildren: 0.025 } } };

/** a file's or app's icon from Windows, cached for the island's life */
const icons = new Map<string, Promise<string>>();
function useIcon(path?: string) {
  const [src, setSrc] = useState('');
  useEffect(() => {
    if (!path) return;
    let live = true;
    if (!icons.has(path)) icons.set(path, bridge.fileIcon(path));
    void icons.get(path)!.then(s => { if (live) setSrc(s); });
    return () => { live = false; };
  }, [path]);
  return src;
}
/** a stable colour from a name, for apps whose icon we don't have yet */
const nameHue = (s: string) => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);

/** the page's title row: back, title, and the page's action */
function Head({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="flex items-center gap-2">
        <button type="button" onClick={() => useIsland.getState().setPanel({ page: 'home' })} aria-label="رجوع" title="رجوع"
                className="grid size-8 place-items-center rounded-full bg-white/[.07] hover:bg-white/[.12]"><ArrowRight className="size-4" /></button>
        <b className="font-display text-[15px]">{title}</b>
      </span>
      {children}
    </div>
  );
}
const Action = ({ icon: I, label, onClick, pressed }: { icon: LucideIcon; label: string; onClick: () => void; pressed?: boolean }) => (
  <button type="button" onClick={onClick} aria-pressed={pressed}
          className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[12px] ${pressed ? 'bg-accent text-island' : 'bg-white/[.07] hover:bg-white/[.12]'}`}>
    <I className="size-3.5" />{label}
  </button>
);
const Empty = ({ children }: { children: ReactNode }) => <p className="m-0 rounded-[18px] bg-white/[.03] px-4 py-6 text-center text-[12.5px] text-ink-3">{children}</p>;

/* ── apps ── */
function AppCard({ app, edit }: { app: PinnedApp; edit: boolean }) {
  const icon = useIcon(app.icon);
  const picked = useSongColor(icon || null).c;
  const color = icon ? picked : `hsl(${nameHue(app.name)} 70% 60%)`;
  return (
    <motion.div variants={item} className="relative">
      <button type="button" title={app.name} onClick={() => { if (!edit) { bridge.send({ t: 'app_open', name: app.name }); closePanel(true); } }}
              className="flex w-full flex-col items-center gap-2 rounded-[18px] px-2 py-3 transition-transform hover:scale-[1.03]" style={tint(color)}>
        <span className="relative">
          {icon ? <img src={icon} alt="" className="size-10 object-contain drop-shadow-[0_4px_10px_rgba(0,0,0,.35)]" />
            : <span className="grid size-10 place-items-center rounded-[12px] text-[16px] font-bold text-white" style={{ background: color }}>{app.name.trim().charAt(0).toUpperCase()}</span>}
          {app.running && <i className="absolute -bottom-1.5 left-1/2 size-1.5 -translate-x-1/2 rounded-full bg-accent shadow-[0_0_6px_var(--color-accent)]" title="مفتوح" />}
        </span>
        <span dir="auto" className="w-full truncate text-center text-[11.5px]">{app.name}</span>
      </button>
      {edit && (
        <button type="button" onClick={() => bridge.send({ t: 'app_unpin', name: app.name })} aria-label={`شيل ${app.name}`}
                className="absolute -top-1.5 -left-1.5 grid size-6 place-items-center rounded-full bg-alert text-white shadow"><X className="size-3.5" /></button>
      )}
    </motion.div>
  );
}
export function AppsPage() {
  const apps = useIsland(s => s.apps);
  const [edit, setEdit] = useState(false);
  const [picking, setPicking] = useState(false);
  const [q, setQ] = useState('');
  const have = new Set(apps.pinned.map(a => a.name.toLowerCase()));
  const choices = (apps.catalog || []).filter(n => !have.has(n.toLowerCase()) && (!q.trim() || n.toLowerCase().includes(q.trim().toLowerCase()))).slice(0, 40);
  return (
    <div className="flex flex-col gap-3">
      <Head title="التطبيقات"><Action icon={edit ? Check : Pencil} label={edit ? 'خلصت' : 'تعديل'} pressed={edit} onClick={() => { setEdit(!edit); setPicking(false); }} /></Head>
      {picking ? (
        <>
          <label className="flex items-center gap-2 rounded-full bg-white/[.06] px-3.5 py-2 text-[12.5px] focus-within:ring-1 focus-within:ring-accent/60">
            <Search className="size-4 text-ink-3" aria-hidden="true" />
            <input autoFocus dir="auto" value={q} onChange={e => setQ(e.target.value)} onPointerDown={borrowKeyboard} onFocus={borrowKeyboard}
                   placeholder="دوّر على برنامج…" aria-label="دوّر على برنامج" className="min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-ink-3" />
          </label>
          <div className="grid max-h-[300px] gap-1 overflow-y-auto">
            {apps.catalog === null ? <Empty>بجيب البرامج…</Empty> : choices.map(n => (
              <button key={n} type="button" onClick={() => bridge.send({ t: 'app_pin', name: n })}
                      className="flex items-center justify-between rounded-[12px] bg-white/[.03] px-3 py-2 text-start text-[13px] hover:bg-white/[.07]">
                <bdi>{n}</bdi><Plus className="size-4 text-accent" aria-hidden="true" />
              </button>
            ))}
          </div>
        </>
      ) : !apps.pinned.length && !edit ? <Empty>مفيش برامج متثبتة. دوس "تعديل" وضيف اللي بتفتحه كتير.</Empty> : (
        <motion.div className="grid grid-cols-3 gap-2" variants={list} initial="hide" animate="show">
          {apps.pinned.map(a => <AppCard key={a.name} app={a} edit={edit} />)}
          {edit && apps.pinned.length < 12 && (
            <motion.button variants={item} type="button" onClick={() => { setPicking(true); bridge.send({ t: 'apps_get' }); }}
                           className="flex flex-col items-center justify-center gap-2 rounded-[18px] border border-dashed border-white/20 px-2 py-3 text-ink-2 hover:bg-white/[.04]">
              <Plus className="size-6" /><span className="text-[11.5px]">ضيف</span>
            </motion.button>
          )}
        </motion.div>
      )}
    </div>
  );
}

/* ── shelf ── */
const KIND: [RegExp, LucideIcon, string][] = [
  [/\.(pdf)$/i, FileText, '#E5533D'], [/\.(docx?|txt|md|rtf|odt|xlsx?|csv|pptx?)$/i, FileText, '#7FA8FF'],
  [/\.(zip|rar|7z|tar|gz)$/i, FileArchive, '#E3B04B'], [/\.(png|jpe?g|gif|webp|bmp|svg|heic)$/i, ImageIcon, '#3CC2B4'],
  [/\.(mp4|mkv|mov|avi|webm)$/i, Film, '#C792EA'], [/\.(mp3|wav|flac|m4a|ogg)$/i, Music2, '#F472B6'], [/\.(exe|msi|lnk)$/i, AppWindow, '#5AA9FF'],
];
const kindOf = (it: ShelfItem): [LucideIcon, string] => it.dir ? [Folder, '#E3B04B'] : (KIND.find(([re]) => re.test(it.name))?.slice(1) as [LucideIcon, string]) ?? [File, '#A1A1A6'];

function ShelfCard({ it }: { it: ShelfItem }) {
  const icon = useIcon(it.path);
  const [I, color] = kindOf(it);
  const start = useRef<{ x: number; y: number } | null>(null);
  return (
    <motion.div variants={item} className="group relative">
      <button type="button" title={it.path} onClick={() => bridge.send({ t: 'shelf_open', i: it.i })}
              onPointerDown={e => { start.current = { x: e.clientX, y: e.clientY }; }}
              onPointerUp={() => { start.current = null; }}
              onPointerMove={e => {   // drag it into another app
                const s = start.current;
                if (s && e.buttons === 1 && Math.hypot(e.clientX - s.x, e.clientY - s.y) > 6) { start.current = null; bridge.dragOut(it.path); }
              }}
              className="flex w-full items-center gap-2.5 rounded-[18px] p-2.5 text-start" style={tint(color)}>
        <span className="grid size-9 shrink-0 place-items-center rounded-[10px]" style={{ background: `color-mix(in srgb, ${color} 14%, transparent)`, color }}>
          {icon ? <img src={icon} alt="" className="size-7 object-contain" /> : <I className="size-5" />}
        </span>
        <span className="min-w-0 flex-1 truncate text-[12px]"><bdi>{it.name}</bdi></span>
      </button>
      <span className="absolute -top-1.5 -left-1.5 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
        <button type="button" onClick={() => bridge.send({ t: 'shelf_folder', i: it.i })} aria-label={`وريني مكان ${it.name}`} title="وريني مكانه"
                className="grid size-6 place-items-center rounded-full bg-fill-2 shadow"><FolderOpen className="size-3.5" /></button>
        <button type="button" onClick={() => bridge.send({ t: 'shelf_remove', i: it.i })} aria-label={`شيل ${it.name} من الرف`} title="شيله من الرف"
                className="grid size-6 place-items-center rounded-full bg-alert text-white shadow"><X className="size-3.5" /></button>
      </span>
    </motion.div>
  );
}
export function ShelfPage() {
  const shelf = useIsland(s => s.shelf);
  return (
    <div className="flex flex-col gap-3">
      <Head title="الرف">{shelf.length > 0 && <Action icon={Trash2} label="فضّي الرف" onClick={() => bridge.send({ t: 'shelf_clear' })} />}</Head>
      {!shelf.length ? <Empty>اسحب ملفات على الجزيرة وهتتحط هنا، ومن هنا تسحبها لأي برنامج.</Empty> : (
        <motion.div className="grid max-h-[360px] grid-cols-2 gap-2 overflow-y-auto p-1.5" variants={list} initial="hide" animate="show">
          {shelf.map(it => <ShelfCard key={it.i} it={it} />)}
        </motion.div>
      )}
    </div>
  );
}

/* ── clipboard ── */
export function ClipsPage() {
  const clips = useIsland(s => s.clips);
  const [copied, setCopied] = useState(-1);
  return (
    <div className="flex flex-col gap-3">
      <Head title="الحافظة">{clips.items.length > 0 && <Action icon={Trash2} label="امسح" onClick={() => bridge.send({ t: 'clip_clear' })} />}</Head>
      {!clips.enabled || !clips.items.length
        ? <Empty>{clips.enabled ? 'أي نص تنسخه هيظهر هنا، ودوسة عليه تنسخه تاني' : 'سجل الحافظة مقفول من الإعدادات'}</Empty>
        : (
          <motion.div className="flex max-h-[380px] flex-col gap-2 overflow-y-auto" variants={list} initial="hide" animate="show">
            {clips.items.map((text, i) => (
              <motion.button key={`${i}-${text.slice(0, 20)}`} variants={item} type="button" title="دوس عشان تنسخه"
                             onClick={() => { bridge.send({ t: 'clip_copy', i }); setCopied(i); }}
                             className="flex items-center gap-3 rounded-[18px] px-3.5 py-2.5 text-start text-[12.5px]"
                             style={copied === i ? tint('var(--color-accent)') : { background: 'rgba(255,255,255,.04)' }}>
                <span dir="auto" className="line-clamp-2 min-w-0 flex-1 break-words">{text.replace(/\s+/g, ' ').trim()}</span>
                <span className="flex shrink-0 items-center gap-1 text-[10.5px]" style={{ color: copied === i ? 'var(--color-accent)' : 'var(--color-ink-3)' }}>
                  {copied === i ? <><Check className="size-3.5" />اتنسخ</> : <Copy className="size-3.5" />}
                </span>
              </motion.button>
            ))}
          </motion.div>
        )}
    </div>
  );
}

/* ── history ── */
const LABEL: Record<string, string> = { success: 'تم', error: 'مشكلة', info: 'يوبي', suggesting: 'سؤال' };
const HUE: Record<string, string> = { success: 'var(--color-gold)', error: 'var(--color-alert)', info: 'var(--color-ink-2)', suggesting: '#C792EA', notice: 'var(--color-accent)' };
export function HistoryPage() {
  const history = useIsland(s => s.history);
  return (
    <div className="flex flex-col gap-3">
      <Head title="اللي فات">{history.length > 0 && <Action icon={Trash2} label="امسح" onClick={() => useIsland.setState({ history: [] })} />}</Head>
      {!history.length ? <Empty>اللي يوبي قاله وورّاهولك النهارده هيتجمع هنا.</Empty> : (
        <motion.div className="flex max-h-[380px] flex-col gap-2 overflow-y-auto" variants={list} initial="hide" animate="show">
          {history.map((h, i) => {
            const c = HUE[h.kind] || HUE.notice;
            return (
              <motion.div key={`${h.at}-${i}`} variants={item} className="rounded-[18px] px-3.5 py-2.5" style={tint(c)}>
                <span className="flex justify-between text-[10.5px]"><b style={{ color: c }}><bdi>{h.label || LABEL[h.kind] || ''}</bdi></b><span className="text-ink-3">{clockFmt.format(h.at)}</span></span>
                <p dir="auto" className="m-0 text-[12.5px]">{h.text}</p>
              </motion.div>
            );
          })}
        </motion.div>
      )}
    </div>
  );
}

/** downloads running now: a row on the home page */
export function DownloadsRow() {
  const dl = useIsland(s => s.downloads);
  const d = dl[0];
  if (!d) return null;
  return (
    <motion.div variants={item} className="col-span-3 flex items-center gap-3 rounded-[18px] px-3 py-2.5" style={tint('var(--color-accent)')}>
      <Download className="yobi-pulse size-4 shrink-0 text-accent" aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <span dir="auto" className="block truncate text-[12.5px]">{dl.length > 1 ? `${nf.format(dl.length)} تحميلات — ` : ''}{d.name}</span>
        <span className="text-[11px] text-ink-2">{fmtBytes(d.bytes)} · {fmtBytes(d.speed)}/ث</span>
      </span>
    </motion.div>
  );
}
