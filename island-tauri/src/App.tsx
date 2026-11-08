import { AnimatePresence, MotionConfig, motion } from 'motion/react';
import { useCallback, useEffect, useState } from 'react';
import { Mic, Pause, PenLine, Play, SkipBack, SkipForward } from 'lucide-react';
import { bridge } from './bridge';
import { compactView, edgeOf, fsHidden, hasDots, stillPref, useIsland } from './store';
import { Capsule } from './components/Capsule';
import { IconButton } from './components/IconButton';
import { Meter } from './components/Meter';
import { Celebrate, CompactIsland, compactSize } from './components/CompactIsland';
import { Turn } from './components/Turn';
import { Panel } from './components/Panel';
import { PEEK_SIZE, TrackPeek } from './components/Music';
import { HUD_SIZE, Hud } from './components/Hud';
import { Notice } from './components/Notice';
import { showNotice } from './notices';
import { IN_SETTINGS, pointerEnter, pointerLeave, voiceOpen } from './panel';
import { SettingsWindow } from './components/Settings';
import { dir } from './i18n';
import { YobiFace, type Look } from './components/YobiFace';
import { CompactOptions } from './design/CompactOptions';
import { TurnOptions } from './design/TurnOptions';
import { PanelOptions } from './design/PanelOptions';
import { MusicOptions } from './design/MusicOptions';
import { MusicOptions2 } from './design/MusicOptions2';
import { HudOptions } from './design/HudOptions';
import { NoticeOptions } from './design/NoticeOptions';
import { DayOptions } from './design/DayOptions';
import { WorkOptions } from './design/WorkOptions';
import { SettingsOptions } from './design/SettingsOptions';

/** Python's messages go into the store; the theme follows the settings. */
function useBridge() {
  const apply = useIsland(s => s.apply);
  const theme = useIsland(s => (s.prefs.theme as string) || 'faience');
  useEffect(() => { bridge.onMessage(m => (m.t === 'notice' ? showNotice(m) : m.t === 'open' ? voiceOpen(m.page) : apply(m))); }, [apply]);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  const still = useIsland(stillPref);
  useEffect(() => { document.documentElement.classList.toggle('still', still); }, [still]);
  const l = useIsland(s => (s.prefs.lang === 'en' ? 'en' : 'ar'));
  useEffect(() => { document.documentElement.lang = l; document.documentElement.dir = dir(); }, [l]);
  return { still, lang: l };
}

export default function App() {
  return IN_SETTINGS ? <SettingsWindow /> : <IslandApp />;
}

function IslandApp() {
  const { still, lang } = useBridge();
  const q = new URLSearchParams(location.search);
  return (
    <MotionConfig reducedMotion={still ? 'always' : 'user'}>
      {q.has('gallery') ? <Gallery /> : q.has('options') ? <CompactOptions /> : q.has('turn') ? <TurnOptions /> : q.has('panel') ? <PanelOptions /> : q.has('music') ? <MusicOptions /> : q.has('music2') ? <MusicOptions2 /> : q.has('hud') ? <HudOptions /> : q.has('notice') ? <NoticeOptions /> : q.has('day') ? <DayOptions /> : q.has('work') ? <WorkOptions /> : q.has('settings_options') ? <SettingsOptions /> : <Island key={lang} />}   {/* a new language redraws everything */}
    </MotionConfig>
  );
}

/**
 * The island. Built so far: interface 1 (the compact island + live activities), interface 2
 * (Yobi's turn), interface 3 (the open panel), interface 4 (music), interface 5 (the HUD) and
 * interface 6 (notices).
 */
function Island() {
  const view = useIsland(compactView);
  const dots = useIsland(hasDots);
  const edge = useIsland(edgeOf);
  const hidden = useIsland(fsHidden);
  const turn = useIsland(s => s.state !== 'idle');
  const open = useIsland(s => s.panel.open);
  const notice = useIsland(s => !!s.notice);
  const peekUntil = useIsland(s => s.peekUntil);
  const hudUntil = useIsland(s => s.hud?.until ?? 0);
  const peekable = useIsland(s => s.media.has && !s.media.front);
  const [, tick] = useState(0);
  useEffect(() => {                                              // the HUD and the new-song card end on their own
    const ms = Math.min(...[peekUntil, hudUntil].filter(t => t > Date.now())) - Date.now();
    if (!Number.isFinite(ms)) return;
    const id = setTimeout(() => tick(n => n + 1), ms + 20);
    return () => clearTimeout(id);
  }, [peekUntil, hudUntil]);
  const hud = !turn && !open && hudUntil > Date.now();
  const peek = !turn && !open && !hud && !notice && peekable && peekUntil > Date.now();
  const [turnSize, setTurnSize] = useState<[number, number]>([280, 44]);
  const [panelSize, setPanelSize] = useState<[number, number]>([400, 200]);
  const [noticeSize, setNoticeSize] = useState<[number, number]>([380, 90]);
  const onNotice = useCallback((w: number, h: number) => setNoticeSize(p => (p[0] === w && p[1] === h ? p : [w, h])), []);
  const onTurn = useCallback((w: number, h: number) => setTurnSize(p => (p[0] === w && p[1] === h ? p : [w, h])), []);
  const onPanel = useCallback((w: number, h: number) => setPanelSize(p => (p[0] === w && p[1] === h ? p : [w, h])), []);
  const [w, h] = turn ? turnSize : hud ? HUD_SIZE : notice ? noticeSize : peek ? PEEK_SIZE : open ? panelSize : compactSize(view, dots, edge);
  const show = turn ? 'turn' : hud ? 'hud' : notice ? 'notice' : peek ? 'peek' : open ? 'panel' : 'compact';
  return (
    <Capsule width={w} height={h} expanded={open || notice || (turn && h > 48)} hidden={hidden && !open} edge={edge}
             onPointerEnter={pointerEnter} onPointerLeave={pointerLeave}>
      <AnimatePresence initial={false} mode="popLayout">
        {show === 'turn' ? (
          <motion.div key="turn" className="h-full" exit={{ opacity: 0, transition: { duration: 0.1 } }}>
            <Turn onSize={onTurn} />
          </motion.div>
        ) : show === 'hud' ? (
          <motion.div key="hud" className="h-full" exit={{ opacity: 0, transition: { duration: 0.1 } }}>
            <Hud />
          </motion.div>
        ) : show === 'notice' ? (
          <motion.div key="notice" className="h-full" exit={{ opacity: 0, transition: { duration: 0.1 } }}>
            <Notice onSize={onNotice} />
          </motion.div>
        ) : show === 'peek' ? (
          <motion.div key="peek" className="h-full" exit={{ opacity: 0, transition: { duration: 0.1 } }}>
            <TrackPeek />
          </motion.div>
        ) : show === 'panel' ? (
          <motion.div key="panel" className="h-full" exit={{ opacity: 0, transition: { duration: 0.1 } }}>
            <Panel onSize={onPanel} />
          </motion.div>
        ) : (
          <motion.div key="compact" className="h-full" exit={{ opacity: 0, transition: { duration: 0.08 } }}>
            <CompactIsland />
          </motion.div>
        )}
      </AnimatePresence>
      {!edge && <Celebrate />}
    </Capsule>
  );
}

/** A page of the building blocks, for reviewing the design system. */
function Gallery() {
  const looks: Look[] = ['neutral', 'listening', 'thinking', 'talking', 'happy', 'sad', 'question', 'calm'];
  const [playing, setPlaying] = useState(true);
  return (
    <div dir="rtl" className="h-full overflow-auto bg-[#1b1b1e] p-8 font-ui text-ink">
      <h1 className="mb-6 font-display text-2xl font-semibold">نظام تصميم يوبي</h1>
      <section className="mb-8">
        <h2 className="mb-3 text-sm text-ink-2">الكبسولة</h2>
        <div className="flex items-start gap-6">
          <div className="relative h-14 w-40"><Capsule width={96} height={28} /></div>
          <div className="relative h-14 w-60"><Capsule width={196} height={34}><div className="flex h-full items-center justify-between px-3"><div className="size-6 rounded-[8px] bg-gradient-to-br from-accent to-gold" /><Meter value={0.4} className="w-10" /></div></Capsule></div>
          <div className="relative h-40 w-96"><Capsule width={360} height={120} expanded>
            <div className="flex h-full items-center gap-4 px-6"><YobiFace look="talking" /><p className="font-display text-[17px] font-semibold">تمام، فتحت ديسكورد</p></div>
          </Capsule></div>
        </div>
      </section>
      <section className="mb-8">
        <h2 className="mb-3 text-sm text-ink-2">وش يوبي</h2>
        <div className="flex flex-wrap gap-3">
          {looks.map(l => (
            <div key={l} className="flex w-24 flex-col items-center gap-2 rounded-card bg-island py-4">
              <YobiFace look={l} level={0.6} /><span className="text-xs text-ink-2">{l}</span>
            </div>
          ))}
        </div>
      </section>
      <section className="mb-8">
        <h2 className="mb-3 text-sm text-ink-2">الأزرار</h2>
        <div className="flex items-center gap-3 rounded-card bg-island p-4">
          <IconButton icon={Mic} label="كلّم يوبي" text="اتكلم" />
          <IconButton icon={PenLine} label="اكتب ليوبي" text="اكتب" />
          <span dir="ltr" className="flex items-center gap-2">
            <IconButton icon={SkipBack} label="اللي فاتت" />
            <IconButton icon={playing ? Pause : Play} label={playing ? 'وقّف' : 'شغّل'} size="lg" tone="solid" onClick={() => setPlaying(p => !p)} />
            <IconButton icon={SkipForward} label="الجاية" />
          </span>
          <button type="button" className="h-10 rounded-pill bg-gold px-5 text-[13px] font-semibold text-island">Euro Truck Simulator 2</button>
        </div>
      </section>
      <section>
        <h2 className="mb-3 text-sm text-ink-2">المقاييس</h2>
        <div className="grid w-80 gap-3 rounded-card bg-island p-5">
          <Meter value={0.12} heat /><Meter value={0.76} heat /><Meter value={0.94} heat /><Meter value={0.38} tone="gold" />
        </div>
      </section>
    </div>
  );
}
