// Renders every island view in a window placed off-screen (nothing appears on your screen and
// the mouse is never touched), saves a picture of each to out/, and checks the layout:
//   • no errors from the island's script
//   • the content fits inside the tab, and the tab fits inside the island window
// Run:  python tests/test_island_views.py     (or: electron tests/island_views [--motion])
const { app, BrowserWindow, ipcMain } = require('electron');
const fs = require('fs');
const path = require('path');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');   // keep painting off-screen
const ISLAND = path.resolve(__dirname, '..', '..', 'island');
const OUT = path.join(__dirname, 'out');
const MOTION = process.argv.includes('--motion');
const SCALE = Number((process.argv.find(a => a.startsWith('--scale=')) || '=1').split('=')[1]);   // 1.25, 1.5: display scaling
const sleep = ms => new Promise(r => setTimeout(r, ms));
const errors = [], failures = [];

ipcMain.handle('file-icon', () => '');
ipcMain.handle('displays', () => [{ id: '1', n: 1, w: 1920, h: 1080, scale: 1, primary: true }, { id: '2', n: 2, w: 2560, h: 1440, scale: 1.5, primary: false }]);
ipcMain.on('yobi', (_e, m) => { if (m && m.t === 'log') errors.push(m.text); });
for (const ch of ['interactive', 'focus', 'rect', 'open-settings', 'drag-out']) ipcMain.on(ch, () => {});

app.whenReady().then(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const win = new BrowserWindow({
    x: -4000, y: -4000, width: 580, height: 360, show: false, frame: false, skipTaskbar: true, focusable: false,
    backgroundColor: '#2b2b2b',
    webPreferences: { preload: path.join(ISLAND, 'preload.js'), backgroundThrottling: false, contextIsolation: true, sandbox: true },
  });
  win.showInactive();
  win.webContents.on('console-message', (_e, level, msg) => { if (level >= 3) errors.push(msg); });
  await win.loadFile(path.join(ISLAND, 'index.html'));
  if (SCALE !== 1) win.webContents.enableDeviceEmulation({ screenPosition: 'desktop', deviceScaleFactor: SCALE, screenSize: { width: 1920, height: 1080 }, viewSize: { width: 580, height: 360 }, viewPosition: { x: 0, y: 0 }, scale: 1 });
  // final states only: animations would leave pictures mid-way (the --motion run keeps them)
  if (!MOTION) await win.webContents.insertCSS('*, *::before, *::after { transition: none !important; animation: none !important; }');

  const send = m => win.webContents.send('yobi', m);
  const js = code => win.webContents.executeJavaScript(code);
  const hover = on => js(`document.getElementById('tab').dispatchEvent(new MouseEvent('${on ? 'mouseenter' : 'mouseleave'}'))`);
  async function view(name, wait = 450) {
    await sleep(wait);
    const r = await js(`(() => { const t = document.getElementById('tab'), i = document.getElementById('inner');
      return { mode: t.dataset.mode, tabH: t.offsetHeight, tabW: t.offsetWidth, innerH: i.offsetHeight, innerW: i.offsetWidth,
               winH: innerHeight, winW: innerWidth, open: t.classList.contains('has-content') }; })()`);
    // mid-animation the content is bigger than the growing tab on purpose: check final states only
    if (!MOTION && r.open && r.innerH > r.tabH + 1) failures.push(`${name}: content ${r.innerH}px is taller than the tab ${r.tabH}px`);
    if (!MOTION && r.open && r.innerW > r.tabW + 1) failures.push(`${name}: content ${r.innerW}px is wider than the tab ${r.tabW}px`);
    if (r.tabH > r.winH || r.tabW > r.winW) failures.push(`${name}: the tab doesn't fit the island window`);
    fs.writeFileSync(path.join(OUT, `${name}${SCALE !== 1 ? '@' + SCALE : ''}.png`), (await win.webContents.capturePage()).toPNG());
    console.log('view', name, JSON.stringify(r));
  }

  const now = Date.now(), at = min => now + min * 60000;
  send({ t: 'island_settings', values: { theme: 'faience', weather: true, celebrate: true } });
  send({ t: 'weather', temp: 23, code: 2, is_day: true, hi: 23, lo: 16, city: 'القاهرة' });
  send({ t: 'stats', cpu: 0.12, ram: 0.63, ram_used: 10e9, ram_total: 16e9, battery: null });
  send({ t: 'prayer', city: 'القاهرة', times: { fajr: at(-500), sunrise: at(-410), dhuhr: at(-150), asr: at(30), maghrib: at(170), isha: at(250), next_fajr: at(900) } });
  send({ t: 'focus', phase: null, focus_min: 25 });
  send({ t: 'water', count: 3, goal: 8 });
  send({ t: 'media', has: true, playing: true, title: 'Ya Hayat El Roh', artist: 'Fadel Chaker', app: 'Spotify', front: false, pos: 80, dur: 298, seek: true, art: null });
  await view('idle_music');
  send({ t: 'media', has: false }); await view('idle_clock');

  if (MOTION) {
    // frames of the open animation: the content should arrive after the tab starts growing
    send({ t: 'media', has: false });
    await hover(true);
    for (const ms of [40, 120, 220, 420]) await view(`motion_open_${ms}`, ms === 40 ? 40 : ms - [40, 120, 220, 420][[40, 120, 220, 420].indexOf(ms) - 1]);
    await hover(false);
    for (const ms of [60, 160, 420]) await view(`motion_close_${ms}`, ms === 60 ? 60 : ms - [60, 160, 420][[60, 160, 420].indexOf(ms) - 1]);
    return finish();
  }

  // Yobi's turns: the face and the line as its mouth
  send({ t: 'state', state: 'listening', text: 'سامعك.. اتكلم 🎤' }); await view('turn_listening');
  send({ t: 'state', state: 'thinking', text: 'بفكر...' }); await view('turn_thinking');
  send({ t: 'state', state: 'success', text: 'تمام، فتحت ديسكورد ✅' }); await view('turn_success');
  send({ t: 'state', state: 'error', text: 'مش لاقي البرنامج ده على الجهاز' }); await view('turn_error', 900);
  send({ t: 'ask', id: 'q1', text: 'قصدك Euro Truck Simulator 2 ولا Rocket League؟', options: [['Euro Truck Simulator 2', 'a'], ['Rocket League', 'b'], ['لا، ولا حاجة', 'none']], timeout: 30000 });
  await view('turn_question');
  send({ t: 'state', state: 'idle' });

  // the hover panel and its pages
  await hover(true); await view('panel');
  for (const p of ['apps', 'shelf', 'clips']) {
    await js(`document.querySelector('.dock [data-page=${p}]').click()`);
    if (p === 'apps') send({ t: 'apps', pinned: [{ name: 'Discord', icon: '', running: true }, { name: 'Google Chrome', icon: '', running: false }, { name: 'Visual Studio Code', icon: '', running: false }], catalog: ['Discord', 'Google Chrome', 'Visual Studio Code', 'Steam', 'Telegram'] });
    if (p === 'shelf') send({ t: 'shelf', items: [{ i: 0, name: 'notes.txt', path: 'C:/x/notes.txt', dir: false }, { i: 1, name: 'تقرير الشهر.pdf', path: 'C:/x/r.pdf', dir: false }] });
    if (p === 'clips') send({ t: 'clips', enabled: true, items: ['أول نص', 'https://example.com/a-long-link-that-should-be-cut-with-an-ellipsis'] });
    await view(`page_${p}`);
  }
  await js(`document.querySelector('.dock [data-page=clips]').click()`);
  await js(`document.getElementById('slot-prayer').click()`); await view('page_prayer');
  await js(`document.querySelector('#prayer-page [data-page=radio]').click()`);
  send({ t: 'radio_stations', items: [{ name: 'أحمد العجمي', url: 'https://backup.qurango.net/radio/ahmad_alajmy' }, { name: 'سعد الغامدي', url: 'https://backup.qurango.net/radio/saad_alghamdi' }] });
  await view('page_radio');
  await js(`document.querySelector('#radio-page [data-page=prayer]').click()`);
  await js(`document.getElementById('open-menu').click()`); await view('menu');
  await js(`document.querySelector('[data-menu=history]')?.click()`); await view('page_history');
  await hover(false); await sleep(600);

  // notices
  const notices = [
    ['notice_reminder', { t: 'notice', kind: 'reminder', sub: 'ayah', text: 'ألا بذكر الله تطمئن القلوب', ref: 'الرعد ٢٨', seconds: 20 }],
    ['notice_adhan', { t: 'notice', kind: 'adhan', prayer: 'asr', at: at(0) }],
    ['notice_download', { t: 'notice', kind: 'download_done', id: 'd1', name: 'movie.mkv', size: 734003200 }],
    ['notice_math', { t: 'notice', kind: 'smart', what: 'math', value: '١٢ × (٣ + ٤)', result: '84' }],
    ['notice_brief', { t: 'notice', kind: 'brief', greet: 'صباح الفل ☀️', weather: { temp: 23, code: 2, hi: 23 }, next: { prayer: 'asr', at: at(30) }, meetings: 0, first_meeting: null }],
    ['notice_care', { t: 'notice', kind: 'care', title: 'ريّح عينك', text: 'بص على حاجة بعيدة ٢٠ ثانية، قاعدة ٢٠-٢٠-٢٠.' }],
  ];
  for (const [name, n] of notices) { send(n); await view(name); }
  await js(`document.querySelector('#nt-buttons button')?.click()`);

  // the live tab, notices that pass by, and themes
  send({ t: 'hud', kind: 'volume', value: 64, muted: false }); await view('hud_volume', 200);
  await sleep(1700);
  send({ t: 'focus', phase: 'focus', round: 0, total: 1500, ends_at: Date.now() + 1100000, paused_left: null, focus_min: 25 });
  await view('live_focus');
  send({ t: 'focus', phase: null, focus_min: 25 });
  for (const theme of ['papyrus', 'night', 'nile', 'carnelian']) {
    send({ t: 'island_settings', values: { theme } }); send({ t: 'state', state: 'success', text: 'تمام، اتحفظ ✅' });
    await view(`theme_${theme}`);
  }
  send({ t: 'state', state: 'idle' });

  // the history page now has the replies and notices from above
  send({ t: 'island_settings', values: { theme: 'faience' } });
  await hover(true); await js(`document.getElementById('open-menu').click()`);
  await js(`document.querySelector('[data-menu=history]').click()`); await view('page_history_filled');
  await hover(false);

  // the Settings window, with what Python would send
  const prefs = new BrowserWindow({ x: -4000, y: -4000, width: 760, height: 760, show: false, frame: false, skipTaskbar: true, focusable: false,
    webPreferences: { preload: path.join(ISLAND, 'preload.js'), backgroundThrottling: false, contextIsolation: true, sandbox: true } });
  prefs.showInactive();
  prefs.webContents.on('console-message', (_e, level, msg) => { if (level >= 3) errors.push(`settings: ${msg}`); });
  await prefs.loadFile(path.join(ISLAND, 'settings.html'));
  if (!MOTION) await prefs.webContents.insertCSS('*, *::before, *::after { transition: none !important; animation: none !important; }');
  prefs.webContents.send('yobi', { t: 'settings', island: { theme: 'faience', weather: true, shortcut: 'Ctrl+Alt+I', display: 'primary', battery_saver_at: 20 },
    daily: { city: 'القاهرة', lat: 30.0444, lon: 31.2357, method: 'EGYPT', asr: 'standard', focus_min: 25, break_min: 5, long_break_min: 15, remind_every_min: 20, remind_for_s: 20, quiet_hours: '', calendar_ical: '' },
    themes: ['faience', 'night', 'papyrus', 'nile', 'carnelian'], methods: ['EGYPT'], cities: [{ name: 'القاهرة', lat: 30.0444, lon: 31.2357, method: 'EGYPT' }] });
  await sleep(600);
  const filled = await prefs.webContents.executeJavaScript(`document.getElementById('form').getAttribute('aria-busy') === 'false' && document.getElementById('display').options.length >= 2`);
  if (!filled) failures.push('settings: the form did not fill in');
  fs.writeFileSync(path.join(OUT, `settings${SCALE !== 1 ? '@' + SCALE : ''}.png`), (await prefs.webContents.capturePage()).toPNG());
  console.log('view settings', filled);
  return finish();

  async function finish() {
    await sleep(200);
    for (const e of errors) failures.push(`window error: ${e}`);
    console.log(failures.length ? `FAILED\n${failures.join('\n')}` : 'ALL OK');
    app.exit(failures.length ? 1 : 0);
  }
});
