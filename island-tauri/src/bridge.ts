// The only place that talks to the window process. Inside Tauri it uses the Rust commands;
// in a plain browser (the design preview, the visual tests) it falls back to a mock that
// anything can drive through window.__yobi.
import type { InMsg, OutMsg } from './types';

export interface IslandRect { x: number; y: number; w: number; h: number }

interface Bridge {
  onMessage(fn: (m: InMsg) => void): void;
  send(m: OutMsg): void;
  interactive(on: boolean): void;
  rect(r: IslandRect): void;
  focus(on: boolean): void;
  /** a file's or an app's icon (a PNG data URL), "" when there's none */
  fileIcon(path: string): Promise<string>;
  /** start dragging a file out of the island into another app */
  dragOut(path: string): void;
  /** files dragged over the island: enter (with their paths), drop, leave */
  onFileDrop(fn: (e: { type: 'enter' | 'drop' | 'leave'; paths: string[] }) => void): void;
  /** the settings window (one at a time) */
  openSettings(): void;
  /** put the island on a screen: "primary", "cursor", or a screen's number */
  display(pref: string): void;
  /** the screens, for the settings */
  displays(): Promise<Screen[]>;
}
export interface Screen { id: string; n: number; w: number; h: number; scale: number; primary: boolean }

const inTauri = '__TAURI_INTERNALS__' in window;

function tauriBridge(): Bridge {
  const core = import('@tauri-apps/api/core');
  const event = import('@tauri-apps/api/event');
  const call = (cmd: string, args?: Record<string, unknown>) => core.then(c => c.invoke(cmd, args)).catch(() => {});
  return {
    onMessage(fn) {
      // listen first, then tell Rust to start delivering, so nothing is lost
      event.then(e => e.listen<InMsg>('yobi', ev => fn(ev.payload))).then(() => call('ready'));
    },
    send: m => void call('send', { msg: m }),
    interactive: on => void call('interactive', { on }),
    rect: r => void call('rect', { r }),
    focus: on => void call('focus', { on }),
    fileIcon: path => core.then(c => c.invoke<string>('file_icon', { path })).catch(() => ''),
    dragOut: path => void call('drag_out', { path }),
    openSettings: () => void call('open_settings'),
    display: pref => void call('display', { pref }),
    displays: () => core.then(c => c.invoke<Screen[]>('displays')).catch(() => []),
    onFileDrop(fn) {
      void import('@tauri-apps/api/webview').then(w => w.getCurrentWebview().onDragDropEvent(ev => {
        const p = ev.payload;
        if (p.type === 'enter') fn({ type: 'enter', paths: p.paths });
        else if (p.type === 'drop') fn({ type: 'drop', paths: p.paths });
        else if (p.type === 'leave') fn({ type: 'leave', paths: [] });
      }));
    },
  };
}

export interface MockBridge extends Bridge {
  deliver(m: InMsg): void; sent: OutMsg[]; lastRect: IslandRect | null;
  /** tests: what was dragged out, and a way to drop files on the island */
  dragged: string[]; drop(type: 'enter' | 'drop' | 'leave', paths?: string[]): void;
  settingsOpened: number; screen: string;
}

function mockBridge(): MockBridge {
  const listeners: ((m: InMsg) => void)[] = [];
  const drops: ((e: { type: 'enter' | 'drop' | 'leave'; paths: string[] }) => void)[] = [];
  const b: MockBridge = {
    sent: [],
    lastRect: null,
    dragged: [],
    drop: (type, paths = []) => drops.forEach(fn => fn({ type, paths })),
    fileIcon: async () => '',
    dragOut: path => void b.dragged.push(path),
    settingsOpened: 0,
    screen: '',
    openSettings: () => void b.settingsOpened++,
    display: pref => void (b.screen = pref),
    displays: async () => [{ id: '1', n: 1, w: 1920, h: 1080, scale: 1.25, primary: true }, { id: '2', n: 2, w: 2560, h: 1440, scale: 1, primary: false }],
    onFileDrop: fn => void drops.push(fn),
    onMessage: fn => void listeners.push(fn),
    deliver: m => listeners.forEach(fn => fn(m)),
    send: m => void b.sent.push(m),
    interactive: () => {},
    rect: r => void (b.lastRect = r),
    focus: () => {},
  };
  (window as unknown as { __yobi: MockBridge }).__yobi = b;
  return b;
}

export const bridge: Bridge = inTauri ? tauriBridge() : mockBridge();
