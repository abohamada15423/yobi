// Renders the new (Tauri) island's web side in a window placed off-screen, with the mock bridge
// standing in for Python, and saves pictures to out/. Nothing appears on screen; the mouse is
// never touched. Checks: no script errors, and every view's capsule fits the island window.
// Run:  electron tests/island_tauri_views     (after `npm run build` in island-tauri)
const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');

app.commandLine.appendSwitch('disable-features', 'CalculateNativeWinOcclusion');
app.commandLine.appendSwitch('force-device-scale-factor', process.env.SCALE || '1.5');   // a high-DPI screen
const DIST = path.resolve(__dirname, '..', '..', 'island-tauri', 'dist', 'index.html');
const OUT = path.join(__dirname, 'out');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const errors = [], failures = [];

async function open(query, width, height) {
  const win = new BrowserWindow({ x: -4000, y: -4000, width, height, show: false, frame: false, skipTaskbar: true,
    focusable: false, backgroundColor: '#2b2b2b', webPreferences: { backgroundThrottling: false } });
  win.showInactive();
  win.webContents.on('console-message', (_e, level, msg) => { if (level >= 3) errors.push(msg); });
  await win.loadFile(DIST, { search: query });
  return win;
}
const shot = async (win, name) => {
  fs.writeFileSync(path.join(OUT, `${name}.png`), (await win.webContents.capturePage()).toPNG());
  console.log('view', name);
};

app.whenReady().then(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  if (!fs.existsSync(DIST)) { console.log('FAILED\nbuild island-tauri first (npm run build)'); return app.exit(1); }

  // the design system
  const gallery = await open('gallery', 900, 760);
  await sleep(1200);
  await shot(gallery, 'gallery');

  // the island: idle, then hovered (the capsule morphs open)
  const island = await open('', 580, 640);
  const js = c => island.webContents.executeJavaScript(c);
  await js(`window.__yobi.deliver({ t: 'island_settings', values: { theme: 'faience' } })`);
  await sleep(700); await shot(island, 'idle');
  await js(`document.querySelector('#root > div').dispatchEvent(new PointerEvent('pointerover', { bubbles: true }))`);
  for (const ms of [60, 160, 320, 900]) { await sleep(ms === 60 ? 60 : 100 + (ms > 320 ? 480 : 60)); await shot(island, `open_${ms}`); }
  const size = await js(`(() => { const r = document.querySelector('#root > div').getBoundingClientRect(); return { w: r.width, h: r.height, ww: innerWidth, wh: innerHeight }; })()`);
  if (size.w > size.ww || size.h + 8 > size.wh) failures.push(`island ${size.w}x${size.h} doesn't fit the window`);
  console.log('open size', JSON.stringify(size));

  // interface 1: the compact island and its live activities, one fresh window per state
  const ART = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><defs><linearGradient id="g"><stop offset="0" stop-color="#3CC2B4"/><stop offset="1" stop-color="#E3B04B"/></linearGradient></defs><rect width="48" height="48" fill="url(#g)"/></svg>');
  const soon = 'Date.now() + 1084000';
  const STATES = [
    // name, messages, expected capsule [w, h] (null = hidden)
    ['c_clock', [], [112, 28]],
    ['c_idle', [{ t: 'island_settings', values: { idle_clock: false } }], [96, 28]],
    ['c_thin', [{ t: 'fullscreen', on: false, max: true }], [64, 6]],
    ['c_dots', [{ t: 'privacy', mic: ['Discord'], cam: ['Zoom'] }], [130, 28]],
    ['c_music', [{ t: 'media', has: true, playing: true, front: false, title: 'سورة الرحمن', artist: 'المنشاوي', art: ART }, { t: 'music_level', v: 0.7 }], [196, 32]],
    ['c_music_noart', [{ t: 'media', has: true, playing: true, front: false, title: 'x' }, { t: 'music_level', v: 0.3 }], [196, 32]],
    ['c_music_front', [{ t: 'media', has: true, playing: true, front: true, title: 'x' }], [112, 28]],
    ['c_music_off', [{ t: 'island_settings', values: { music_tab: false } }, { t: 'media', has: true, playing: true, front: false }], [112, 28]],
    ['c_focus', [`{ t: 'focus', phase: 'focus', round: 1, total: 4, ends_at: ${soon} }`], [176, 32]],
    ['c_break', [`{ t: 'focus', phase: 'break', round: 1, total: 4, ends_at: ${soon} }`], [176, 32]],
    ['c_paused', [{ t: 'focus', phase: 'focus', ends_at: null, paused_left: 754 }], [176, 32]],
    ['c_download', [{ t: 'downloads', items: [{ id: '1', name: 'a.zip', bytes: 5e7, speed: 4.2e6 }, { id: '2', name: 'b.iso', bytes: 1e9, speed: 1e6 }] }], [212, 32]],
    ['c_focus_wins', [{ t: 'media', has: true, playing: true, front: false }, { t: 'downloads', items: [{ id: '1', name: 'a', bytes: 1, speed: 1 }] }, `{ t: 'focus', phase: 'focus', ends_at: ${soon} }`], [176, 32]],
    ['c_music_dots', [{ t: 'media', has: true, playing: true, front: false, art: ART }, { t: 'privacy', mic: ['Discord'], cam: [] }], [214, 32]],
    ['c_fullscreen', [{ t: 'fullscreen', on: true }], null],
    ['c_fullscreen_turn', [{ t: 'fullscreen', on: true }, { t: 'state', state: 'listening' }], [280, 44]],
    ['c_theme_carnelian', [{ t: 'island_settings', values: { theme: 'carnelian' } }, `{ t: 'focus', phase: 'focus', ends_at: ${soon} }`], [176, 32]],
  ];
  const capsule = `document.querySelector('#root > div')`;
  for (const [name, msgs, want] of STATES) {
    const w = await open('', 580, 120);
    const run = c => w.webContents.executeJavaScript(c);
    for (const m of msgs) await run(`window.__yobi.deliver(${typeof m === 'string' ? m : JSON.stringify(m)})`);
    await sleep(900);
    const got = await run(`(() => { const r = ${capsule}.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), o: +getComputedStyle(${capsule}).opacity, rect: window.__yobi.lastRect, text: ${capsule}.innerText }; })()`);
    if (want === null) {
      if (got.o > 0.05 || !got.rect || got.rect.w !== 0) failures.push(`${name}: should be hidden, got ${JSON.stringify(got)}`);
    } else if (got.w !== want[0] || got.h !== want[1] || got.o < 0.99) {
      failures.push(`${name}: want ${want.join('x')}, got ${got.w}x${got.h} opacity ${got.o}`);
    } else if (!got.rect || got.rect.w !== want[0] || got.rect.h !== want[1] + 8) {
      failures.push(`${name}: click area ${JSON.stringify(got.rect)} doesn't match the capsule`);
    }
    fs.writeFileSync(path.join(OUT, `${name}.png`), (await w.webContents.capturePage({ x: 140, y: 0, width: 300, height: 50 })).toPNG());
    console.log('view', name, `${got.w}x${got.h}`, JSON.stringify(got.text));
    w.destroy();
  }

  // the morphs: clock → music → focus, and a celebration, caught mid-flight
  const mw = await open('', 580, 120);
  const mrun = c => mw.webContents.executeJavaScript(c);
  await sleep(700);
  await mrun(`window.__yobi.deliver(${JSON.stringify({ t: 'media', has: true, playing: true, front: false, art: ART })})`);
  for (const ms of [40, 120, 260]) { await sleep(ms === 40 ? 40 : ms - (ms === 120 ? 40 : 120)); fs.writeFileSync(path.join(OUT, `m_music_${ms}.png`), (await mw.webContents.capturePage({ x: 140, y: 0, width: 300, height: 50 })).toPNG()); }
  await sleep(700);
  await mrun(`window.__yobi.deliver({ t: 'focus', phase: 'focus', ends_at: ${soon} })`);
  for (const ms of [40, 120, 260]) { await sleep(ms === 40 ? 40 : ms - (ms === 120 ? 40 : 120)); fs.writeFileSync(path.join(OUT, `m_focus_${ms}.png`), (await mw.webContents.capturePage({ x: 140, y: 0, width: 300, height: 50 })).toPNG()); }
  await sleep(700);
  await mrun(`window.__yobi.deliver({ t: 'island_settings', values: { celebrate: true } }); window.__yobi.deliver({ t: 'notice', kind: 'focus_done', round: 1, next_min: 5 })`);
  for (const ms of [250, 500]) { await sleep(250); fs.writeFileSync(path.join(OUT, `m_celebrate_${ms}.png`), (await mw.webContents.capturePage({ x: 140, y: 0, width: 300, height: 50 })).toPNG()); }
  console.log('motion frames saved');

  // interface 2: Yobi's turn. Pictures of each state, then its rules, each in its own window.
  const crop = { x: 40, y: 0, width: 500, height: 130 };
  const TURNS = [
    ['t_listening', [{ t: 'state', state: 'listening', text: 'سامعك.. اتكلم' }, { t: 'level', v: 0.7 }]],
    ['t_thinking', [{ t: 'state', state: 'thinking', text: 'بفكر في طلبك…' }]],
    ['t_executing', [{ t: 'state', state: 'executing', text: 'بفتح Discord' }, { t: 'progress', v: 0.6 }]],
    ['t_executing_unknown', [{ t: 'state', state: 'executing', text: 'بنزّل التحديث' }, { t: 'progress', v: 2 }]],
    ['t_success', [{ t: 'state', state: 'success', text: 'تمام، فتحت ديسكورد ✅' }]],
    ['t_error', [{ t: 'say', state: 'error', text: 'مش لاقي البرنامج ده على الجهاز' }]],
    ['t_long', [{ t: 'say', state: 'info', text: 'الساعة ١٠:٤٥ بالليل. لو هتلعب كمان، اشرب مياه الأول وخد بريك صغير لعينيك.' }]],
    ['t_question', [{ t: 'ask', id: 'q1', text: 'قصدك Euro Truck Simulator 2 ولا Rocket League؟', options: [['Euro Truck Simulator 2', 'ets2'], ['Rocket League', 'rl'], ['لا، ولا حاجة', 'none']], timeout: 30000 }]],
  ];
  for (const [name, msgs] of TURNS) {
    const w = await open('', 580, 640);
    const run = c => w.webContents.executeJavaScript(c);
    await sleep(300);
    for (const m of msgs) await run(`window.__yobi.deliver(${JSON.stringify(m)})`);
    await sleep(3200);                                   // long enough for the longest reply to finish typing
    const got = await run(`(() => { const c = ${capsule}, r = c.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), text: c.innerText, ww: innerWidth, wh: innerHeight }; })()`);
    if (got.w > got.ww || got.h + 8 > got.wh) failures.push(`${name}: ${got.w}x${got.h} doesn't fit the window`);
    const say = msgs.find(m => m.text && m.t !== 'state' || m.t === 'state' && ['success'].includes(m.state));
    if (say && !got.text.includes(say.text.slice(-6))) failures.push(`${name}: the words aren't all shown: ${JSON.stringify(got.text)}`);
    fs.writeFileSync(path.join(OUT, `${name}.png`), (await w.webContents.capturePage(crop)).toPNG());
    console.log('view', name, `${got.w}x${got.h}`);
    w.destroy();
  }

  // the rules, all at once in parallel windows (they wait on real timers)
  const rule = async (name, body) => {
    const w = await open('', 580, 640);
    const run = c => w.webContents.executeJavaScript(c);
    const send = m => run(`window.__yobi.deliver(${JSON.stringify(m)})`);
    const st = () => run(`(() => { const s = window.__island.getState(); return { state: s.state, words: s.words, typing: s.typing, held: s.replyHeld, history: s.history.length, q: !!s.question, sent: window.__yobi.sent }; })()`);
    await sleep(300);
    try { await body({ run, send, st, w }); } catch (e) { failures.push(`${name}: ${e.message}`); }
    w.destroy();
  };
  const expect = (name, ok, what) => { if (!ok) throw new Error(what); };
  await Promise.all([
    rule('answer', async ({ run, send, st }) => {
      await send(TURNS[7][1][0]); await sleep(800);
      await run(`document.querySelector('#root button').click()`); await sleep(100);
      let s = await st();
      expect('answer', s.sent.some(m => m.t === 'answer' && m.id === 'q1' && m.value === 'ets2'), `no answer sent: ${JSON.stringify(s.sent)}`);
      expect('answer', !s.q, 'the buttons should go after an answer');
      await run(`document.querySelector('#root button')?.click()`);
      await sleep(2000); s = await st();
      expect('answer', s.state === 'idle', `should close 1.8 s after the answer, state ${s.state}`);
      expect('answer', s.sent.filter(m => m.t === 'answer').length === 1, 'answered twice');
      expect('answer', s.sent.at(-1).t === 'view' && s.sent.at(-1).state === 'idle' && !s.sent.at(-1).reply, `last view: ${JSON.stringify(s.sent.at(-1))}`);
    }),
    rule('reading time', async ({ send, st }) => {
      await send({ t: 'state', state: 'success', text: 'تم' });       // 3800 + 2*25 ms
      await sleep(3300); let s = await st();
      expect('reading', s.state === 'success', `closed too early: ${s.state}`);
      expect('reading', s.sent.some(m => m.t === 'view' && m.state === 'success' && m.reply), 'view should say the reply is showing');
      await sleep(1000); s = await st();
      expect('reading', s.state === 'idle', `should have closed by now: ${s.state}`);
    }),
    rule('streaming', async ({ send, st }) => {
      await send({ t: 'say', text: 'الساعة' }); await sleep(100);
      await send({ t: 'say', text: 'الساعة ١٠:٤٥ بالليل' }); await sleep(1500);
      const s = await st();
      expect('streaming', s.history === 1 && s.words === 'الساعة ١٠:٤٥ بالليل' && !s.typing, `history ${s.history}, words ${s.words}, typing ${s.typing}`);
    }),
    rule('end_turn waits for the reply', async ({ send, st }) => {
      await send({ t: 'say', text: 'أهلاً' }); await sleep(200);
      await send({ t: 'end_turn' }); await send({ t: 'listening_soft', text: 'سامعك' }); await sleep(100);
      let s = await st();
      expect('end_turn', s.state === 'info', `the reply was cut: ${s.state}`);
      await send({ t: 'state', state: 'thinking', text: 'بفكر' }); await send({ t: 'end_turn' }); await sleep(100);
      s = await st();
      expect('end_turn', s.state === 'idle', `end_turn should close a thinking turn: ${s.state}`);
    }),
    rule('hover holds a reply', async ({ run, send, st }) => {
      await send({ t: 'state', state: 'success', text: 'تم' });
      await run(`${capsule}.dispatchEvent(new PointerEvent('pointerover', { bubbles: true }))`);
      await sleep(4600); let s = await st();
      expect('hover', s.state === 'success', `closed under the pointer: ${s.state}`);
      await run(`${capsule}.dispatchEvent(new PointerEvent('pointerout', { bubbles: true }))`);
      await sleep(1800); s = await st();
      expect('hover', s.state === 'idle', `should close after the pointer leaves: ${s.state}`);
    }),
    rule('less motion types nothing', async ({ run, send, st }) => {
      await send({ t: 'island_settings', values: { reduce_motion: true } });
      await send({ t: 'say', text: 'الساعة ١٠:٤٥ بالليل. لو هتلعب كمان، اشرب مياه' }); await sleep(150);
      const s = await st(), shown = await run(`${capsule}.querySelector('p span[aria-hidden]').textContent`);
      expect('still', !s.typing && shown === s.words, `typing ${s.typing}, shown ${JSON.stringify(shown)}`);
    }),
  ]);
  console.log('turn rules checked');

  // the morph: compact → listening → a reply, caught mid-flight
  const tw = await open('', 580, 640);
  const trun = c => tw.webContents.executeJavaScript(c);
  await sleep(700);
  await trun(`window.__yobi.deliver({ t: 'state', state: 'listening', text: 'سامعك.. اتكلم' })`);
  for (const ms of [40, 120, 260]) { await sleep(ms === 40 ? 40 : ms - (ms === 120 ? 40 : 120)); fs.writeFileSync(path.join(OUT, `m_turn_${ms}.png`), (await tw.webContents.capturePage(crop)).toPNG()); }
  await sleep(600);
  await trun(`window.__yobi.deliver({ t: 'say', state: 'success', text: 'تمام، فتحت ديسكورد وشغّلت المزيكا' })`);
  for (const ms of [120, 400, 900]) { await sleep(ms === 120 ? 120 : ms === 400 ? 280 : 500); fs.writeFileSync(path.join(OUT, `m_reply_${ms}.png`), (await tw.webContents.capturePage(crop)).toPNG()); }

  // interface 3: the open panel. Pictures first, then its rules.
  const pcrop = { x: 70, y: 0, width: 440, height: 470 };
  const MACHINE = [
    { t: 'stats', cpu: 0.12, ram: 0.63, ram_used: 10.1 * 2 ** 30, ram_total: 16 * 2 ** 30, battery: { percent: 81, plugged: true } },
    { t: 'weather', temp: 23, code: 2, is_day: true, hi: 27, lo: 16, city: 'القاهرة' },
    { t: 'menu_state', listen: true, voice: false, companion: true },
  ];
  const hover = `${capsule}.dispatchEvent(new PointerEvent('pointerover', { bubbles: true }))`;
  const leave = `${capsule}.dispatchEvent(new PointerEvent('pointerout', { bubbles: true }))`;
  const click = sel => `document.querySelector(${JSON.stringify(sel)}).click()`;
  const PANELS = [
    ['p_home', [], []],
    ['p_home_privacy', [{ t: 'privacy', mic: ['Discord'], cam: [] }, { t: 'stats', cpu: 0.93, ram: 0.76, ram_used: 1, ram_total: 2, battery: { percent: 14, plugged: false } }, { t: 'hud', kind: 'net', online: false, gone_s: 0 }], []],
    ['p_menu', [], [click('[aria-label="خيارات تانية"]')]],
    ['p_chat', [], [click('[aria-label="اكتب رسالة ليوبي"]')]],
    ['p_page_apps', [], [click('[aria-label="التطبيقات"]')]],
  ];
  for (const [name, extra, acts] of PANELS) {
    const w = await open('', 580, 640);
    const run = c => w.webContents.executeJavaScript(c);
    for (const m of [...MACHINE, ...extra]) await run(`window.__yobi.deliver(${JSON.stringify(m)})`);
    await sleep(300); await run(hover); await sleep(500);
    for (const a of acts) { await run(a); await sleep(150); }
    await sleep(700);
    const got = await run(`(() => { const r = ${capsule}.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), ww: innerWidth, wh: innerHeight }; })()`);
    if (got.w > got.ww || got.h + 8 > got.wh) failures.push(`${name}: ${got.w}x${got.h} doesn't fit the window`);
    fs.writeFileSync(path.join(OUT, `${name}.png`), (await w.webContents.capturePage(pcrop)).toPNG());
    console.log('view', name, `${got.w}x${got.h}`);
    w.destroy();
  }
  const pstate = `(() => { const s = window.__island.getState(); return { open: s.panel.open, page: s.panel.page, menu: s.panel.menu, chat: s.panel.chat, kb: s.panel.kb, state: s.state, status: s.status, sent: window.__yobi.sent, focus: document.activeElement && document.activeElement.getAttribute('aria-label') }; })()`;
  const key = k => `document.dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(k)}, bubbles: true }))`;
  await Promise.all([
    rule('panel opens and closes', async ({ run }) => {
      await run(hover); await sleep(100);
      let s = await run(pstate); expect('', s.open, 'hover should open the panel');
      await run(leave); await sleep(250);
      s = await run(pstate); expect('', s.open, 'closed before its 450 ms grace');
      await sleep(450); s = await run(pstate);
      expect('', !s.open, 'should close after the pointer leaves');
      expect('', s.sent.some(m => m.t === 'panel' && m.open) && s.sent.at(-1).t === 'panel' && !s.sent.at(-1).open, `panel messages: ${JSON.stringify(s.sent)}`);
    }),
    rule('menu keeps it open', async ({ run }) => {
      await run(hover); await sleep(100);
      await run(click('[aria-label="خيارات تانية"]')); await sleep(100);
      await run(`window.__yobi.deliver(${JSON.stringify(MACHINE[2])})`); await sleep(100);
      await run(click('[role=menuitemcheckbox]')); await run(leave); await sleep(800);
      const s = await run(pstate);
      expect('', s.open && s.menu, 'the menu should keep the panel open');
      expect('', s.sent.some(m => m.t === 'menu_open') && s.sent.some(m => m.t === 'menu' && m.id === 'toggle_listen'), `sent: ${JSON.stringify(s.sent)}`);
      await run(key('Escape')); await sleep(100);
      expect('', !(await run(pstate)).menu, 'Esc should close the menu first');
    }),
    rule('write to Yobi', async ({ run }) => {
      await run(hover); await sleep(100);
      await run(click('[aria-label="اكتب رسالة ليوبي"]')); await sleep(200);
      await run(`(() => { const i = document.querySelector('input'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, '  افتح ديسكورد '); i.dispatchEvent(new Event('input', { bubbles: true })); i.form.requestSubmit(); })()`);
      await sleep(200);
      const s = await run(pstate);
      expect('', s.sent.some(m => m.t === 'chat' && m.text === 'افتح ديسكورد'), `no chat sent: ${JSON.stringify(s.sent)}`);
      expect('', !s.open && s.state === 'thinking' && s.status === 'افتح ديسكورد', `after sending: ${JSON.stringify(s)}`);
    }),
    rule('keyboard', async ({ run }) => {
      await run(`window.__yobi.deliver({ t: 'kb_open' })`); await sleep(300);
      let s = await run(pstate);
      expect('', s.open && s.kb && s.focus === 'كلّم يوبي من غير ما تنده', `kb open: ${JSON.stringify(s)}`);
      await run(leave); await sleep(700);
      expect('', (await run(pstate)).open, 'a keyboard-opened panel waits for Esc');
      await run(key('ArrowLeft')); await sleep(80); s = await run(pstate);
      expect('', s.page === 'apps' && s.sent.some(m => m.t === 'apps_get'), `ArrowLeft: ${s.page}`);
      await run(key('ArrowLeft')); await sleep(80);
      expect('', (await run(pstate)).page === 'shelf', 'ArrowLeft twice should reach the shelf');
      await run(key('Escape')); await sleep(80);
      expect('', !(await run(pstate)).open, 'Esc should close it');
    }),
    rule('a turn takes the island', async ({ run }) => {
      await run(hover); await sleep(100);
      await run(`window.__yobi.deliver({ t: 'state', state: 'listening', text: 'سامعك' })`); await sleep(100);
      expect('', !(await run(pstate)).open, 'a Yobi turn should close the panel');
    }),
    rule('talk button', async ({ run }) => {
      await run(hover); await sleep(100);
      await run(click('[aria-label="كلّم يوبي من غير ما تنده"]')); await sleep(100);
      const s = await run(pstate);
      expect('', !s.open && s.sent.some(m => m.t === 'quick' && m.id === 'listen'), `talk: ${JSON.stringify(s)}`);
    }),
  ]);
  console.log('panel rules checked');

  // the morph: compact → panel, caught mid-flight
  const pw = await open('', 580, 640);
  const prun = c => pw.webContents.executeJavaScript(c);
  for (const m of MACHINE) await prun(`window.__yobi.deliver(${JSON.stringify(m)})`);
  await sleep(700); await prun(hover);
  for (const ms of [60, 160, 320]) { await sleep(ms === 60 ? 60 : ms === 160 ? 100 : 160); fs.writeFileSync(path.join(OUT, `m_panel_${ms}.png`), (await pw.webContents.capturePage(pcrop)).toPNG()); }

  // interface 4: music. A colourful cover so the tint shows; pictures, then the rules.
  const COVER = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><rect width="120" height="120" fill="#1E5AA8"/><circle cx="35" cy="40" r="45" fill="#E3B04B"/><circle cx="95" cy="90" r="40" fill="#C2410C"/></svg>');
  const SONG = { t: 'media', has: true, playing: true, front: false, title: 'سورة الرحمن', artist: 'محمد صديق المنشاوي', app: 'Spotify', pos: 84, dur: 270, seek: true, art: COVER };
  const SONG2 = { ...SONG, title: 'سورة الملك', pos: 0 };
  const MUSIC = [
    ['mu_panel', [SONG], true],
    ['mu_paused_noart', [{ ...SONG, playing: false, art: null }], true],
    ['mu_panel_full', [SONG, { t: 'privacy', mic: ['Discord'], cam: ['Zoom'] }], true],
    ['mu_peek', [SONG, SONG2], false],
  ];
  for (const [name, msgs, open_] of MUSIC) {
    const w = await open('', 580, 640);
    const run = c => w.webContents.executeJavaScript(c);
    for (const m of [...MACHINE, ...msgs]) await run(`window.__yobi.deliver(${JSON.stringify(m)})`);
    await sleep(300); if (open_) await run(hover); await sleep(1100);
    const got = await run(`(() => { const r = ${capsule}.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), wh: innerHeight }; })()`);
    if (got.h + 8 > got.wh) failures.push(`${name}: ${got.h} tall doesn't fit the window`);
    if (name === 'mu_peek' && (got.w !== 330 || got.h !== 60)) failures.push(`mu_peek: the new-song card should show, got ${got.w}x${got.h}`);
    fs.writeFileSync(path.join(OUT, `${name}.png`), (await w.webContents.capturePage(open_ ? pcrop : crop)).toPNG());
    console.log('view', name, `${got.w}x${got.h}`);
    w.destroy();
  }
  const ms_ = `(() => { const s = window.__island.getState(); const sl = document.querySelector('[role=slider]'); return { playing: s.media.playing, peek: s.peekUntil > Date.now(), page: s.panel.page, sent: window.__yobi.sent.filter(m => m.t === 'media'), now: sl && +sl.getAttribute('aria-valuenow'), toggle: document.querySelector('[aria-label="وقّف"],[aria-label="شغّل"]')?.getAttribute('aria-label') }; })()`;
  const deliver = m => `window.__yobi.deliver(${JSON.stringify(m)})`;
  await Promise.all([
    rule('new-song card', async ({ run }) => {
      await run(deliver(SONG)); await sleep(100);
      expect('', !(await run(ms_)).peek, 'the first song we hear about is not "new"');
      await run(deliver(SONG2)); await sleep(100);
      expect('', (await run(ms_)).peek, 'a new song should show the card');
      await sleep(4400);                                   // 3.6 s, then the shrink settles
      const r = await run(`${capsule}.getBoundingClientRect().width`);
      expect('', !(await run(ms_)).peek && Math.round(r) === 196, `the card should end after 3.6 s and leave the live music pill, width ${r}`);
    }),
    rule('no card when you are looking', async ({ run }) => {
      await run(deliver(SONG)); await run(deliver({ ...SONG2, front: true })); await sleep(100);
      expect('', !(await run(ms_)).peek, 'no card when the player is in front');
      await run(deliver({ t: 'island_settings', values: { track_peek: false } })); await run(deliver({ ...SONG, title: 'x' })); await sleep(100);
      expect('', !(await run(ms_)).peek, 'no card when switched off');
      await run(deliver({ t: 'island_settings', values: { track_peek: true } })); await run(hover); await sleep(100);
      await run(deliver({ ...SONG, title: 'y' })); await sleep(100);
      expect('', !(await run(ms_)).peek, 'no card over the open panel');
    }),
    rule('controls', async ({ run }) => {
      await run(deliver(SONG)); await run(hover); await sleep(600);
      await run(click('[aria-label="وقّف"]')); await sleep(100);
      let s = await run(ms_);
      expect('', s.playing === false && s.toggle === 'شغّل' && s.sent.some(m => m.cmd === 'toggle'), `toggle: ${JSON.stringify(s)}`);
      await run(click('[aria-label="الأغنية الجاية"]')); await run(click('[aria-label="الأغنية اللي فاتت"]')); await sleep(100);
      s = await run(ms_);
      expect('', s.sent.some(m => m.cmd === 'next') && s.sent.some(m => m.cmd === 'prev'), `next/prev: ${JSON.stringify(s.sent)}`);
    }),
    rule('seek', async ({ run }) => {
      await run(deliver(SONG)); await run(hover); await sleep(600);
      await run(`(() => { const sl = document.querySelector('[role=slider]'), r = sl.getBoundingClientRect(); sl.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: r.left + r.width / 2, clientY: r.top + 2 })); })()`);
      await sleep(100); let s = await run(ms_);
      const seek = s.sent.find(m => m.cmd === 'seek');
      expect('', seek && Math.abs(seek.pos - 135) < 3, `click in the middle should seek to 2:15, sent ${JSON.stringify(seek)}`);
      await run(`document.querySelector('[role=slider]').focus(); document.querySelector('[role=slider]').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }))`);
      await sleep(100); s = await run(ms_);
      const last = s.sent.filter(m => m.cmd === 'seek').at(-1);
      expect('', last.pos > seek.pos + 9 && s.page === 'home', `ArrowRight should seek +10 s and not change the page: ${JSON.stringify(last)} page ${s.page}`);
    }),
    rule('the song colour comes from the cover', async ({ run }) => {
      const solid = c => 'data:image/svg+xml,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" fill="${c}"/></svg>`);
      const song = () => run(`getComputedStyle(document.querySelector('[style*="--song"]')).getPropertyValue('--song').trim()`);
      await run(deliver({ ...SONG, art: solid('#C2410C') })); await run(hover); await sleep(800);
      const red = await song();
      const hue = +(/hsl\((\d+)/.exec(red) || [])[1];
      expect('', hue >= 10 && hue <= 25, `a rust-red cover should give a red-orange colour, got ${red}`);
      await run(deliver({ ...SONG, title: 'grey', art: solid('#808080') })); await sleep(800);
      expect('', (await song()).toLowerCase() === '#3cc2b4', `a grey cover should fall back to the theme colour (faience #3cc2b4), got ${await song()}`);
    }),
    rule('the position runs', async ({ run }) => {
      await run(deliver(SONG)); await run(hover); await sleep(500);
      const a = (await run(ms_)).now; await sleep(2700);
      const b = (await run(ms_)).now;
      expect('', b > a, `the timeline should move while playing: ${a} → ${b}`);
    }),
  ]);
  console.log('music rules checked');

  // interface 5: the HUD. Each reading's picture, then its rules.
  const HUDS = [
    ['h_volume', { t: 'hud', kind: 'volume', value: 62, muted: false }],
    ['h_muted', { t: 'hud', kind: 'volume', value: 40, muted: true }],
    ['h_brightness', { t: 'hud', kind: 'brightness', value: 80 }],
    ['h_caps', { t: 'hud', kind: 'caps', on: true }],
    ['h_kbd', { t: 'hud', kind: 'kbd', name: 'العربية', badge: 'ع' }],
    ['h_battery_low', { t: 'hud', kind: 'battery', value: 14, plugged: false, low: true }],
    ['h_charging', { t: 'hud', kind: 'battery', value: 57, plugged: true, low: false }],
    ['h_net_back', { t: 'hud', kind: 'net', online: true, gone_s: 200 }],
    ['h_net_gone', { t: 'hud', kind: 'net', online: false, gone_s: 0 }],
  ];
  const hcrop = { x: 140, y: 0, width: 300, height: 56 };
  for (const [name, m] of HUDS) {
    const w = await open('', 580, 640);
    const run = c => w.webContents.executeJavaScript(c);
    await sleep(300); await run(deliver(m)); await sleep(500);
    const got = await run(`(() => { const r = ${capsule}.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), text: ${capsule}.innerText }; })()`);
    if (got.w !== 250 || got.h !== 36) failures.push(`${name}: the HUD should be 250x36, got ${got.w}x${got.h}`);
    fs.writeFileSync(path.join(OUT, `${name}.png`), (await w.webContents.capturePage(hcrop)).toPNG());
    console.log('view', name, JSON.stringify(got.text));
    w.destroy();
  }
  const hs = `(() => { const s = window.__island.getState(); const r = ${capsule}.getBoundingClientRect(); return { hud: !!s.hud && s.hud.until > Date.now(), kind: s.hud && s.hud.kind, offline: s.offline, w: Math.round(r.width), h: Math.round(r.height) }; })()`;
  await Promise.all([
    rule('a reading passes', async ({ run }) => {
      await run(deliver(HUDS[0][1])); await sleep(1200);
      expect('', (await run(hs)).hud, 'the HUD should still be up at 1.2 s');
      await sleep(1100); const s = await run(hs);
      expect('', !s.hud && s.w === 112, `the HUD should be gone by 2.3 s and the clock back, ${JSON.stringify(s)}`);
    }),
    rule('a low battery stays longer', async ({ run }) => {
      await run(deliver(HUDS[5][1])); await sleep(3000);
      expect('', (await run(hs)).hud, 'a low battery should stay 5 s');
    }),
    rule('never over a turn or the panel', async ({ run }) => {
      await run(deliver({ t: 'state', state: 'thinking', text: 'بفكر' })); await run(deliver(HUDS[0][1])); await run(deliver(HUDS[8][1])); await sleep(100);
      let s = await run(hs);
      expect('', !s.hud && s.offline, `no HUD over a turn (but the panel still learns the internet is gone): ${JSON.stringify(s)}`);
      await run(deliver({ t: 'state', state: 'idle' })); await run(hover); await sleep(100);
      await run(deliver(HUDS[2][1])); await sleep(100);
      expect('', !(await run(hs)).hud, 'no HUD over the open panel');
    }),
    rule('a turn clears the HUD', async ({ run }) => {
      await run(deliver(HUDS[0][1])); await sleep(100);
      await run(deliver({ t: 'state', state: 'listening', text: 'سامعك' })); await sleep(100);
      expect('', !(await run(hs)).hud, 'a Yobi turn should take the island from the HUD');
    }),
    rule('the HUD comes before the new-song card', async ({ run }) => {
      await run(deliver(SONG)); await run(deliver(SONG2)); await sleep(100);
      await run(deliver(HUDS[0][1])); await sleep(500);
      let s = await run(hs);
      expect('', s.w === 250, `the HUD should cover the new-song card, width ${s.w}`);
      await sleep(1600); s = await run(hs);
      expect('', s.w === 330, `the card should come back after the HUD while its time lasts, width ${s.w}`);
    }),
  ]);
  console.log('hud rules checked');

  // the liquid flowing: the same reading changing, caught mid-flight
  const vw = await open('', 580, 640);
  const vrun = c => vw.webContents.executeJavaScript(c);
  await sleep(300); await vrun(deliver({ t: 'hud', kind: 'volume', value: 20, muted: false })); await sleep(500);
  await vrun(deliver({ t: 'hud', kind: 'volume', value: 90, muted: false }));
  for (const ms of [60, 160, 400]) { await sleep(ms === 60 ? 60 : ms === 160 ? 100 : 240); fs.writeFileSync(path.join(OUT, `m_hud_${ms}.png`), (await vw.webContents.capturePage(hcrop)).toPNG()); }

  // interface 6: notices. Every kind's picture, then the rules.
  const T0 = Date.now();
  const NOTICES = [
    ['n_adhan', { t: 'notice', kind: 'adhan', prayer: 'asr', at: T0 }],
    ['n_prayer_soon', { t: 'notice', kind: 'prayer_soon', prayer: 'maghrib', minutes: 10, at: T0 }],
    ['n_focus_done', { t: 'notice', kind: 'focus_done', round: 2, next_min: 5 }],
    ['n_break_done', { t: 'notice', kind: 'break_done', focus_min: 25 }],
    ['n_ayah', { t: 'notice', kind: 'reminder', sub: 'ayah', text: 'أَلَا بِذِكْرِ ٱللَّهِ تَطْمَئِنُّ ٱلْقُلُوبُ', ref: 'الرعد ٢٨', seconds: 20 }],
    ['n_dhikr', { t: 'notice', kind: 'reminder', sub: 'dhikr', text: 'سبحان الله وبحمده، سبحان الله العظيم', seconds: 20 }],
    ['n_meeting', { t: 'notice', kind: 'meeting', id: 'm1', title: 'مراجعة المشروع', at: T0, has_link: true }],
    ['n_download', { t: 'notice', kind: 'download_done', id: 'd1', name: 'movie.mkv', size: 734e6 }],
    ['n_link', { t: 'notice', kind: 'smart', what: 'link', value: 'https://github.com/yobi/island/pull/42' }],
    ['n_color', { t: 'notice', kind: 'smart', what: 'color', value: '#E8A25B' }],
    ['n_math', { t: 'notice', kind: 'smart', what: 'math', value: '35 × 35 + 20', result: 1245 }],
    ['n_count', { t: 'notice', kind: 'smart', what: 'count', words: 412, chars: 2310 }],
    ['n_brief', { t: 'notice', kind: 'brief', greet: 'صباح الفل 🌞', weather: { temp: 23, code: 2, hi: 27 }, next: { prayer: 'dhuhr', at: T0 + 3600e3 }, meetings: 2, first_meeting: { title: 'x', start: T0 + 7200e3 } }],
    ['n_welcome', { t: 'notice', kind: 'welcome', away_min: 95, events: ['فاتك أذان العصر', 'التحميل خلص: movie.mkv'] }],
    ['n_care', { t: 'notice', kind: 'care', title: 'بقالك ساعتين قدام الشاشة', text: 'قوم اتمشى دقيقتين وبص لحاجة بعيدة' }],
    ['n_screenshot', { t: 'notice', kind: 'screenshot', w: 1920, h: 1080, thumb: COVER }],
  ];
  const ncrop = { x: 40, y: 0, width: 500, height: 280 };
  for (const [name, m] of NOTICES) {
    const w = await open('', 580, 640);
    const run = c => w.webContents.executeJavaScript(c);
    await sleep(300); await run(deliver(m)); await sleep(900);
    const got = await run(`(() => { const r = ${capsule}.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), wh: innerHeight, text: ${capsule}.innerText }; })()`);
    if (got.w !== 380 || got.h + 8 > got.wh || got.h < 60) failures.push(`${name}: the notice should be 380 wide and fit, got ${got.w}x${got.h}`);
    fs.writeFileSync(path.join(OUT, `${name}.png`), (await w.webContents.capturePage(ncrop)).toPNG());
    console.log('view', name, `${got.w}x${got.h}`);
    w.destroy();
  }
  const ns = `(() => { const s = window.__island.getState(); const r = ${capsule}.getBoundingClientRect(); return { on: !!s.notice, kind: s.notice && s.notice.msg.kind, paused: s.notice && s.notice.paused, history: s.history.map(h => h.label || h.kind), celebrate: s.celebrateAt, w: Math.round(r.width), o: +getComputedStyle(${capsule}).opacity, sent: window.__yobi.sent.filter(m => m.t !== 'view' && m.t !== 'panel') }; })()`;
  const N = Object.fromEntries(NOTICES.map(([k, m]) => [k, m]));
  await Promise.all([
    rule('a notice passes', async ({ run }) => {
      await run(deliver(N.n_count)); await sleep(5500);
      expect('', (await run(ns)).on, 'a 6 s notice should still be up at 5.5 s');
      await sleep(900); expect('', !(await run(ns)).on, 'it should be gone after 6 s');
    }),
    rule('hovering holds a notice', async ({ run }) => {
      await run(deliver(N.n_count)); await sleep(500); await run(hover); await sleep(6500);
      let s = await run(ns);
      expect('', s.on && s.paused, `held under the pointer: ${JSON.stringify(s)}`);
      await run(leave); await sleep(1200);
      expect('', (await run(ns)).on, 'at least 1.5 s more after leaving');
      await sleep(5200); s = await run(ns);
      expect('', !s.on, 'it should end after the rest of its time');
    }),
    rule('a reminder waits when the island is busy', async ({ run }) => {
      await run(deliver({ t: 'state', state: 'thinking', text: 'بفكر' })); await run(deliver(N.n_dhikr)); await run(deliver(N.n_download)); await sleep(100);
      let s = await run(ns);
      expect('', !s.on && s.sent.filter(m => m.t === 'notice_dropped' && m.kind === 'reminder').length === 1, `over a turn: ${JSON.stringify(s)}`);
      await run(deliver({ t: 'state', state: 'idle' })); await run(deliver(N.n_count)); await run(deliver(N.n_dhikr)); await sleep(100);
      s = await run(ns);
      expect('', s.kind === 'smart' && s.sent.filter(m => m.t === 'notice_dropped').length === 2, `over another notice: ${JSON.stringify(s)}`);
    }),
    rule('buttons', async ({ run }) => {
      const press = label => run(`[...document.querySelectorAll('#root button')].find(b => b.textContent === ${JSON.stringify(label)}).click()`);
      await run(deliver(N.n_download)); await sleep(500); await press('افتح'); await sleep(80);
      await run(deliver(N.n_meeting)); await sleep(500); await press('انضم'); await sleep(80);
      await run(deliver(N.n_math)); await sleep(500); await press('انسخ الناتج'); await sleep(80);
      await run(deliver(N.n_break_done)); await sleep(500); await press('ابدأ ٢٥ د'); await sleep(80);
      await run(deliver(N.n_link)); await sleep(500); await press('تمام'); await sleep(80);
      const s = await run(ns);
      const want = [{ t: 'dl_open', id: 'd1' }, { t: 'meeting_join', id: 'm1' }, { t: 'smart_action', action: 'copy_result', value: '1245' }, { t: 'notice_action', action: 'focus_start' }];
      expect('', JSON.stringify(s.sent) === JSON.stringify(want) && !s.on, `sent ${JSON.stringify(s.sent)}, notice ${s.on}`);
    }),
    rule('fullscreen lets the adhan and meetings through', async ({ run }) => {
      await run(deliver({ t: 'fullscreen', on: true })); await run(deliver(N.n_download)); await sleep(700);
      expect('', (await run(ns)).o < 0.05, 'a download notice should stay hidden over a fullscreen game');
      await run(deliver(N.n_adhan)); await sleep(700);
      expect('', (await run(ns)).o > 0.95, 'the adhan should get through');
    }),
    rule('history, celebration, and the HUD on top', async ({ run }) => {
      await run(deliver({ t: 'island_settings', values: { celebrate: true } }));
      await run(deliver(N.n_count)); await run(deliver(N.n_focus_done)); await sleep(100);
      let s = await run(ns);
      expect('', s.history.join() === 'تركيز' && s.celebrate > 0, `history ${JSON.stringify(s.history)} (copies aren't kept), celebrate ${s.celebrate}`);
      await run(deliver(HUDS[0][1])); await sleep(500);
      expect('', (await run(ns)).w === 250, 'the HUD shows over a notice');
      await sleep(1700); s = await run(ns);
      expect('', s.w === 380 && s.kind === 'focus_done', `the notice comes back after the HUD: ${s.w} ${s.kind}`);
    }),
  ]);
  console.log('notice rules checked');

  // interface 7: your day. Prayer times are built around "now" so the sky shows each part of the day.
  const H = 3600e3, NOW = Date.now();
  const times = o => ({ t: 'prayer', city: 'القاهرة', times: Object.fromEntries(Object.entries(o).map(([k, h]) => [k, NOW + h * H])) });
  const DAY = times({ fajr: -9, sunrise: -7.7, dhuhr: -2.6, asr: 0.5, maghrib: 2.9, isha: 4.2, next_fajr: 15 });
  const NIGHT = times({ fajr: -19, sunrise: -17.7, dhuhr: -12.6, asr: -9.5, maghrib: -7, isha: -5.6, next_fajr: 4 });
  const DUSK = times({ fajr: -12, sunrise: -10.7, dhuhr: -5.6, asr: -2.5, maghrib: -0.4, isha: 1, next_fajr: 12 });
  const FOCUS = { t: 'focus', phase: 'focus', round: 1, total: 1500, ends_at: NOW + 1084e3, paused_left: null, focus_min: 25 };
  const WATER = { t: 'water', count: 3, goal: 8 };
  const MEET = { t: 'meetings', events: [{ id: 'm1', title: 'مراجعة المشروع', start: NOW + 12 * 60e3, end: NOW + 72 * 60e3, has_link: true }] };
  const STATIONS = { t: 'radio_stations', items: ['محمد صديق المنشاوي', 'عبد الباسط عبد الصمد', 'محمود خليل الحصري', 'ماهر المعيقلي', 'سعد الغامدي'].map((name, i) => ({ name, url: `https://backup.qurango.net/radio/r${i}` })) };
  const dcrop = { x: 70, y: 0, width: 440, height: 630 };
  const DAYS = [
    ['d_home', [DAY, FOCUS, WATER, MEET], []],
    ['d_home_night', [NIGHT, { t: 'focus', phase: null, focus_min: 25 }, WATER], []],
    ['d_home_dusk', [DUSK, { ...FOCUS, phase: 'break', ends_at: null, paused_left: 140, total: 300 }], []],
    ['d_home_full', [DAY, FOCUS, WATER, MEET, SONG, { t: 'privacy', mic: ['Discord'], cam: [] }], []],
    ['d_prayer', [DAY], [`document.querySelector('[aria-label^="مواقيت الصلاة"]').click()`]],
    ['d_radio', [DAY, STATIONS, { t: 'island_settings', values: { radio_station: STATIONS.items[0].url } }], [`document.querySelector('[aria-label^="مواقيت الصلاة"]').click()`, `[...document.querySelectorAll('#root button')].find(b => b.textContent.includes('إذاعة القرآن')).click()`]],
  ];
  for (const [name, msgs, acts] of DAYS) {
    const w = await open('', 580, 640);
    const run = c => w.webContents.executeJavaScript(c);
    for (const m of [...MACHINE, ...msgs]) await run(deliver(m));
    await sleep(300); await run(hover); await sleep(600);
    for (const a of acts) { await run(a); await sleep(400); }
    await sleep(700);
    const got = await run(`(() => { const r = ${capsule}.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), wh: innerHeight }; })()`);
    if (got.h + 8 > got.wh) failures.push(`${name}: ${got.h} tall doesn't fit the ${got.wh} window`);
    fs.writeFileSync(path.join(OUT, `${name}.png`), (await w.webContents.capturePage(dcrop)).toPNG());
    console.log('view', name, `${got.w}x${got.h}`);
    w.destroy();
  }
  const ds = `(() => { const s = window.__island.getState(); return { page: s.panel.page, water: s.water && s.water.count, celebrate: s.celebrateAt, radio: s.radio, sent: window.__yobi.sent.filter(m => !['view', 'panel', 'menu_open'].includes(m.t)) }; })()`;
  const pressLabel = l => `document.querySelector('[aria-label="${l}"]').click()`;
  await Promise.all([
    rule('focus buttons', async ({ run }) => {
      await run(deliver({ t: 'focus', phase: null, focus_min: 25 })); await run(hover); await sleep(400);
      await run(pressLabel('ابدأ جلسة تركيز')); await run(deliver(FOCUS)); await sleep(200);
      await run(pressLabel('وقّف مؤقتًا')); await run(pressLabel('إنهاء الجلسة')); await sleep(100);
      const s = await run(ds);
      expect('', s.sent.map(m => m.cmd).join() === 'start,pause,stop', `focus: ${JSON.stringify(s.sent)}`);
    }),
    rule('water', async ({ run }) => {
      await run(deliver({ t: 'island_settings', values: { celebrate: true } })); await run(deliver({ t: 'water', count: 7, goal: 8 })); await run(hover); await sleep(400);
      await run(pressLabel('شربت كوباية')); await sleep(100);
      const s = await run(ds);
      expect('', s.water === 8 && s.celebrate > 0 && s.sent.some(m => m.t === 'water' && m.cmd === 'add'), `water: ${JSON.stringify({ w: s.water, c: s.celebrate, sent: s.sent })}`);
    }),
    rule('meeting join only near the time', async ({ run }) => {
      await run(deliver({ t: 'meetings', events: [{ ...MEET.events[0], start: NOW + 40 * 60e3 }] })); await run(hover); await sleep(400);
      expect('', !(await run(`!!document.querySelector('#root button') && [...document.querySelectorAll('#root button')].some(b => b.textContent === 'انضم')`)), 'no join 40 minutes before');
      await run(deliver(MEET)); await sleep(300);
      await run(`[...document.querySelectorAll('#root button')].find(b => b.textContent === 'انضم').click()`); await sleep(100);
      expect('', (await run(ds)).sent.some(m => m.t === 'meeting_join' && m.id === 'm1'), 'join should send meeting_join');
    }),
    rule('prayer page and radio', async ({ run }) => {
      await run(deliver(DAY)); await run(hover); await sleep(400);
      await run(`document.querySelector('[aria-label^="مواقيت الصلاة"]').click()`); await sleep(200);
      expect('', (await run(ds)).page === 'prayer', 'the sky opens the prayer times');
      await run(`[...document.querySelectorAll('#root button')].find(b => b.textContent.includes('إذاعة القرآن')).click()`); await sleep(200);
      let s = await run(ds);
      expect('', s.page === 'radio' && s.sent.some(m => m.t === 'radio_get'), `radio page asks for stations: ${JSON.stringify(s.sent)}`);
      await run(deliver(STATIONS)); await sleep(200);
      await run(`[...document.querySelectorAll('#root button')].find(b => b.textContent === 'ماهر المعيقلي').click()`); await sleep(600);
      s = await run(ds);
      expect('', s.radio.name === 'ماهر المعيقلي' && s.sent.some(m => m.t === 'settings_set' && m.values.radio_station === STATIONS.items[3].url), `choosing a reciter: ${JSON.stringify(s.radio)}`);
      await run(`document.querySelector('[aria-label="دوّر على قارئ"]').focus(); document.querySelector('[aria-label="دوّر على قارئ"]').dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }))`);
      await sleep(80); expect('', (await run(ds)).page === 'radio', 'arrows in the search box should not change the page');
    }),
    rule('the adhan pauses the radio; the last station comes back', async ({ run }) => {
      await run(deliver(STATIONS)); await run(deliver({ t: 'island_settings', values: { radio_station: STATIONS.items[1].url } })); await sleep(100);
      let s = await run(ds);
      expect('', s.radio.url === STATIONS.items[1].url && s.radio.name === 'عبد الباسط عبد الصمد', `the saved station: ${JSON.stringify(s.radio)}`);
      await run(`window.__island.setState(s => ({ radio: { ...s.radio, playing: true } }))`);
      await run(deliver({ t: 'notice', kind: 'adhan', prayer: 'asr', at: NOW })); await sleep(100);
      s = await run(ds);
      expect('', !s.radio.playing && s.radio.msg === 'وقفت الإذاعة عشان الأذان', `after the adhan: ${JSON.stringify(s.radio)}`);
    }),
  ]);
  console.log('day rules checked');

  // interface 8: the work pages
  const APPS = { t: 'apps', pinned: [['Discord', true], ['Google Chrome', true], ['Visual Studio Code', false], ['Spotify', true], ['Steam', false], ['Telegram', false], ['OBS Studio', false]].map(([name, running]) => ({ name, icon: '', running })) };
  const CATALOG = { t: 'apps', pinned: APPS.pinned, catalog: ['Discord', 'Notepad', 'Paint', 'Word', 'Excel', 'Calculator'] };
  const SHELF = { t: 'shelf', items: [['تقرير الشهر.pdf', false], ['notes.txt', false], ['صور الرحلة.zip', false], ['screenshot.png', false], ['intro.mp4', false], ['المشروع', true]].map(([name, dir], i) => ({ i, name, path: `C:\\Users\\me\\Desktop\\${name}`, dir })) };
  const CLIPS = { t: 'clips', enabled: true, items: ['اجتماع بكرة الساعة ١١ في المكتب', 'https://github.com/yobi/island/pull/42', 'npm run tauri build', 'شكراً جداً على المساعدة 🙏'] };
  const DL = { t: 'downloads', items: [{ id: '1', name: 'movie.mkv', bytes: 4.2e8, speed: 5.1e6 }, { id: '2', name: 'b.iso', bytes: 1e9, speed: 1e6 }] };
  const dock = l => `document.querySelector('[aria-label="${l}"]').click()`;
  const WORK = [
    ['w_apps', [APPS], [dock('التطبيقات')]],
    ['w_apps_edit', [APPS], [dock('التطبيقات'), `[...document.querySelectorAll('#root button')].find(b => b.textContent === 'تعديل').click()`]],
    ['w_apps_picker', [APPS], [dock('التطبيقات'), `[...document.querySelectorAll('#root button')].find(b => b.textContent === 'تعديل').click()`, `[...document.querySelectorAll('#root button')].find(b => b.textContent === 'ضيف').click()`, deliver(CATALOG)]],
    ['w_shelf', [SHELF], [dock('الرف')]],
    ['w_shelf_empty', [], [dock('الرف')]],
    ['w_clips', [CLIPS], [dock('الحافظة'), `document.querySelector('[title="دوس عشان تنسخه"]').click()`]],
    ['w_history', [{ t: 'say', text: 'تمام، فتحت ديسكورد', state: 'success' }, { t: 'state', state: 'idle' }, { t: 'notice', kind: 'download_done', id: 'd', name: 'movie.mkv', size: 7e8 }, { t: 'ask', id: 'q', text: 'أفتح سبوتيفاي؟', options: [['أيوه', 'yes']], timeout: 100 }, { t: 'state', state: 'idle' }], [`window.__island.setState({ notice: null })`, hover, dock('خيارات تانية'), `[...document.querySelectorAll('#root button')].find(b => b.textContent.includes('اللي فات')).click()`]],
    ['w_downloads', [DL], []],
    ['w_drop', [SHELF], [`window.__yobi.drop('enter', ['C:\\\\x.txt'])`]],
  ];
  for (const [name, msgs, acts] of WORK) {
    const w = await open('', 580, 640);
    const run = c => w.webContents.executeJavaScript(c);
    for (const m of [...MACHINE, DAY, ...msgs]) await run(deliver(m));
    await sleep(300); if (name !== 'w_history') await run(hover); await sleep(500);
    for (const a of acts) { await run(a); await sleep(350); }
    await sleep(700);
    const got = await run(`(() => { const r = ${capsule}.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), wh: innerHeight }; })()`);
    if (got.h + 8 > got.wh) failures.push(`${name}: ${got.h} tall doesn't fit the ${got.wh} window`);
    fs.writeFileSync(path.join(OUT, `${name}.png`), (await w.webContents.capturePage(dcrop)).toPNG());
    console.log('view', name, `${got.w}x${got.h}`);
    w.destroy();
  }
  const ws = `(() => { const s = window.__island.getState(); return { open: s.panel.open, page: s.panel.page, dropping: s.dropping, history: s.history.length, dragged: window.__yobi.dragged, sent: window.__yobi.sent.filter(m => !['view', 'panel', 'menu_open'].includes(m.t)) }; })()`;
  const btn = t => `[...document.querySelectorAll('#root button')].find(b => b.textContent === ${JSON.stringify(t)} || b.title === ${JSON.stringify(t)} || b.getAttribute('aria-label') === ${JSON.stringify(t)}).click()`;
  await Promise.all([
    rule('apps', async ({ run }) => {
      await run(deliver(APPS)); await run(hover); await sleep(300); await run(dock('التطبيقات')); await sleep(300);
      await run(btn('تعديل')); await sleep(150); await run(btn('شيل Steam')); await run(btn('ضيف')); await sleep(150);
      await run(deliver(CATALOG)); await sleep(200); await run(btn('Paint')); await run(btn('خلصت')); await sleep(200);
      await run(btn('Discord')); await sleep(150);
      const s = await run(ws);
      const want = [{ t: 'apps_get' }, { t: 'app_unpin', name: 'Steam' }, { t: 'apps_get' }, { t: 'app_pin', name: 'Paint' }, { t: 'app_open', name: 'Discord' }];
      expect('', JSON.stringify(s.sent) === JSON.stringify(want) && !s.open, `apps: ${JSON.stringify(s)}`);
    }),
    rule('shelf', async ({ run }) => {
      await run(deliver(SHELF)); await run(hover); await sleep(300); await run(dock('الرف')); await sleep(400);
      await run(`document.querySelector('[title$="notes.txt"]').click()`);
      await run(btn('وريني مكان intro.mp4')); await run(btn('شيل صور الرحلة.zip من الرف'));
      await run(`(() => { const b = document.querySelector('[title$="screenshot.png"]'), r = b.getBoundingClientRect();
        b.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, clientX: r.left + 20, clientY: r.top + 10, buttons: 1 }));
        b.dispatchEvent(new PointerEvent('pointermove', { bubbles: true, clientX: r.left + 40, clientY: r.top + 22, buttons: 1 })); })()`);
      await run(btn('فضّي الرف')); await sleep(100);
      const s = await run(ws);
      const want = [{ t: 'shelf_open', i: 1 }, { t: 'shelf_folder', i: 4 }, { t: 'shelf_remove', i: 2 }, { t: 'shelf_clear' }];
      expect('', JSON.stringify(s.sent) === JSON.stringify(want) && s.dragged.join() === 'C:\\Users\\me\\Desktop\\screenshot.png', `shelf: ${JSON.stringify(s)}`);
    }),
    rule('clipboard and history', async ({ run }) => {
      await run(deliver(CLIPS)); await run(deliver({ t: 'say', text: 'أهلاً', state: 'info' })); await run(deliver({ t: 'state', state: 'idle' }));
      await run(hover); await sleep(300); await run(dock('الحافظة')); await sleep(300);
      await run(`document.querySelectorAll('[title="دوس عشان تنسخه"]')[2].click()`); await run(btn('امسح')); await sleep(100);
      let s = await run(ws);
      expect('', JSON.stringify(s.sent) === JSON.stringify([{ t: 'clip_copy', i: 2 }, { t: 'clip_clear' }]), `clips: ${JSON.stringify(s.sent)}`);
      await run(dock('خيارات تانية')); await sleep(150); await run(`[...document.querySelectorAll('#root button')].find(b => b.textContent.includes('اللي فات')).click()`); await sleep(300);
      expect('', (await run(ws)).page === 'history' && (await run(ws)).history === 1, 'the menu opens the history with one entry');
      await run(btn('امسح')); await sleep(100);
      expect('', (await run(ws)).history === 0, 'clearing the history');
    }),
    rule('dropping files', async ({ run }) => {
      await run(`window.__yobi.drop('enter', ['C:\\\\a.txt', 'C:\\\\b.png'])`); await sleep(200);
      let s = await run(ws);
      expect('', s.open && s.page === 'shelf' && s.dropping, `dragging over: ${JSON.stringify(s)}`);
      await run(`window.__yobi.drop('drop', ['C:\\\\a.txt', 'C:\\\\b.png'])`); await sleep(100);
      s = await run(ws);
      expect('', !s.dropping && JSON.stringify(s.sent) === JSON.stringify([{ t: 'shelf_add', paths: ['C:\\a.txt', 'C:\\b.png'] }]), `dropped: ${JSON.stringify(s)}`);
      await run(deliver({ t: 'state', state: 'thinking', text: 'x' })); await run(`window.__yobi.drop('enter', ['C:\\\\c.txt'])`); await sleep(100);
      expect('', !(await run(ws)).dropping, 'no drop target over a Yobi turn');
    }),
  ]);
  console.log('work rules checked');

  // interface 9: the settings window, fed Python's real defaults (settings_sample.json)
  const SETTINGS = JSON.parse(fs.readFileSync(path.join(__dirname, 'settings_sample.json'), 'utf8'));
  const sopen = async () => {
    const w = await open('settings', 900, 640);
    const run = c => w.webContents.executeJavaScript(c);
    await sleep(300);
    expect('', (await run(`window.__yobi.sent.some(m => m.t === 'settings_get')`)), 'the window should ask Python for the settings');
    await run(deliver(SETTINGS)); await sleep(600);
    return { w, run };
  };
  try {
    const { w, run } = await sopen();
    fs.writeFileSync(path.join(OUT, 's_top.png'), (await w.webContents.capturePage()).toPNG());
    for (const id of ['prayer', 'keys']) {
      await run(`document.querySelector('#s-${id}').scrollIntoView({ block: 'start' })`); await sleep(500);
      fs.writeFileSync(path.join(OUT, `s_${id}.png`), (await w.webContents.capturePage()).toPNG());
    }
    await run(`(() => { const i = document.querySelector('[aria-label="دوّر في الإعدادات"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, 'الصلاة'); i.dispatchEvent(new Event('input', { bubbles: true })); })()`);
    await sleep(400); fs.writeFileSync(path.join(OUT, 's_search.png'), (await w.webContents.capturePage()).toPNG());
    console.log('view settings');
    w.destroy();
  } catch (e) { failures.push(`settings pictures: ${e.message}`); }
  await Promise.all([
    rule('settings save what you change', async () => {
      const { w, run } = await sopen();
      const sent = () => run(`window.__yobi.sent.filter(m => m.t === 'settings_set' || m.t === 'preview')`);
      await run(`document.querySelector('[role=switch][aria-label="الأغنية اللي شغالة"]').click()`);
      await run(`[...document.querySelectorAll('[role=radio]')].find(b => b.textContent.includes('عقيق')).click()`);
      await run(`(() => { const i = document.querySelector('[aria-label="مدة التركيز"]'); i.focus(); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, '40'); i.dispatchEvent(new FocusEvent('focusout', { bubbles: true })); })()`);
      await run(`(() => { const s = document.querySelector('[aria-label="الجزيرة تظهر على"]'); s.value = '2'; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
      await run(`[...document.querySelectorAll('button')].find(b => b.textContent.includes('جرّب تنبيه الأذان')).click()`);
      await sleep(150);
      const got = await sent();
      const want = [{ t: 'settings_set', section: 'island', values: { music_tab: false } }, { t: 'settings_set', section: 'island', values: { theme: 'carnelian' } },
        { t: 'settings_set', section: 'daily', values: { focus_min: 40 } }, { t: 'settings_set', section: 'island', values: { display: '2' } }, { t: 'preview', what: 'adhan' }];
      expect('', JSON.stringify(got) === JSON.stringify(want), `sent ${JSON.stringify(got)}`);
      await run(deliver({ t: 'settings_saved' })); await sleep(100);
      expect('', (await run(`document.querySelector('[role=status]').textContent`)) === 'اتحفظ ✓', 'a save should say so');
      w.destroy();
    }),
    rule('settings: city, calendar, search', async () => {
      const { w, run } = await sopen();
      await run(`(() => { const s = document.querySelector('[aria-label="المدينة"]'); s.value = '__other'; s.dispatchEvent(new Event('change', { bubbles: true })); })()`);
      await run(deliver({ ...SETTINGS, daily: { ...SETTINGS.daily, city: 'مكان تاني' } })); await sleep(200);
      expect('', await run(`!!document.querySelector('[aria-label="خط العرض"]')`), 'another place shows the coordinates');
      const setIcal = v => run(`(() => { const i = document.querySelector('[aria-label="رابط iCal"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, ${JSON.stringify(v)}); i.dispatchEvent(new Event('input', { bubbles: true })); [...document.querySelectorAll('button')].find(b => b.textContent === 'احفظ').click(); })()`);
      await setIcal('http://not-secure.example/cal.ics'); await sleep(100);
      expect('', (await run(`document.querySelector('[role=status]').textContent`)).includes('https'), 'an http link should be refused');
      await setIcal('https://calendar.google.com/calendar/ical/x/basic.ics'); await sleep(100);
      const sent = await run(`window.__yobi.sent.filter(m => m.t === 'settings_set')`);
      expect('', JSON.stringify(sent) === JSON.stringify([{ t: 'settings_set', section: 'daily', values: { city: 'مكان تاني' } }, { t: 'settings_set', section: 'daily', values: { calendar_ical: 'https://calendar.google.com/calendar/ical/x/basic.ics' } }]), `sent ${JSON.stringify(sent)}`);
      await run(`(() => { const i = document.querySelector('[aria-label="دوّر في الإعدادات"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(i, 'كاميرا'); i.dispatchEvent(new Event('input', { bubbles: true })); })()`);
      await sleep(150);
      const secs = await run(`[...document.querySelectorAll('main section')].map(s => s.id)`);
      expect('', secs.join() === 's-shows', `searching "كاميرا" should leave one section, got ${secs}`);
      w.destroy();
    }),
    rule('the island opens settings and follows the screen choice', async ({ run }) => {
      await run(hover); await sleep(200); await run(dock('خيارات تانية')); await sleep(150);
      await run(`[...document.querySelectorAll('#root button')].find(b => b.textContent.includes('الإعدادات')).click()`); await sleep(100);
      await run(deliver({ t: 'island_settings', values: { display: 'cursor' } })); await sleep(100);
      const s = await run(`({ opened: window.__yobi.settingsOpened, screen: window.__yobi.screen, open: window.__island.getState().panel.open })`);
      expect('', s.opened === 1 && s.screen === 'cursor' && !s.open, `island: ${JSON.stringify(s)}`);
    }),
  ]);
  console.log('settings rules checked');

  // English (Settings → Look → Language): every word, the direction, and the numbers follow it
  const AR = /[؀-ۿ]/;
  await Promise.all([
    rule('english: the panel', async ({ run, w }) => {
      await run(deliver({ t: 'island_settings', values: { lang: 'en' } })); await sleep(300);
      await run(hover); await sleep(700);
      const s = await run(`({ dir: document.documentElement.dir, text: document.querySelector('#root').innerText })`);
      expect('', s.dir === 'ltr', `direction ${s.dir}`);
      expect('', /Talk/.test(s.text) && /Write/.test(s.text), `English dock: ${JSON.stringify(s.text)}`);
      expect('', !AR.test(s.text), `Arabic left in the panel: ${JSON.stringify(s.text.match(/[^\n]*[؀-ۿ][^\n]*/g))}`);
      fs.writeFileSync(path.join(OUT, 'en_panel.png'), (await w.webContents.capturePage()).toPNG());
      await run(dock('More')); await sleep(200);
      const menu = await run(`document.querySelector('#root').innerText`);
      expect('', /Settings/.test(menu) && /Quit Yobi/.test(menu) && !AR.test(menu), `English menu: ${JSON.stringify(menu)}`);
    }),
    rule('english: a notice and the compact island', async ({ run }) => {
      await run(deliver({ t: 'island_settings', values: { lang: 'en' } }));
      await run(deliver({ t: 'focus', phase: 'focus', round: 1, total: 4, ends_at: Date.now() + 1084000 })); await sleep(500);
      const c = await run(`document.querySelector('#root > div').innerText`);
      expect('', /\d/.test(c) && !AR.test(c), `compact island in English: ${JSON.stringify(c)}`);
      await run(deliver({ t: 'notice', kind: 'focus_done', round: 1, next_min: 5 })); await sleep(500);
      const n = await run(`document.querySelector('[role=status]')?.innerText || ''`);
      expect('', n && !AR.test(n), `notice in English: ${JSON.stringify(n)}`);
    }),
    rule('english: the settings window', async () => {
      const w = await open('settings', 900, 640);
      const run = c => w.webContents.executeJavaScript(c);
      await sleep(300);
      await run(deliver({ ...SETTINGS, island: { ...SETTINGS.island, lang: 'en' } })); await sleep(600);
      const s = await run(`({ dir: document.querySelector('#root > div').dir, text: document.querySelector('nav').innerText })`);
      expect('', s.dir === 'ltr' && /Yobi settings/.test(s.text) && /Prayer/.test(s.text), `settings in English: ${JSON.stringify(s)}`);
      fs.writeFileSync(path.join(OUT, 'en_settings.png'), (await w.webContents.capturePage()).toPNG());
      await run(`[...document.querySelectorAll('[role=radio]')].find(b => b.textContent === 'عربي').click()`); await sleep(100);
      const sent = await run(`window.__yobi.sent.filter(m => m.t === 'settings_set')`);
      expect('', JSON.stringify(sent) === JSON.stringify([{ t: 'settings_set', section: 'island', values: { lang: 'ar' } }]), `sent ${JSON.stringify(sent)}`);
      w.destroy();
    }),
  ]);
  console.log('english rules checked');

  // voice commands (island_voice.py): Yobi ends its turn, then asks the island to open a page
  await Promise.all([
    rule('a voice command opens a page, which closes by itself', async ({ run }) => {
      await run(deliver({ t: 'state', state: 'thinking', text: 'افتح الرف' })); await run(deliver({ t: 'open', page: 'shelf' })); await sleep(100);
      expect('', !(await run(`window.__island.getState().panel.open`)), 'no page over a Yobi turn');
      await run(deliver({ t: 'end_turn' })); await run(deliver({ t: 'open', page: 'shelf' })); await sleep(300);
      const s = await run(`(() => { const p = window.__island.getState().panel; return { open: p.open, page: p.page }; })()`);
      expect('', s.open && s.page === 'shelf', `after the turn: ${JSON.stringify(s)}`);
      await sleep(10300);
      expect('', !(await run(`window.__island.getState().panel.open`)), 'the page should close after 10 s when left alone');
      await run(deliver({ t: 'open', page: 'settings' })); await sleep(100);
      expect('', (await run(`window.__yobi.settingsOpened`)) === 1, 'opening the settings window by voice');
    }),
  ]);
  console.log('voice rules checked');

  await sleep(200);
  for (const e of errors) failures.push(`window error: ${e}`);
  console.log(failures.length ? `FAILED\n${failures.join('\n')}` : 'ALL OK');
  app.exit(failures.length ? 1 : 0);
});
