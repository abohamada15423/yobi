// The open panel's rules (interface 3), outside React: hover and the keyboard shortcut open it,
// leaving or Esc closes it, and writing to Yobi borrows the keyboard and gives it back after.
import { bridge } from './bridge';
import { isHovering, setHovering } from './turn';
import { holdNotice } from './notices';
import { PANEL_CLOSED, useIsland, type Page } from './store';

const get = () => useIsland.getState();
/** this page is the settings window, not the island: no shortcut, no file drops */
export const IN_SETTINGS = '__YOBI_SETTINGS__' in window || new URLSearchParams(location.search).has('settings');
const PAGES: Page[] = ['home', 'apps', 'shelf', 'clips'];
let closeTimer: ReturnType<typeof setTimeout> | undefined;
let borrowed = false;                                         // a box in a page took the keyboard

/** a text box in a page (the radio's search) takes the keyboard until the panel closes */
export function borrowKeyboard() { if (!borrowed) { borrowed = true; bridge.focus(true); } }

export function openPanel() {
  clearTimeout(closeTimer);
  const s = get();
  if (s.state !== 'idle' || s.panel.open) return;            // a Yobi turn keeps the island
  useIsland.setState({ peekUntil: 0, hud: null });
  s.setPanel({ ...PANEL_CLOSED, open: true });
}

/** force: also when the menu, the writing box or a keyboard-opened panel is up */
export function closePanel(force = false) {
  const p = get().panel;
  if (!p.open) return;
  if (!force && (p.menu || p.chat || p.kb)) return;
  if (p.kb || p.chat || borrowed) bridge.focus(false);
  borrowed = false;
  if (!isHovering()) bridge.interactive(false);
  get().setPanel(PANEL_CLOSED);
}

export function pointerEnter() {
  clearTimeout(closeTimer);
  setHovering(true);
  bridge.interactive(true);
  holdNotice(true);                                          // a notice waits while you read it
  openPanel();
}
export function pointerLeave() {
  setHovering(false);
  holdNotice(false);
  if (!get().panel.chat && !get().panel.kb) bridge.interactive(false);
  clearTimeout(closeTimer);
  closeTimer = setTimeout(() => closePanel(false), 450);
}

/** a page button: pressing the open page again goes back home */
export function showPage(page: Page) {
  const p = get().panel;
  const next = p.page === page ? 'home' : page;
  get().setPanel({ page: next, menu: false });
  if (next === 'apps') bridge.send({ t: 'apps_get' });
  if (next === 'radio' && !get().radio.stations.length) bridge.send({ t: 'radio_get' });
}

export function toggleMenu() {
  const p = get().panel;
  if (!p.menu) bridge.send({ t: 'menu_open' });               // Python answers with the switches' state
  get().setPanel({ menu: !p.menu });
}

export function openChat() {
  get().setPanel({ menu: false, chat: true });
  bridge.interactive(true);
  bridge.focus(true);
}
export function closeChat(alsoPanel: boolean) {
  if (!get().panel.chat) return;
  get().setPanel({ chat: false });
  bridge.focus(false);
  if (alsoPanel) closePanel(true);
}
export function sendChat(text: string) {
  text = text.trim();
  if (!text) return;
  closeChat(true);
  bridge.send({ t: 'chat', text });
  get().apply({ t: 'state', state: 'thinking', text });         // Yobi's turn starts right away
}

/** a voice command opened a page: it stays until you've had a look (10 s), longer while the pointer is on it */
export function voiceOpen(page: Page | 'settings') {
  if (page === 'settings') { bridge.openSettings(); return; }
  const s = get();
  if (s.state !== 'idle') return;
  clearTimeout(closeTimer);
  useIsland.setState({ peekUntil: 0, hud: null });
  s.setPanel({ ...PANEL_CLOSED, open: true, page });
  bridge.interactive(true);
  if (page === 'apps') bridge.send({ t: 'apps_get' });
  if (page === 'radio' && !s.radio.stations.length) bridge.send({ t: 'radio_get' });
  closeTimer = setTimeout(() => { if (!isHovering()) closePanel(true); }, 10_000);
}

/** the shortcut (or Python's kb_open) */
function keyboardOpen() {
  const s = get();
  if (s.state !== 'idle') return;                              // a question: Turn puts the keyboard on its buttons
  clearTimeout(closeTimer);
  useIsland.setState({ peekUntil: 0, hud: null });
  s.setPanel({ ...PANEL_CLOSED, open: true, kb: true });
  setTimeout(() => document.querySelector<HTMLButtonElement>('[data-dock] button')?.focus(), 40);
}

useIsland.subscribe((s, p) => {
  if (s.kbOpenAt !== p.kbOpenAt) keyboardOpen();
  if (s.state !== 'idle' && p.state === 'idle') {             // a Yobi turn takes the island
    if (s.peekUntil || s.hud) useIsland.setState({ peekUntil: 0, hud: null });
    if (s.panel.open) {
      if (s.panel.chat || s.panel.kb) bridge.focus(false);
      s.setPanel(PANEL_CLOSED);
    }
  }
  if (s.panel.open !== p.panel.open) bridge.send({ t: 'panel', open: s.panel.open });
});

document.addEventListener('keydown', e => {
  const p = get().panel;
  if (!p.open) return;
  const typing = (e.target as HTMLElement).matches?.('input, textarea, [role=slider]');   // a slider uses the arrows itself
  if (e.key === 'Escape') {
    e.preventDefault();
    if (p.menu) get().setPanel({ menu: false });
    else if (p.chat) closeChat(true);
    else closePanel(true);
  } else if (!typing && !p.menu && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
    e.preventDefault();
    const i = Math.max(0, PAGES.indexOf(p.page));
    showPage(PAGES[(i + (e.key === 'ArrowLeft' ? 1 : PAGES.length - 1)) % PAGES.length]);   // RTL: left is forward
  }
});
window.addEventListener('blur', () => { if (get().panel.kb) closePanel(true); });   // clicked somewhere else

// the keyboard shortcut from the settings (Ctrl+Alt+I unless changed); Tauri only
if ('__TAURI_INTERNALS__' in window && !IN_SETTINGS) {
  let current = '';
  const apply = async (key: string) => {
    if (key === current) return;
    const gs = await import('@tauri-apps/plugin-global-shortcut');
    if (current) await gs.unregister(current).catch(() => {});
    current = '';
    if (!key) return;
    try {
      await gs.register(key, ev => {
        if (ev.state !== 'Pressed') return;
        bridge.interactive(true);
        bridge.focus(true);
        get().apply({ t: 'kb_open' });
      });
      current = key;
    } catch {
      bridge.send({ t: 'log', text: `shortcut ${key} is taken by another app` });
    }
  };
  const key = (s = get()) => (typeof s.prefs.shortcut === 'string' ? s.prefs.shortcut : 'Ctrl+Alt+I');
  void apply(key());
  useIsland.subscribe((s, p) => { if (s.prefs.shortcut !== p.prefs.shortcut) void apply(key(s)); });
}

// files dragged onto the island go on the shelf (only their paths are kept, by Python)
if (!IN_SETTINGS) bridge.onFileDrop(e => {
  const s = get();
  if (e.type === 'enter') {
    if (s.state !== 'idle' || !e.paths.length) return;
    clearTimeout(closeTimer);
    setHovering(true);
    bridge.interactive(true);
    useIsland.setState({ dropping: true, peekUntil: 0, hud: null });
    s.setPanel({ ...(s.panel.open ? s.panel : PANEL_CLOSED), open: true, page: 'shelf', menu: false });
  } else if (e.type === 'drop') {
    useIsland.setState({ dropping: false });
    if (e.paths.length) bridge.send({ t: 'shelf_add', paths: e.paths });
  } else {
    useIsland.setState({ dropping: false });
  }
});

// the screen the island sits on follows the settings
useIsland.subscribe((s, p) => {
  if (!IN_SETTINGS && s.prefs.display !== p.prefs.display && typeof s.prefs.display === 'string') bridge.display(s.prefs.display);
  if (!IN_SETTINGS && s.prefs.position !== p.prefs.position && typeof s.prefs.position === 'string') bridge.edge(s.prefs.position);
});
