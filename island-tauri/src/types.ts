// The contract with Python (electron_island.py and island_*.py), unchanged from the Electron island.
// One JSON object per message; `t` says what it is.

export type YobiState =
  | 'idle' | 'listening' | 'recording' | 'thinking' | 'executing' | 'account' | 'speaking'
  | 'success' | 'error' | 'info' | 'suggesting';

export interface MediaInfo {
  has: boolean; playing?: boolean; title?: string; artist?: string; app?: string;
  front?: boolean; pos?: number; dur?: number; seek?: boolean; art?: string | null;
}
export interface Stats { cpu: number; ram: number; ram_used: number; ram_total: number; battery: { percent: number; plugged: boolean } | null }
export interface PrayerTimes { fajr: number; sunrise: number; dhuhr: number; asr: number; maghrib: number; isha: number; next_fajr: number }
export interface FocusInfo { phase: 'focus' | 'break' | 'long' | null; round?: number; total?: number; ends_at?: number | null; paused_left?: number | null; focus_min?: number }
export interface Weather { temp: number; code: number; is_day: boolean; hi: number; lo: number; city: string }
export interface Download { id: string; name: string; bytes: number; speed: number }
export interface ShelfItem { i: number; name: string; path: string; dir: boolean }
export interface PinnedApp { name: string; icon: string; running: boolean }
export interface Station { name: string; url: string }
export interface Meeting { id: string; title: string; start: number; end: number; has_link: boolean }

export type HudMsg =
  | { t: 'hud'; kind: 'volume'; value: number; muted: boolean }
  | { t: 'hud'; kind: 'brightness'; value: number }
  | { t: 'hud'; kind: 'caps'; on: boolean }
  | { t: 'hud'; kind: 'kbd'; name: string; badge: string }
  | { t: 'hud'; kind: 'battery'; value: number; plugged: boolean; low: boolean }
  | { t: 'hud'; kind: 'net'; online: boolean; gone_s: number };

export type NoticeMsg = { t: 'notice'; kind: string; [k: string]: unknown };

/** Python → island */
export type InMsg =
  | { t: 'state'; state: YobiState; text?: string }
  | { t: 'say'; text: string; state?: YobiState; chime?: boolean }
  | { t: 'ask'; id: string; text: string; options: [string, string][]; timeout: number; chime?: boolean }
  | { t: 'listening_soft'; text?: string }
  | { t: 'end_turn' }
  | { t: 'level'; v: number }
  | { t: 'progress'; v: number }
  | { t: 'kb_open' }
  | HudMsg
  | NoticeMsg
  | ({ t: 'media' } & MediaInfo)
  | { t: 'music_level'; v: number }
  | ({ t: 'stats' } & Stats)
  | { t: 'prayer'; city: string; times: PrayerTimes }
  | ({ t: 'focus' } & FocusInfo)
  | { t: 'water'; count: number; goal: number }
  | { t: 'meetings'; events: Meeting[] }
  | ({ t: 'weather' } & Weather)
  | { t: 'downloads'; items: Download[] }
  | { t: 'shelf'; items: ShelfItem[] }
  | { t: 'clips'; enabled: boolean; items: string[] }
  | { t: 'apps'; pinned: PinnedApp[]; catalog?: string[] }
  | { t: 'radio_stations'; items: Station[]; error?: boolean }
  | { t: 'privacy'; mic: string[]; cam: string[] }
  | { t: 'fullscreen'; on: boolean; max?: boolean }
  | { t: 'battery_saver'; on: boolean }
  | { t: 'island_settings'; values: Record<string, unknown> }
  | { t: 'menu_state'; listen: boolean | null; voice: boolean | null; companion: boolean | null }
  | { t: 'settings'; [k: string]: unknown }
  | { t: 'settings_saved' }
  /** a voice command opened one of the island's pages (island_voice.py) */
  | { t: 'open'; page: 'prayer' | 'shelf' | 'clips' | 'apps' | 'history' | 'settings' };

/** island → Python (the same names the Electron island sends) */
export type OutMsg =
  | { t: 'answer'; id: string; value: string }
  | { t: 'view'; state: YobiState; reply: boolean }
  | { t: 'quick'; id: string }
  | { t: 'chat'; text: string }
  | { t: 'menu'; id: string }
  | { t: 'menu_open' }
  | { t: 'panel'; open: boolean }
  | { t: 'media'; cmd: 'toggle' | 'next' | 'prev' | 'seek'; pos?: number }
  | { t: 'focus'; cmd: 'start' | 'pause' | 'resume' | 'stop' | 'skip' }
  | { t: 'water'; cmd: 'add' }
  | { t: 'meeting_join'; id: string }
  | { t: 'notice_action'; action: string }
  | { t: 'notice_dropped'; kind: string }
  | { t: 'dl_open' | 'dl_folder'; id: string }
  | { t: 'shelf_add'; paths: string[] }
  | { t: 'shelf_open' | 'shelf_folder' | 'shelf_remove'; i: number }
  | { t: 'shelf_clear' }
  | { t: 'clip_copy'; i: number }
  | { t: 'clip_clear' }
  | { t: 'apps_get' | 'radio_get' }
  | { t: 'app_open' | 'app_pin' | 'app_unpin'; name: string }
  | { t: 'smart_action'; action: string; value: string }
  | { t: 'settings_get' }
  | { t: 'settings_set'; section: 'island' | 'daily'; values: Record<string, unknown> }
  | { t: 'preview'; what: string }
  | { t: 'log'; text: string };
