// Everything Python has told the island, in one Zustand store. Components read slices of it;
// only `apply` writes, one message at a time. Decisions (what to show when) live in selectors
// and in the interfaces, built one by one.
import { create } from 'zustand';
import type { ShownNotice } from './notices';
import type {
  Download, FocusInfo, HudMsg, InMsg, MediaInfo, Meeting, PinnedApp, PrayerTimes,
  ShelfItem, Station, Stats, Weather, YobiState,
} from './types';

export interface IslandStore {
  // Yobi's turn
  state: YobiState;
  status: string;
  words: string;
  question: { id: string; text: string; options: [string, string][]; timeout: number } | null;
  level: number;
  progress: number;
  /** a reply is still being typed out */
  typing: boolean;
  /** a reply's reading time is running (with `typing`: Yobi's reply is still on screen) */
  replyHeld: boolean;
  /** a new reply or state (not a longer version of the same one): restarts the typing */
  seq: number;
  shakeAt: number;
  chime: { at: number; f1: number; f2?: number } | null;
  /** what Yobi said and asked, newest first (the history page reads it) */
  history: { at: number; kind: YobiState | 'notice'; text: string; label?: string }[];
  // passing notices
  /** a passing reading (volume, brightness, Caps Lock…), shown until `until` */
  hud: (HudMsg & { at: number; until: number }) | null;
  /** the notice on screen (interface 6); notices.ts decides and times them */
  notice: ShownNotice | null;
  // the machine and your day
  media: MediaInfo;
  /** when `media.pos` was true: the position runs on from here while playing */
  mediaAt: number;
  /** a new song while you're not looking: the short card shows until then */
  peekUntil: number;
  mediaKey: string | null;
  mediaSeen: boolean;
  musicLevel: number;
  stats: Stats | null;
  prayer: { city: string; times: PrayerTimes } | null;
  focus: FocusInfo;
  water: { count: number; goal: number } | null;
  meetings: Meeting[];
  weather: Weather | null;
  downloads: Download[];
  shelf: ShelfItem[];
  clips: { enabled: boolean; items: string[] };
  apps: { pinned: PinnedApp[]; catalog: string[] | null };
  /** the Qur'an radio, played by the island itself (radio.ts) */
  radio: { stations: Station[]; error: boolean; url: string; name: string; playing: boolean; msg: string };
  privacy: { mic: string[]; cam: string[] };
  fullscreen: { on: boolean; max: boolean };
  batterySaver: boolean;
  prefs: Record<string, unknown>;
  menu: { listen: boolean | null; voice: boolean | null; companion: boolean | null };
  kbOpenAt: number;
  /** the open panel (interface 3): which page, and whether the menu or the writing box is up */
  panel: PanelState;
  /** files are being dragged over the island (they'll go on the shelf) */
  dropping: boolean;
  /** the internet dropped (from the `net` notice) */
  offline: boolean;
  /** when a goal was last reached (a focus round, a download, the day's water); 0 = never */
  celebrateAt: number;
  apply(m: InMsg): void;
  doneTyping(): void;
  /** the turn is over: back to the compact island */
  hide(): void;
  setPanel(p: Partial<PanelState>): void;
}
export type Page = 'home' | 'prayer' | 'radio' | 'apps' | 'shelf' | 'clips' | 'history' | 'settings';
export interface PanelState { open: boolean; page: Page; menu: boolean; chat: boolean; kb: boolean }
export const PANEL_CLOSED: PanelState = { open: false, page: 'home', menu: false, chat: false, kb: false };

export const useIsland = create<IslandStore>((set) => ({
  state: 'idle', status: '', words: '', question: null, level: 0, progress: -1,
  typing: false, replyHeld: false, seq: 0, shakeAt: 0, chime: null, history: [],
  hud: null, notice: null,
  media: { has: false }, mediaAt: 0, peekUntil: 0, mediaKey: null, mediaSeen: false, musicLevel: 0, stats: null, prayer: null, focus: { phase: null },
  water: null, meetings: [], weather: null, downloads: [], shelf: [],
  clips: { enabled: true, items: [] }, apps: { pinned: [], catalog: null },
  radio: { stations: [], error: false, url: '', name: '', playing: false, msg: '' }, privacy: { mic: [], cam: [] },
  fullscreen: { on: false, max: false }, batterySaver: false, prefs: {},
  menu: { listen: null, voice: null, companion: null }, kbOpenAt: 0, celebrateAt: 0,
  panel: PANEL_CLOSED, offline: false, dropping: false,

  apply: (m) => set((s): Partial<IslandStore> => {
    const now = Date.now();
    switch (m.t) {
      case 'state': {
        if (m.state === 'idle') return IDLE_TURN;
        const reply = isReply(m.state), text = m.text ?? '';
        return {
          state: m.state, status: reply ? '' : text, words: reply ? text : '', question: null, typing: false, seq: s.seq + 1,
          ...(m.state !== 'executing' ? { progress: -1 } : {}),
          ...(m.state === 'error' && s.state !== 'error' ? { shakeAt: now } : {}),
          ...(reply && text && text !== '▍' ? { history: remember(s.history, m.state, text) } : {}),
        };
      }
      case 'say': {
        const st: YobiState = m.state && isReply(m.state) ? m.state : 'info';
        if (!m.text) return {};
        // streaming: the brain sends a longer version of the same reply; keep typing on
        if (s.words && m.text.startsWith(s.words) && s.state === st && (s.typing || s.replyHeld)) {
          const h = s.history[0] && m.text.startsWith(s.history[0].text) ? [{ ...s.history[0], text: m.text }, ...s.history.slice(1)] : s.history;
          return { words: m.text, typing: true, history: h };
        }
        return {
          state: st, words: m.text, status: '', question: null, typing: true, seq: s.seq + 1, progress: -1,
          history: remember(s.history, st, m.text),
          ...(m.chime !== false ? { chime: { at: now, f1: st === 'error' ? 330 : 520 } } : {}),
          ...(st === 'error' ? { shakeAt: now } : {}),
        };
      }
      case 'ask': return {
        state: 'suggesting', words: m.text, status: '', typing: false, seq: s.seq + 1, progress: -1,
        question: { id: m.id, text: m.text, options: m.options, timeout: m.timeout },
        history: remember(s.history, 'suggesting', m.text),
        ...(m.chime !== false ? { chime: { at: now, f1: 660, f2: 880 } } : {}),
      };
      case 'listening_soft': return replyVisible(s) ? {} : { state: 'listening', status: m.text ?? '', words: '', question: null, seq: s.seq + 1 };
      case 'end_turn': return !replyVisible(s) && isActive(s.state) ? IDLE_TURN : {};
      case 'level': return { level: clamp01(m.v) };
      case 'progress': return { progress: s.state === 'executing' ? Number(m.v) : -1 };
      case 'kb_open': return { kbOpenAt: now };
      case 'hud': {
        const net = m.kind === 'net' ? { offline: !m.online } : {};
        if (s.state !== 'idle' || s.panel.open) return net;   // never over a Yobi turn or the open panel
        const long = m.kind === 'battery' && m.low;           // a low battery stays longer
        return { ...net, hud: { ...m, at: now, until: now + (long ? 5000 : HUD_MS) } };
      }
      case 'media': {
        const { t: _t, ...info } = m;
        const media: MediaInfo = info.has ? { ...s.media, ...info } : { has: false };
        const key = media.has ? `${media.app}|${media.title}|${media.artist}` : null;
        // a new song while you're not looking at the player (not the first one we hear about)
        const peek = s.prefs.track_peek !== false && s.mediaSeen && key && key !== s.mediaKey
          && media.playing && !media.front && s.state === 'idle' && !s.panel.open;
        return { media, mediaAt: now, mediaKey: key, mediaSeen: true, ...(peek ? { peekUntil: now + PEEK_MS } : {}) };
      }
      case 'music_level': return { musicLevel: clamp01(m.v) };
      case 'stats': { const { t: _t, ...st } = m; return { stats: st }; }
      case 'prayer': return { prayer: { city: m.city, times: m.times } };
      case 'focus': { const { t: _t, ...f } = m; return { focus: f }; }
      case 'water': return {
        water: { count: m.count, goal: m.goal },
        ...(s.prefs.celebrate && s.water && s.water.count < m.goal && m.count >= m.goal ? { celebrateAt: now } : {}),
      };
      case 'meetings': return { meetings: m.events };
      case 'weather': { const { t: _t, ...w } = m; return { weather: w }; }
      case 'downloads': return { downloads: m.items };
      case 'shelf': return { shelf: m.items };
      case 'clips': return { clips: { enabled: m.enabled, items: m.items } };
      case 'apps': return { apps: { pinned: m.pinned, catalog: m.catalog ?? s.apps.catalog } };
      case 'radio_stations': {
        const name = s.radio.name || m.items.find(x => x.url === s.radio.url)?.name || '';
        return { radio: { ...s.radio, stations: m.items, error: !!m.error, name } };
      }
      case 'privacy': return { privacy: { mic: m.mic, cam: m.cam } };
      case 'fullscreen': return { fullscreen: { on: m.on, max: !!m.max } };
      case 'battery_saver': return { batterySaver: m.on };
      case 'island_settings': return { prefs: { ...s.prefs, ...m.values } };
      case 'menu_state': return { menu: { listen: m.listen, voice: m.voice, companion: m.companion } };
      default: return {};
    }
  }),
  doneTyping: () => set({ typing: false }),
  hide: () => set(IDLE_TURN),
  setPanel: (p) => set(s => ({ panel: { ...s.panel, ...p } })),
}));

/** What the compact island shows, by the same rules as the Electron island: focus, then music, then a download. */
export type Compact = 'thin' | 'idle' | 'clock' | 'info' | 'focus' | 'music' | 'download';
export const musicLive = (s: IslandStore) => s.prefs.music_tab !== false && s.media.has && !!s.media.playing && !s.media.front;
export const hasDots = (s: IslandStore) => s.privacy.mic.length > 0 || s.privacy.cam.length > 0;
export function compactView(s: IslandStore): Compact {
  if (s.focus.phase) return 'focus';
  if (musicLive(s)) return 'music';
  if (s.downloads.length) return 'download';
  if (s.fullscreen.max && !hasDots(s)) return 'thin';      // a maximized window: a sliver, out of the way
  return s.prefs.idle_clock === false ? 'idle' : s.prefs.idle_info === false ? 'clock' : 'info';
}
/** a fullscreen game or video hides the island; only Yobi's own turns, the adhan and a meeting get through */
export const fsHidden = (s: IslandStore) => s.fullscreen.on && s.state === 'idle'
  && !(s.notice && (s.notice.msg.kind === 'adhan' || s.notice.msg.kind === 'meeting'));
/** the user's own "less motion" switch and the battery saver count, besides Windows' setting */
export const stillPref = (s: IslandStore) => !!s.prefs.reduce_motion || s.batterySaver;

export const PEEK_MS = 3600, HUD_MS = 1500;
/** where the song is now (it runs on between Python's updates) */
export function mediaPos(s: IslandStore) {
  let p = s.media.pos || 0;
  if (s.media.playing) p += (Date.now() - s.mediaAt) / 1000;
  return s.media.dur ? Math.min(p, s.media.dur) : p;
}

const IDLE_TURN: Partial<IslandStore> = { state: 'idle', status: '', words: '', question: null, progress: -1, typing: false, replyHeld: false };
/** Yobi's reply is still on screen (being typed, or within its reading time) */
export const replyVisible = (s: IslandStore) => s.typing || (isReply(s.state) && s.replyHeld);
export function remember(h: IslandStore['history'], kind: YobiState | 'notice', text: string, label?: string) {
  text = text.trim();
  return text ? [{ at: Date.now(), kind, text, label }, ...h].slice(0, 40) : h;
}

const REPLY = new Set<YobiState>(['success', 'error', 'info', 'suggesting']);
const ACTIVE = new Set<YobiState>(['listening', 'recording', 'thinking', 'executing', 'account', 'speaking']);
export const isReply = (s: YobiState) => REPLY.has(s);
export const isActive = (s: YobiState) => ACTIVE.has(s);
const clamp01 = (v: number) => Math.max(0, Math.min(1, Number(v) || 0));

// the off-screen tests (outside Tauri) read the store directly
if (!('__TAURI_INTERNALS__' in window)) (window as unknown as { __island: typeof useIsland }).__island = useIsland;
