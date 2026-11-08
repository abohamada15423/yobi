// Yobi island window. Python (electron_island.py) owns all logic; this process only
// shows what Python sends and reports clicks back, over a local socket.
const { app, BrowserWindow, ipcMain, screen, globalShortcut } = require('electron');
const fs = require('fs');
const net = require('net');
const path = require('path');

const PORT = Number(process.env.YOBI_ISLAND_PORT);
const TOKEN = process.env.YOBI_ISLAND_TOKEN || '';
const W = 580, H = 360;

if (!PORT || !TOKEN) { console.error('Start the island from agent.py.'); app.exit(2); }
if (!app.requestSingleInstanceLock()) app.exit(0);

let win = null, prefs = null, sock = null, buf = '';
let ignoring = true, tabRect = null, displayPref = 'primary', placedOn = null;
const pending = [];

function toPython(msg) {
  if (sock && !sock.destroyed) sock.write(JSON.stringify(msg) + '\n');
}

function toRenderers(msg) {
  if (win && !win.isDestroyed() && !win.webContents.isLoading()) win.webContents.send('yobi', msg);
  else pending.push(msg);
  if (prefs && !prefs.isDestroyed()) prefs.webContents.send('yobi', msg);
}

function connect() {
  sock = net.createConnection({ host: '127.0.0.1', port: PORT }, () => toPython({ t: 'hello', token: TOKEN }));
  sock.setEncoding('utf8');
  sock.on('data', chunk => {
    buf += chunk;
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i); buf = buf.slice(i + 1);
      if (!line.trim()) continue;
      let msg; try { msg = JSON.parse(line); } catch { continue; }
      if (msg.t === 'quit') { app.quit(); return; }
      if (msg.t === 'island_settings' && msg.values) applySettings(msg.values);
      toRenderers(msg);
    }
  });
  // Python is gone: nothing left to show.
  sock.on('close', () => app.quit());
  sock.on('error', () => app.quit());
}

function setIgnore(on) {
  if (!win || ignoring === on) return;
  ignoring = on;
  win.setIgnoreMouseEvents(on, { forward: true });
}

// Click-through windows get no mouse or drag events, so watch the cursor directly:
// over the tab (or a file being dragged over it), the window starts taking input.
// The cursor has to rest on the tab a moment first: a quick pass or a click on a browser tab
// underneath goes straight through instead of being caught by the island.
const DWELL_MS = 250;
function watchCursor() {
  let since = 0;
  setInterval(() => {
    if (!win || win.isDestroyed() || !ignoring || !tabRect) { since = 0; return; }
    if (displayPref === 'cursor' && targetDisplay().id !== placedOn) placeWindow();
    const p = screen.getCursorScreenPoint(), b = win.getBounds();
    const x = p.x - b.x, y = p.y - b.y, pad = 4;
    const inside = x >= tabRect.x - pad && x <= tabRect.x + tabRect.w + pad && y >= -2 && y <= tabRect.y + tabRect.h + pad;
    if (!inside) { since = 0; return; }
    since = since || Date.now();
    if (Date.now() - since >= DWELL_MS) { since = 0; setIgnore(false); }
  }, 50);
}

// the keyboard shortcut that opens the panel (Settings: island.shortcut, empty = off)
let shortcut = null;
function targetDisplay() {
  const all = screen.getAllDisplays();
  if (displayPref === 'cursor') return screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  return all.find(d => String(d.id) === displayPref) || screen.getPrimaryDisplay();
}
function placeWindow() {
  if (!win || win.isDestroyed()) return;
  const d = targetDisplay(), a = d.workArea;
  placedOn = d.id;
  win.setBounds({ x: Math.round(a.x + (a.width - W) / 2), y: a.y, width: W, height: H });
}
function applySettings(v) {
  if ('display' in v && v.display !== displayPref) { displayPref = v.display || 'primary'; placeWindow(); }
  if ('shortcut' in v && v.shortcut !== shortcut) {
    if (shortcut) globalShortcut.unregister(shortcut);
    shortcut = null;
    if (v.shortcut) {
      const ok = globalShortcut.register(v.shortcut, () => {
        if (!win || win.isDestroyed()) return;
        setIgnore(false);
        win.focus();
        win.webContents.send('yobi', { t: 'kb_open' });
      });
      if (ok) shortcut = v.shortcut;
      else toPython({ t: 'log', text: `shortcut ${v.shortcut} is taken by another app` });
    }
  }
}

function openSettings() {
  if (prefs && !prefs.isDestroyed()) { prefs.show(); prefs.focus(); return; }
  prefs = new BrowserWindow({
    width: 600, height: 760, minWidth: 480, minHeight: 520, title: 'إعدادات يوبي',
    autoHideMenuBar: true, backgroundColor: '#0E2A52', show: false,
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  prefs.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  prefs.webContents.on('will-navigate', e => e.preventDefault());
  prefs.loadFile(path.join(__dirname, 'settings.html'));
  prefs.once('ready-to-show', () => prefs.show());
  prefs.on('closed', () => { prefs = null; });
}

app.whenReady().then(() => {
  const area = screen.getPrimaryDisplay().workArea;
  win = new BrowserWindow({
    width: W, height: H,
    x: Math.round(area.x + (area.width - W) / 2), y: area.y,
    frame: false, transparent: true, resizable: false, movable: false,
    minimizable: false, maximizable: false, fullscreenable: false,
    alwaysOnTop: true, skipTaskbar: true, hasShadow: false, show: false,
    backgroundColor: '#00000000',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, sandbox: true, nodeIntegration: false },
  });
  win.setAlwaysOnTop(true, 'screen-saver');
  placeWindow();
  for (const ev of ['display-added', 'display-removed', 'display-metrics-changed']) screen.on(ev, placeWindow);
  win.setIgnoreMouseEvents(true, { forward: true });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', e => e.preventDefault());
  win.loadFile(path.join(__dirname, 'index.html'));
  win.webContents.on('did-finish-load', () => {
    while (pending.length) win.webContents.send('yobi', pending.shift());
    win.showInactive();
  });
  connect();
  watchCursor();
});

ipcMain.on('yobi', (_e, msg) => { if (msg && typeof msg.t === 'string') toPython(msg); });
ipcMain.on('interactive', (_e, on) => setIgnore(!on));
ipcMain.on('focus', (_e, on) => { if (!win) return; if (on) win.focus(); else win.blur(); });
ipcMain.on('rect', (_e, r) => {
  if (r && [r.x, r.y, r.w, r.h].every(Number.isFinite)) tabRect = r;
});
ipcMain.on('open-settings', () => openSettings());
// the screens, for the Settings window
ipcMain.handle('displays', () => screen.getAllDisplays().map((d, i) => ({
  id: String(d.id), n: i + 1, w: d.size.width, h: d.size.height, scale: d.scaleFactor,
  primary: d.id === screen.getPrimaryDisplay().id,
})));
ipcMain.handle('file-icon', async (_e, p) => {
  try {
    if (typeof p !== 'string' || !fs.existsSync(p)) return '';
    return (await app.getFileIcon(p, { size: 'normal' })).toDataURL();
  } catch { return ''; }
});
// drag a shelf file out into another app
ipcMain.on('drag-out', async (e, p) => {
  try {
    if (typeof p !== 'string' || !fs.existsSync(p)) return;
    e.sender.startDrag({ file: p, icon: await app.getFileIcon(p, { size: 'normal' }) });
  } catch { /* nothing to drag */ }
});
app.on('will-quit', () => globalShortcut.unregisterAll());
app.on('window-all-closed', () => app.quit());
