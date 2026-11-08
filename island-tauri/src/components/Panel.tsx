// Interface 3: the open panel (design C, "tiles"): a wide tile for the time, small tiles for the
// machine, then the dock. The menu and the writing box take the dock's place; pages take the tiles'.
import { AnimatePresence, motion } from 'motion/react';
import { Battery, BatteryCharging, Clipboard, Cpu, Grid2x2, History, Inbox, MemoryStick, Mic, MoreHorizontal, PenLine, SendHorizontal, Settings2, Sparkles, type LucideIcon } from 'lucide-react';
import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { bridge } from '../bridge';
import { closePanel, openChat, sendChat, showPage, toggleMenu } from '../panel';
import { useIsland, type Page } from '../store';
import { spring, stagger } from '../motion';
import { IconButton } from './IconButton';
import { useNow } from './CompactIsland';
import { WX_ICON } from './IdleInfo';
import { MusicTile } from './Music';
import { DayTiles, PrayerPage, RadioPage, SkyTile } from './Day';
import { AppsPage, ClipsPage, DownloadsRow, HistoryPage, ShelfPage } from './Work';
import { songVars, useSongColor } from '../songColor';
import { T, WEATHER, dir, fmt } from '../i18n';

const pct = fmt.pct;
const WX = WEATHER;

const Tile = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <motion.div variants={{ hide: { opacity: 0, y: -6, scale: 0.97 }, show: { opacity: 1, y: 0, scale: 1, transition: spring.content } }}
              className={`rounded-[18px] bg-fill-1 ${className}`}>{children}</motion.div>
);

/** the time: a big tile, or one line while music plays so the song gets the room */
function ClockTile() {
  const now = useNow(10_000);
  const music = useIsland(s => s.media.has);
  const weather = useIsland(s => (s.prefs.weather !== false ? s.weather : null));
  const Icon = weather ? WX_ICON(weather.code, weather.is_day) : null;
  const wx = weather && Icon && (
    <span className="inline-flex items-center gap-1" title={T(`${WX(weather.code)} · العظمى ${fmt.num(weather.hi)}° والصغرى ${fmt.num(weather.lo)}°`, `${WX(weather.code)} · high ${weather.hi}°, low ${weather.lo}°`)}>
      <Icon className="size-4 text-gold" />{fmt.num(weather.temp)}°
    </span>
  );
  if (music) return (
    <Tile className="col-span-3 flex items-baseline justify-between bg-transparent px-1">
      <span className="font-display text-[26px] font-bold tabular-nums">{fmt.clock(now)}</span>
      <span className="flex items-center gap-2 text-[12px] text-ink-2">{fmt.date(now)}{wx}</span>
    </Tile>
  );
  return (
    <Tile className="col-span-3 flex items-start justify-between rounded-[20px] px-4 py-3">
      <span>
        <p className="m-0 font-display text-[34px] leading-none font-bold tabular-nums">{fmt.clock(now)}</p>
        <p className="m-0 mt-1.5 text-[12.5px] text-ink-2">{fmt.date(now)}</p>
        <p className="m-0 text-[12px] text-ink-3">{fmt.hijri(now, true)}</p>
      </span>
      {weather && <span className="mt-1 flex flex-col items-end text-[12px] text-ink-2">{wx}<span className="text-[11px] text-ink-3">{WX(weather.code)}</span></span>}
    </Tile>
  );
}

/** one machine reading: a ring in its own colour with its icon, the number beside it */
function Ring({ icon: I, name, value, color, title }: { icon: LucideIcon; name: string; value: number; color: string; title?: string }) {
  const k = 2 * Math.PI * 15, v = Math.max(0, Math.min(1, value || 0));
  return (
    <div className="flex items-center gap-2.5 rounded-[18px] bg-white/[.04] px-3 py-2.5 ring-1 ring-white/5" title={title}
         role="meter" aria-label={name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)}>
      <span className="relative grid size-9 shrink-0 place-items-center">
        <svg className="absolute inset-0 -rotate-90" viewBox="0 0 36 36" aria-hidden="true">
          <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255,255,255,.08)" strokeWidth="3.5" />
          <motion.circle cx="18" cy="18" r="15" fill="none" stroke={color} strokeWidth="3.5" strokeLinecap="round"
                         initial={false} animate={{ strokeDashoffset: k * (1 - v) }} strokeDasharray={k} transition={spring.content} />
        </svg>
        <I className="size-3.5" style={{ color }} aria-hidden="true" />
      </span>
      <span className="flex flex-col leading-tight"><b className="text-[13px] tabular-nums">{pct(v * 100)}</b><span className="text-[10.5px] text-ink-3">{name}</span></span>
    </div>
  );
}

const HOT = 'var(--color-alert)';
function Machine() {
  const st = useIsland(s => s.stats);
  if (!st) return null;
  const gb = (b: number) => (b / 2 ** 30).toFixed(1);
  const bat = st.battery;
  return (
    <Tile className={`col-span-3 grid gap-2.5 bg-transparent ${bat ? 'grid-cols-3' : 'grid-cols-2'}`}>
      <Ring icon={Cpu} name={T('المعالج', 'CPU')} value={st.cpu} color={st.cpu >= 0.9 ? HOT : 'var(--color-accent)'} />
      <Ring icon={MemoryStick} name={T('الرامات', 'Memory')} value={st.ram} color={st.ram >= 0.9 ? HOT : 'var(--color-gold)'} title={`${gb(st.ram_used)} / ${gb(st.ram_total)} GB`} />
      {bat && <Ring icon={bat.plugged ? BatteryCharging : Battery} name={T('البطارية', 'Battery')} value={bat.percent / 100}
                    color={bat.percent <= 20 && !bat.plugged ? HOT : '#7BD88F'} />}
    </Tile>
  );
}

/** who has the mic or the camera, and a lost internet: a quiet line under the tiles */
function Privacy() {
  const { mic, cam } = useIsland(s => s.privacy);
  const offline = useIsland(s => s.offline);
  const sep = T('، ', ', ');
  const who = [mic.length ? `${T('المايك', 'Microphone')}: ${mic.join(sep)}` : '', cam.length ? `${T('الكاميرا', 'Camera')}: ${cam.join(sep)}` : '', offline ? T('النت مقطوع', 'Offline') : ''].filter(Boolean);
  if (!who.length) return null;
  return <Tile className="col-span-3 px-3 py-2 text-[11.5px] text-ink-2"><span dir="auto">{who.join(' — ')}</span></Tile>;
}

function Home() {
  const prayer = useIsland(s => !!s.prayer);
  const music = useIsland(s => s.media.has);
  return (
    <motion.div className="grid grid-cols-3 gap-2.5" variants={{ show: { transition: stagger } }} initial="hide" animate="show">
      {prayer ? <SkyTile size={music ? 'slim' : 'normal'} /> : <ClockTile />}<MusicTile /><DayTiles /><DownloadsRow /><Machine /><Privacy />
    </motion.div>
  );
}

function Dock() {
  const page = useIsland(s => s.panel.page);
  const menu = useIsland(s => s.panel.menu);
  const go = (p: Page) => () => showPage(p);
  return (
    <div data-dock className="flex items-center justify-between">
      <span className="flex gap-2">
        <IconButton icon={Mic} text={T('اتكلم', 'Talk')} label={T('كلّم يوبي من غير ما تنده', 'Talk to Yobi without the wake word')} tone="solid"
                    onClick={() => { closePanel(true); bridge.send({ t: 'quick', id: 'listen' }); }} />
        <IconButton icon={PenLine} text={T('اكتب', 'Write')} label={T('اكتب رسالة ليوبي', 'Write to Yobi')} onClick={openChat} />
        <IconButton icon={MoreHorizontal} label={T('خيارات تانية', 'More')} pressed={menu} onClick={toggleMenu} />
      </span>
      <span className="flex gap-2">
        <IconButton icon={Grid2x2} label={T('التطبيقات', 'Apps')} pressed={page === 'apps'} onClick={go('apps')} />
        <IconButton icon={Inbox} label={T('الرف', 'Shelf')} pressed={page === 'shelf'} onClick={go('shelf')} />
        <IconButton icon={Clipboard} label={T('الحافظة', 'Clipboard')} pressed={page === 'clips'} onClick={go('clips')} />
      </span>
    </div>
  );
}

function Chat() {
  const [text, setText] = useState('');
  return (
    <form className="flex items-center gap-2" onSubmit={e => { e.preventDefault(); sendChat(text); }}>
      <input autoFocus dir="auto" autoComplete="off" value={text} onChange={e => setText(e.target.value)}
             placeholder={T('اكتب ليوبي…', 'Write to Yobi…')} aria-label={T('رسالة ليوبي', 'Message to Yobi')}
             className="h-10 min-w-0 flex-1 rounded-pill bg-fill-1 px-4 text-[13px] text-ink outline-none placeholder:text-ink-3 focus:ring-1 focus:ring-accent/60" />
      <IconButton icon={SendHorizontal} label={T('ابعت', 'Send')} tone="solid" disabled={!text.trim()} onClick={() => sendChat(text)} />
    </form>
  );
}

function Switch({ name, on, id }: { name: string; on: boolean | null; id: string }) {
  return (
    <button type="button" role="menuitemcheckbox" aria-checked={!!on} disabled={on === null}
            onClick={() => bridge.send({ t: 'menu', id })}
            className="flex h-10 items-center justify-between rounded-[14px] px-3 text-[13px] hover:bg-fill-2 disabled:opacity-50">
      {name}
      <span className={`flex h-[22px] w-[38px] items-center rounded-pill p-[2px] transition-colors ${on ? 'bg-accent' : 'bg-line'}`}>
        <motion.i layout transition={spring.micro} className={`size-[18px] rounded-pill bg-ink ${on ? 'ms-auto' : 'me-auto'}`} />
      </span>
    </button>
  );
}

function Menu() {
  const m = useIsland(s => s.menu);
  const item = 'flex h-10 items-center justify-center gap-1.5 rounded-[14px] bg-fill-1 text-[12.5px] hover:bg-fill-2';
  return (
    <motion.div role="menu" className="flex flex-col gap-2.5" variants={{ show: { transition: stagger } }} initial="hide" animate="show">
      <Tile className="grid gap-0.5 rounded-[20px] p-1.5">
        <Switch name={T('الاستماع', 'Listening')} on={m.listen} id="toggle_listen" />
        <Switch name={T('الرد بالصوت', 'Spoken replies')} on={m.voice} id="toggle_voice" />
        <Switch name={T('أسئلة يوبي', 'Yobi’s questions')} on={m.companion} id="toggle_companion" />
      </Tile>
      <motion.div className="grid grid-cols-3 gap-2" variants={{ hide: { opacity: 0 }, show: { opacity: 1, transition: spring.content } }}>
        <button type="button" role="menuitem" className={item} onClick={() => showPage('history')}><History className="size-4" />{T('اللي فات', 'History')}</button>
        <button type="button" role="menuitem" className={item} onClick={() => { closePanel(true); bridge.openSettings(); }}><Settings2 className="size-4" />{T('الإعدادات', 'Settings')}</button>
        <button type="button" role="menuitem" className={item} onClick={() => { closePanel(true); bridge.send({ t: 'menu', id: 'demo' }); }}><Sparkles className="size-4" />{T('جرّب الحالات', 'Demo')}</button>
      </motion.div>
      <motion.button type="button" role="menuitem" variants={{ hide: { opacity: 0 }, show: { opacity: 1, transition: spring.content } }}
                     onClick={() => { closePanel(true); bridge.send({ t: 'menu', id: 'quit' }); }}
                     className="h-10 rounded-[14px] bg-alert/15 text-[13px] font-semibold text-alert hover:bg-alert/25">{T('اقفل يوبي', 'Quit Yobi')}</motion.button>
    </motion.div>
  );
}

/** The open panel. It measures itself and tells the island how big to be. */
export function Panel({ onSize }: { onSize: (w: number, h: number) => void }) {
  const p = useIsland(s => s.panel);
  const box = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(() => onSize(Math.ceil(el.offsetWidth), Math.ceil(el.offsetHeight)));
    ro.observe(el);
    return () => ro.disconnect();
  }, [onSize]);
  const body = p.menu ? 'menu' : p.page;
  const music = useIsland(s => s.media.has);
  const dropping = useIsland(s => s.dropping);
  const col = useSongColor(useIsland(s => s.media.art));
  return (
    <div ref={box} dir={dir()} className="absolute top-0 left-1/2 flex w-[400px] -translate-x-1/2 flex-col gap-3 p-4" style={songVars(col)}>
      {music && <span aria-hidden="true" className="pointer-events-none absolute -top-24 -left-16 -z-10 size-80 rounded-full opacity-30 blur-3xl"
                      style={{ background: 'radial-gradient(var(--song), transparent 70%)' }} />}
      {dropping && <span aria-hidden="true" className="pointer-events-none absolute inset-1.5 rounded-[26px] border-2 border-dashed border-accent/70 bg-accent/5" />}
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.div key={body} exit={{ opacity: 0, transition: { duration: 0.1 } }}>
          {body === 'menu' ? <Menu /> : body === 'home' ? <Home /> : body === 'prayer' ? <PrayerPage /> : body === 'radio' ? <RadioPage />
            : body === 'apps' ? <AppsPage /> : body === 'shelf' ? <ShelfPage /> : body === 'clips' ? <ClipsPage /> : body === 'history' ? <HistoryPage /> : null}
        </motion.div>
      </AnimatePresence>
      {p.chat ? <Chat /> : <Dock />}
    </div>
  );
}

