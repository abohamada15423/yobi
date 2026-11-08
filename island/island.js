// Yobi island renderer. Shows what Python says; reports clicks back.
// One render() decides what the tab shows, by priority:
//   a Yobi turn  >  hud (volume, caps…)  >  track peek  >  hover panel  >  live music  >  sliver
(() => {
  // errors in this window go to Yobi's log
  window.addEventListener('error', e => window.yobi.send({ t: 'log', text: `${e.message} @${e.lineno}` }));
  const $ = id => document.getElementById(id);
  const tab = $('tab'), inner = $('inner'), statusEl = $('status'), words = $('words');
  const choices = $('choices'), dock = $('dock'), menu = $('menu'), chat = $('chat'), chatInput = $('chat-input');
  const glance = $('glance'), now = $('now'), hudEl = $('hud'), liveArt = $('live-art'), liveTime = $('live-time');
  const day = $('day'), meetingEl = $('meeting'), prayerPage = $('prayer-page'), noticeEl = $('notice');
  const shelfPage = $('shelf-page'), clipsPage = $('clips-page'), dlRow = $('dl-row'), privacyRow = $('privacy-row');
  const dots = $('dots'), face = $('face');
  const appsPage = $('apps-page'), radioPage = $('radio-page');
  const path = $('line-path'), rest = $('line-rest');
  const api = window.yobi;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');

  const ACTIVE = new Set(['listening', 'recording', 'thinking', 'executing', 'account', 'speaking']);
  const REPLY = new Set(['success', 'error', 'info', 'suggesting']);
  const MIN_W = { listening: 270, recording: 270, thinking: 270, executing: 270, account: 270, speaking: 270,
                  success: 260, error: 260, info: 260, suggesting: 320 };
  const IDLE = [96, 28], LIVE = [196, 32], MAX_W = 540, TOP = 8;   // the capsule floats TOP px under the screen edge
  const HUD_MS = 1500, PEEK_MS = 3600;

  const nf = new Intl.NumberFormat('ar-EG');
  const nf2 = new Intl.NumberFormat('ar-EG', { minimumIntegerDigits: 2 });
  const clockFmt = new Intl.DateTimeFormat('ar-EG', { hour: 'numeric', minute: '2-digit' });
  const dateFmt = new Intl.DateTimeFormat('ar-EG', { weekday: 'long', day: 'numeric', month: 'long' });
  const hijriFmt = new Intl.DateTimeFormat('ar-EG-u-ca-islamic-umalqura', { day: 'numeric', month: 'long', year: 'numeric' });
  const PRAYER = { fajr: 'الفجر', sunrise: 'الشروق', dhuhr: 'الظهر', asr: 'العصر', maghrib: 'المغرب', isha: 'العشاء' };
  const FIVE = ['fajr', 'dhuhr', 'asr', 'maghrib', 'isha'];
  const until = ms => {                                      // "بعد ١ س ٢٠ د"
    const m = Math.max(0, Math.round(ms / 60000));
    if (m < 1) return 'دلوقتي';
    const h = Math.floor(m / 60), r = m % 60;
    return 'بعد ' + (h ? `${nf.format(h)} س` + (r ? ` ${nf.format(r)} د` : '') : `${nf.format(r)} د`);
  };
  const pct = v => nf.format(Math.round(v)) + '٪';
  const mmss = s => { s = Math.max(0, Math.floor(s || 0)); return `${nf.format(Math.floor(s / 60))}:${nf2.format(s % 60)}`; };

  const ICON = {
    prev: '<path d="M6 5v14"/><path d="M19 5 9 12l10 7z" fill="currentColor"/>',
    next: '<path d="M18 5v14"/><path d="M5 5l10 7-10 7z" fill="currentColor"/>',
    play: '<path d="M7.5 4.8v14.4L19 12z" fill="currentColor" stroke="none"/>',
    pause: '<rect x="6" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none"/><rect x="14" y="4.5" width="4" height="15" rx="1" fill="currentColor" stroke="none"/>',
    volume: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/><path d="M15.5 9a4 4 0 0 1 0 6M18 6.5a7.5 7.5 0 0 1 0 11"/>',
    muted: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/><path d="m16 9.5 5 5m0-5-5 5"/>',
    brightness: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
    caps: '<path d="M12 4 4.5 12H9v4.5h6V12h4.5z"/><path d="M9 20h6"/>',
    battery: '<rect x="2.5" y="7" width="17" height="10" rx="2"/><path d="M21.5 10.5v3"/>',
    charging: '<rect x="2.5" y="7" width="17" height="10" rx="2"/><path d="M21.5 10.5v3M11.5 8.5 9 12.3h3.2L10.5 15.5"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/>',
    wifi: '<path d="M2.5 9a14 14 0 0 1 19 0M5.5 12.5a9.5 9.5 0 0 1 13 0M8.8 16a4.6 4.6 0 0 1 6.4 0"/><circle cx="12" cy="19.2" r="1" fill="currentColor"/>',
    wifioff: '<path d="M2.5 9a14 14 0 0 1 19 0M5.5 12.5a9.5 9.5 0 0 1 13 0M8.8 16a4.6 4.6 0 0 1 6.4 0"/><path d="M3 3l18 18"/>',
    mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/>',
    pen: '<path d="M4 20h4L19 9a2.1 2.1 0 0 0-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    more: '<circle cx="5.5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="18.5" cy="12" r="1.4" fill="currentColor"/>',
    grid: '<rect x="4" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6"/>',
    tray: '<path d="M3.5 13.5 6 5h12l2.5 8.5V19a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1z"/><path d="M3.5 13.5h5l1.5 2.5h4l1.5-2.5h5"/>',
    clip: '<rect x="5.5" y="4.5" width="13" height="16" rx="2"/><path d="M9 4.5V3.5h6v1M9 10h6M9 14h4"/>',
  };
  const svg = name => `<svg class="i" viewBox="0 0 24 24">${ICON[name]}</svg>`;
  for (const b of document.querySelectorAll('[data-media]')) b.innerHTML = svg(b.dataset.media === 'toggle' ? 'pause' : b.dataset.media);
  for (const b of document.querySelectorAll('[data-icon]')) b.insertAdjacentHTML('afterbegin', svg(b.dataset.icon));

  // assistant
  let state = 'idle', hideTimer = null, hideAt = 0, askId = null, typing = null, progress = -1;
  // everything else
  let open = false, hovering = false, closeDockTimer = null;
  let hud = null, hudTimer = null, peekUntil = 0, peekTimer = null;
  let media = { has: false }, mediaAt = 0, mediaKey = null, art = null, seenMedia = false;
  let stats = null, panelTicker = null;
  // your day
  let prayer = null, focus = { phase: null }, water = null, meetings = [], page = 'home';
  let notice = null, noticeTimer = null, liveTick = 0;
  // your work
  let downloads = [], shelf = [], clips = { enabled: true, items: [] }, privacy = { mic: [], cam: [] };
  let fullscreen = false, prefs = { music_tab: true, track_peek: true, reduce_motion: false };
  // batch 5
  let weather = null, offline = false, maxFront = false, saverOn = false, celebrateFrom = 0;
  let apps = { pinned: [], catalog: null }, appsEdit = false;
  let radio = { stations: [], url: '', name: '', playing: false, tries: 0 };
  const audio = new Audio(); audio.preload = 'none';
  const reducedNow = () => reduced.matches || !!prefs.reduce_motion || saverOn;
  const WX = c => c === 0 ? 'صافي' : c <= 2 ? 'غائم جزئيًا' : c === 3 ? 'غائم' : c <= 48 ? 'شبورة' : c <= 57 ? 'رذاذ'
    : c <= 67 ? 'مطر' : c <= 77 ? 'تلج' : c <= 82 ? 'زخات مطر' : c <= 86 ? 'زخات تلج' : 'عاصفة رعدية';
  const wxText = w => w ? `${nf.format(w.temp)}° ${WX(w.code)}` : '';
  function celebrate() {                      // the line's small gold flourish for a goal reached
    if (!prefs.celebrate || reducedNow()) return;
    celebrateFrom = performance.now();
    tab.classList.add('celebrating');
    setTimeout(() => tab.classList.remove('celebrating'), 1000);
    kick();
  }
  let level = 0, levelTarget = 0, levelAt = 0, music = 0, musicTarget = 0, musicAt = 0, meterShown = 0;
  let shakeFrom = 0, animating = false, lastMode = 'idle', lastPage = null, panelBox = [0, 0];

  // ---------- what the tab is showing ----------
  function mode() {
    const t = Date.now();
    if (state !== 'idle') return 'assistant';
    if (hud && t < hud.until && !open) return 'hud';
    if (notice && (notice.paused || t < notice.until)) return 'notice';
    if (t < peekUntil && !open && media.has && !media.front) return 'peek';
    if (open) return 'panel';
    if (focusActive() || musicLive() || downloads.length) return 'live';
    return 'idle';
  }
  const musicLive = () => prefs.music_tab && media.has && media.playing && !media.front;
  const fmtBytes = b => b >= 1e9 ? `${nf.format(+(b / 1e9).toFixed(1))} ج.ب` : b >= 1e6 ? `${nf.format(+(b / 1e6).toFixed(1))} م.ب` : `${nf.format(Math.round(b / 1e3))} ك.ب`;
  const focusActive = () => !!focus.phase;

  function render(fullWords) {
    const m = mode();
    tab.dataset.mode = m;
    const assistant = m === 'assistant', panel = m === 'panel';
    const pg = panel && menu.hidden ? page : null;      // the open menu takes the panel's place
    const home = pg === 'home';
    glance.hidden = !home;
    now.hidden = !((home && media.has) || m === 'peek');
    day.hidden = !home;
    meetingEl.hidden = !home || !nextMeeting();
    prayerPage.hidden = pg !== 'prayer';
    noticeEl.hidden = m !== 'notice';
    tab.dataset.notice = m === 'notice' ? notice.kind : '';
    hudEl.hidden = m !== 'hud';
    shelfPage.hidden = pg !== 'shelf';
    appsPage.hidden = pg !== 'apps';
    radioPage.hidden = pg !== 'radio';
    clipsPage.hidden = pg !== 'clips';
    $('history-page').hidden = pg !== 'history';
    for (const b of document.querySelectorAll('[data-page]')) b.setAttribute('aria-pressed', String(panel && page === b.dataset.page));
    dlRow.hidden = !home || !downloads.length;
    if (!dlRow.hidden) drawDownloads();
    const who = [privacy.mic.length ? `المايك: ${privacy.mic.join('، ')}` : '', privacy.cam.length ? `الكاميرا: ${privacy.cam.join('، ')}` : ''].filter(Boolean);
    privacyRow.hidden = !home || !who.length;
    if (offline) who.push('النت مقطوع');
    privacyRow.hidden = !home || !who.length;
    privacyRow.textContent = who.join(' — ');
    $('wx').hidden = !(prefs.weather !== false && weather);
    $('wx').textContent = wxText(weather);
    if (weather) $('wx').title = `العظمى ${nf.format(weather.hi)}° والصغرى ${nf.format(weather.lo)}°`;
    tab.classList.toggle('thin', maxFront && m === 'idle' && dots.hidden);
    const clocked = m === 'idle' && prefs.idle_clock !== false && !tab.classList.contains('thin');
    tab.classList.toggle('clocked', clocked);
    $('idle-clock').hidden = !clocked;
    if (clocked) $('idle-clock').textContent = clockFmt.format(new Date());
    // the live tab shows one thing: focus, then music, then a download
    const focusLive = m === 'live' && focusActive();
    const dlLive = m === 'live' && !focusLive && !musicLive() && downloads.length > 0;
    tab.classList.toggle('focus-live', focusLive);
    tab.classList.toggle('dl-live', dlLive);
    tab.classList.toggle('on-break', focusLive && focus.phase !== 'focus');
    liveArt.hidden = !(m === 'live' && art && !focusLive && !dlLive);
    liveTime.hidden = !(focusLive || dlLive);
    if (focusLive) liveTime.textContent = mmss(focusLeft());
    else if (dlLive) liveTime.textContent = `⬇ ${fmtBytes(downloads[0].speed)}/ث`;
    // privacy dots stay visible whatever the island shows
    $('dot-mic').hidden = !privacy.mic.length; $('dot-cam').hidden = !privacy.cam.length;
    dots.hidden = !(privacy.mic.length || privacy.cam.length);
    dots.title = who.join('\n');
    tab.classList.toggle('has-dots', !dots.hidden);
    // a fullscreen game or video: only a Yobi turn and the adhan / a meeting get through
    const fsHide = fullscreen && !(m === 'assistant' || (m === 'notice' && ['adhan', 'meeting'].includes(notice.kind)));
    tab.classList.toggle('fs-hidden', fsHide);
    // Yobi's face: on Yobi's own turns and the notices Yobi tells you, not on utility ones
    const look = faceLook(m);
    tab.classList.toggle('has-face', !!look);
    if (look) face.dataset.look = look;
    statusEl.hidden = !(assistant || (panel && !chat.hidden));
    words.hidden = !assistant;
    choices.hidden = !assistant || !choices.children.length;
    dock.hidden = !panel || !chat.hidden;
    if (!panel) { menu.hidden = true; }
    tab.classList.toggle('open', panel);
    tab.classList.toggle('has-art', !!art);
    now.classList.toggle('no-art', !art);
    tab.classList.toggle('muted', m === 'hud' && !!hud?.muted);
    if (panel && m !== lastMode) { drawStats(); drawMedia(); drawClock(); drawDay(); }
    if (pg === 'prayer') drawPrayerPage();
    if (m !== lastMode) api.send({ t: 'panel', open: panel });
    if (panel) startPanelTicker(); else stopPanelTicker();
    document.documentElement.classList.toggle('still', reducedNow());
    // a new page slides in from the side you're going to (RTL: forward comes from the left)
    if (pg && lastMode === 'panel' && pg !== lastPage) {
      const back = pg === 'home' || (lastPage === 'radio' && pg === 'prayer');
      animateIn([...inner.children].filter(el => !el.hidden && el !== dock && el !== menu), back ? 'enter-back' : 'enter-fwd');
    }
    lastPage = pg;
    lastMode = m;
    fit(m, fullWords);
    kick();
  }
  const FACE_STATE = { listening: 'listening', recording: 'listening', speaking: 'listening', thinking: 'thinking',
    executing: 'thinking', account: 'thinking', success: 'happy', error: 'sad', info: 'neutral', suggesting: 'question' };
  const FACE_NOTICE = { adhan: 'calm', prayer_soon: 'neutral', focus_done: 'happy', break_done: 'question',
    download_done: 'happy', brief: 'happy', welcome: 'happy', care: 'neutral', meeting: 'neutral' };
  function faceLook(m) {
    if (m === 'assistant') return FACE_STATE[state] || 'neutral';
    if (m === 'notice' && notice) return FACE_NOTICE[notice.kind] || null;
    return null;
  }
  // a blink every few seconds while the face is showing
  (function blinkLater() {
    setTimeout(() => {
      if (tab.classList.contains('has-face') && !reducedNow() && ['neutral', 'listening', 'question'].includes(face.dataset.look)) {
        face.classList.add('blink');
        setTimeout(() => face.classList.remove('blink'), 140);
      }
      blinkLater();
    }, 3200 + Math.random() * 3000);
  })();
  // ---------- history: what Yobi said and showed, newest first ----------
  const history = [];
  const HIST_LABEL = { success: 'تم', error: 'مشكلة', info: 'يوبي', suggesting: 'سؤال' };
  function remember(kind, text, label) {
    text = String(text || '').trim();
    if (!text) return;
    history.unshift({ at: Date.now(), kind, text, label: label || HIST_LABEL[kind] || '' });
    history.length = Math.min(history.length, 40);
    drawHistory();
  }
  function drawHistory() {
    $('history-empty').hidden = history.length > 0;
    $('history-clear').hidden = !history.length;
    $('history-list').replaceChildren(...history.map(h => {
      const li = document.createElement('li'); li.className = h.kind;
      const time = document.createElement('time'); time.textContent = clockFmt.format(new Date(h.at));
      const k = document.createElement('span'); k.className = 'k'; k.textContent = h.label;
      const x = document.createElement('span'); x.className = 'x'; x.dir = 'auto'; x.textContent = h.text;
      li.append(time, k, x); return li;
    }));
    if (open && page === 'history') fit('panel');
  }
  function animateIn(els, cls) {
    if (reducedNow()) return;
    for (const el of els) {
      el.classList.remove('enter-fwd', 'enter-back', 'enter-drop');
      void el.offsetWidth;                       // restart the animation
      el.classList.add(cls);
      el.addEventListener('animationend', () => el.classList.remove(cls), { once: true });
    }
  }

  // ---------- sizing ----------
  function reportRect(w, h) {                   // where the tab is, so the window can catch hover and drops
    if (tab.classList.contains('fs-hidden')) { api.rect({ x: -9999, y: -9999, w: 0, h: 0 }); return; }
    api.rect({ x: Math.round((innerWidth - w) / 2), y: 0, w, h: Math.max(h, 16) + TOP });   // the gap above counts too
  }
  function fit(m, fullWords) {
    if (m === 'idle' || m === 'live') {
      const [w, h] = m === 'idle' ? (tab.classList.contains('thin') ? [64, 6] : tab.classList.contains('clocked') ? [116, 30] : IDLE)
        : tab.classList.contains('dl-live') ? [236, LIVE[1]] : LIVE;
      tab.style.borderRadius = h / 2 + 'px';
      tab.classList.remove('has-content');
      tab.classList.toggle('closing', m === 'idle');
      tab.style.width = w + 'px'; tab.style.height = h + 'px';
      panelBox = [0, 0];
      reportRect(w, h);
      return;
    }
    tab.classList.remove('closing');
    tab.classList.add('has-content');
    const shown = words.textContent;
    if (fullWords !== undefined) words.textContent = fullWords;   // size for the finished text, then type into it
    inner.style.width = 'max-content';
    inner.style.minHeight = '';
    inner.style.maxWidth = MAX_W + 'px';
    inner.style.minWidth = (m === 'assistant' ? (MIN_W[state] || 260) : m === 'panel' ? 300 : 0) + 'px';
    const w = Math.ceil(inner.getBoundingClientRect().width) + 2;
    inner.style.width = w + 'px';
    const h = Math.ceil(inner.offsetHeight);   // after fixing the width: text and buttons may rewrap
    if (fullWords !== undefined) words.textContent = shown;
    let tw = w, th = Math.min(h, 340);
    if (m === 'panel') { tw = Math.max(tw, panelBox[0]); th = Math.max(th, panelBox[1]); panelBox = [tw, th]; inner.style.width = tw + 'px'; inner.style.minHeight = th + 'px'; }
    else { panelBox = [0, 0]; inner.style.minHeight = ''; }
    tab.style.width = tw + 'px';
    tab.style.height = th + 'px';
    tab.style.borderRadius = Math.min(th / 2, 34) + 'px';      // a pill when short, a rounded card when tall
    reportRect(tw, th);
  }

  // ---------- assistant: visibility & timers ----------
  function report() { api.send({ t: 'view', state, reply: replyVisible() }); }
  function replyVisible() { return !!typing || (REPLY.has(state) && hideTimer !== null); }
  function clearHide() { clearTimeout(hideTimer); hideTimer = null; hideAt = 0; }
  function scheduleHide(ms) {
    clearHide();
    hideAt = Date.now() + ms;
    hideTimer = setTimeout(() => { hideTimer = null; if (hovering) { scheduleHide(1500); return; } hide(); }, ms);
  }
  function readingTime(text, st) {
    const n = String(text || '').length;
    if (st === 'success') return 3800 + Math.min(4000, n * 25);
    if (st === 'error') return 4500 + Math.min(4000, n * 25);
    return Math.min(10000, Math.max(4000, n * 45));
  }
  function hide() {
    clearHide(); stopTyping();
    state = 'idle'; askId = null; progress = -1;
    tab.dataset.state = 'idle';
    statusEl.textContent = ''; words.textContent = '';
    choices.replaceChildren();
    removeProgress();
    if (!hovering) { open = false; closeChat(true); }
    render(); report();
  }

  function enterTurn() {
    // a Yobi turn takes the island: drop notices and the hover panel
    hud = null; peekUntil = 0; open = false; menu.hidden = true; closeChat(true);
  }

  function setState(st, text = '') {
    stopTyping();
    const prev = state;
    state = st; tab.dataset.state = st;
    enterTurn();
    if (st !== 'suggesting') { choices.replaceChildren(); askId = null; }
    if (ACTIVE.has(st)) {
      statusEl.textContent = text; words.textContent = '';
      clearHide(); scheduleHide(60000);           // safety net if a turn never ends
    } else if (REPLY.has(st)) {
      statusEl.textContent = ''; words.textContent = text;
      scheduleHide(readingTime(text, st));
      if (text && text !== '▍') remember(st, text);
    }
    if (st === 'error' && prev !== 'error') shakeFrom = performance.now();
    if (st !== 'executing') removeProgress();
    render(); report();
  }

  function say(text, st = 'info', chime = true) {
    text = String(text || '');
    if (!text) return;
    if (!REPLY.has(st)) st = 'info';
    const current = typing ? typing.full : words.textContent;
    // Streaming: the brain sends a longer version of the same reply; keep typing on.
    if (current && text.startsWith(current) && state === st && (typing || replyVisible())) {
      if (typing) typing.full = text; else startTyping(text, current.length);
      if (history[0] && text.startsWith(history[0].text)) { history[0].text = text; drawHistory(); }
      render(text); clearHide();
      return;
    }
    remember(st, text);
    stopTyping();
    state = st; tab.dataset.state = st;
    enterTurn();
    choices.replaceChildren(); askId = null;
    statusEl.textContent = ''; words.textContent = '';
    if (chime) tone(st === 'error' ? 330 : 520);
    if (st === 'error') shakeFrom = performance.now();
    render(text);
    startTyping(text, 0);
    clearHide(); report();
  }

  function startTyping(full, from) {
    if (reducedNow()) { words.textContent = full; finishTyping(full); return; }
    typing = { full, chars: from, last: performance.now() };
    words.classList.add('typing');
    const step = t => {
      if (!typing) return;
      const rate = Math.max(30, typing.full.length / 3.5);           // chars per second
      typing.chars = Math.min(typing.full.length, typing.chars + (t - typing.last) / 1000 * rate);
      typing.last = t;
      words.textContent = typing.full.slice(0, Math.floor(typing.chars));
      if (typing.chars >= typing.full.length) { const f = typing.full; typing = null; finishTyping(f); return; }
      requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  function finishTyping(full) {
    words.classList.remove('typing');
    words.textContent = full;
    scheduleHide(readingTime(full, state));
    report();
  }
  function stopTyping() {
    if (typing) { words.textContent = typing.full; typing = null; }
    words.classList.remove('typing');
  }

  function ask(id, text, options, timeout, chime) {
    setState('suggesting', text);
    askId = id;
    choices.replaceChildren();
    (options || []).forEach(([label, value], i) => {
      const b = document.createElement('button');
      b.type = 'button'; b.textContent = label; b.dir = 'auto';
      if (i > 0 && /^(no|none|cancel)$/i.test(String(value))) b.className = 'decline';
      b.onclick = () => {
        if (askId !== id) return;
        for (const c of choices.children) c.disabled = true;
        askId = null;
        api.send({ t: 'answer', id, value });
        choices.replaceChildren(); render();
        scheduleHide(1800);
      };
      choices.append(b);
    });
    if (chime) tone(660, 880);
    render(); scheduleHide(timeout || 30000);
  }

  // ---------- progress (executing) ----------
  function setProgress(v) {
    progress = v;
    if (v < 0 || state !== 'executing') { removeProgress(); return; }
    let bar = inner.querySelector('.progress');
    if (!bar) { bar = document.createElement('div'); bar.className = 'progress'; bar.append(document.createElement('span')); inner.append(bar); render(); }
    bar.firstChild.style.width = v > 1 ? '0' : Math.round(v * 100) + '%';
  }
  function removeProgress() { inner.querySelector('.progress')?.remove(); }

  // ---------- hud: volume, brightness, caps lock, keyboard, battery ----------
  function showHud(m) {
    if (state !== 'idle' || open) return;            // never over a Yobi turn or the open panel
    const icon = $('hud-icon'), label = $('hud-label'), value = $('hud-value');
    let meterValue = null;
    if (m.kind === 'volume') {
      icon.innerHTML = svg(m.muted || m.value === 0 ? 'muted' : 'volume');
      label.textContent = 'الصوت';
      value.textContent = m.muted ? 'مكتوم' : pct(m.value);
      meterValue = m.muted ? 0 : m.value / 100;
    } else if (m.kind === 'brightness') {
      icon.innerHTML = svg('brightness'); label.textContent = 'الإضاءة'; value.textContent = pct(m.value);
      meterValue = m.value / 100;
    } else if (m.kind === 'caps') {
      icon.innerHTML = svg('caps'); label.textContent = 'Caps Lock'; value.textContent = m.on ? 'شغال' : 'مقفول';
    } else if (m.kind === 'kbd') {
      icon.innerHTML = `<span class="badge">${escapeHtml(m.badge || '⌨')}</span>`;
      label.textContent = 'لغة الكيبورد'; value.textContent = m.name || '';
    } else if (m.kind === 'battery') {
      icon.innerHTML = svg(m.plugged ? 'charging' : 'battery');
      label.textContent = m.low ? 'البطارية قربت تخلص' : m.plugged ? 'بيشحن' : 'على البطارية';
      value.textContent = pct(m.value);
      meterValue = m.value / 100;
    } else if (m.kind === 'net') {
      icon.innerHTML = svg(m.online ? 'wifi' : 'wifioff');
      label.textContent = m.online ? 'النت رجع' : 'النت فصل';
      value.textContent = m.online && m.gone_s >= 60 ? `بعد ${until(m.gone_s * 1000).replace('بعد ', '')}` : '';
      tab.classList.toggle('muted', !m.online);
    } else return;
    const fresh = !hud || hud.kind !== m.kind || Date.now() > hud.until;
    hud = { ...m, meter: meterValue, until: Date.now() + (m.low ? 5000 : HUD_MS) };
    if (fresh && meterValue !== null) meterShown = meterValue;
    clearTimeout(hudTimer);
    hudTimer = setTimeout(render, hud.until - Date.now() + 20);
    render();
  }
  function escapeHtml(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]); }

  // ---------- media ----------
  function onMedia(m) {
    const prevKey = mediaKey;
    if ('art' in m) { art = m.art || null; $('art').src = art || ''; liveArt.src = art || ''; }
    media = { ...media, ...m };
    if (!m.has) media = { has: false };
    mediaAt = performance.now();
    mediaKey = m.has ? `${m.app}|${m.title}|${m.artist}` : null;
    // a new song while you're not looking at the player: peek
    if (prefs.track_peek && seenMedia && mediaKey && prevKey !== mediaKey && media.playing && !media.front && state === 'idle' && !open) {
      peekUntil = Date.now() + PEEK_MS;
      clearTimeout(peekTimer); peekTimer = setTimeout(render, PEEK_MS + 20);
    }
    seenMedia = true;
    drawMedia();
    render();
  }
  function mediaPos() {
    let p = media.pos || 0;
    if (media.playing) p += (performance.now() - mediaAt) / 1000;
    return media.dur ? Math.min(p, media.dur) : p;
  }
  function drawMedia() {
    if (!media.has) return;
    $('m-title').textContent = media.title || 'من غير اسم';
    $('m-artist').textContent = [media.artist, media.app].filter(Boolean).join(' – ');
    $('art').hidden = !art;
    const t = $('m-toggle');
    t.innerHTML = svg(media.playing ? 'pause' : 'play');
    t.setAttribute('aria-label', media.playing ? 'وقّف' : 'شغّل');
    $('m-timeline').hidden = !(media.dur > 0);
    drawTimeline();
  }
  function drawTimeline() {
    if (!media.has || !(media.dur > 0)) return;
    const p = mediaPos();
    $('m-pos').textContent = mmss(p); $('m-dur').textContent = mmss(media.dur);
    $('m-fill').style.width = (p / media.dur * 100).toFixed(2) + '%';
    $('m-bar').setAttribute('aria-valuenow', String(Math.round(p / media.dur * 100)));
  }
  function mediaCmd(cmd, pos) {
    api.send({ t: 'media', cmd, pos });
    if (cmd === 'toggle') { media.pos = mediaPos(); mediaAt = performance.now(); media.playing = !media.playing; drawMedia(); }
    if (cmd === 'seek') { media.pos = pos; mediaAt = performance.now(); drawTimeline(); }
  }
  for (const b of document.querySelectorAll('[data-media]')) b.onclick = () => mediaCmd(b.dataset.media);
  $('m-bar').addEventListener('click', e => {
    if (!media.seek) return;
    const r = e.currentTarget.getBoundingClientRect();
    mediaCmd('seek', Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * media.dur);
  });
  $('m-bar').addEventListener('keydown', e => {
    if (!media.seek || !['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
    e.preventDefault();
    mediaCmd('seek', Math.max(0, Math.min(media.dur, mediaPos() + (e.key === 'ArrowRight' ? 10 : -10))));
  });

  // ---------- glance: clock and machine ----------
  function drawClock() {
    const d = new Date();
    $('clock-time').textContent = clockFmt.format(d);
    $('clock-date').textContent = dateFmt.format(d);
    $('clock-hijri').textContent = hijriFmt.format(d);
  }

  // ---------- your day: prayer, focus, water, meetings ----------
  function nextPrayer() {
    if (!prayer) return null;
    const t = Date.now(), times = prayer.times;
    for (let i = 0; i < FIVE.length; i++) {
      if (times[FIVE[i]] > t) return { key: FIVE[i], at: times[FIVE[i]], from: i ? times[FIVE[i - 1]] : times.isha - 864e5 };
    }
    return { key: 'fajr', at: times.next_fajr, from: times.isha };
  }
  function focusLeft() {
    if (!focus.phase) return 0;
    return focus.ends_at ? Math.max(0, (focus.ends_at - Date.now()) / 1000) : (focus.paused_left || 0);
  }
  function nextMeeting() {
    const t = Date.now();
    return meetings.find(e => e.end > t && e.start - t < 3 * 3600e3) || null;
  }
  function setActs(el, items) {
    const key = items.map(i => i[0]).join();
    if (el.dataset.key === key) return;
    el.dataset.key = key;
    el.replaceChildren(...items.map(([cmd, icon, label]) => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'mini'; b.innerHTML = svg(icon);
      b.setAttribute('aria-label', label); b.title = label;
      b.onclick = () => api.send({ t: 'focus', cmd });
      return b;
    }));
  }
  function drawDay() {
    const np = nextPrayer();
    if (np) {
      $('pr-name').textContent = PRAYER[np.key];
      $('pr-in').textContent = until(np.at - Date.now());
      meterTo('pr-fill', (Date.now() - np.from) / (np.at - np.from));
    }
    if (focus.phase) {
      const label = focus.phase === 'focus' ? `تركيز ${nf.format((focus.round || 0) + 1)}` : focus.phase === 'long' ? 'راحة طويلة' : 'راحة';
      $('fc-name').textContent = label;
      $('fc-val').textContent = mmss(focusLeft());
      meterTo('fc-fill', focus.total ? focusLeft() / focus.total : 0);
      setActs($('fc-acts'), [focus.ends_at ? ['pause', 'pause', 'وقّف مؤقتًا'] : ['resume', 'play', 'كمّل'], ['stop', 'stop', 'إنهاء الجلسة']]);
    } else {
      $('fc-name').textContent = 'تركيز';
      $('fc-val').textContent = `${nf.format(focus.focus_min || 25)} د`;
      meterTo('fc-fill', 0);
      setActs($('fc-acts'), [['start', 'play', 'ابدأ جلسة تركيز']]);
    }
    $('slot-water').hidden = !water;
    if (water) {
      $('wt-val').textContent = `${nf.format(water.count)} من ${nf.format(water.goal)}`;
      meterTo('wt-fill', water.goal ? water.count / water.goal : 0);
    }
    const mt = nextMeeting();
    if (mt) {
      const soon = mt.start - Date.now();
      $('mt-text').textContent = soon > 0 ? `${mt.title} — ${clockFmt.format(new Date(mt.start))} (${until(soon)})` : `${mt.title} — شغال دلوقتي`;
      $('mt-join').hidden = !(mt.has_link && soon < 15 * 60e3);
      $('mt-join').onclick = () => api.send({ t: 'meeting_join', id: mt.id });
    }
  }
  function drawPrayerPage() {
    if (!prayer) return;
    $('pp-city').textContent = prayer.city || '';
    const np = nextPrayer(), t = Date.now();
    const rows = ['fajr', 'sunrise', 'dhuhr', 'asr', 'maghrib', 'isha'].map(k => {
      const li = document.createElement('li');
      const at = prayer.times[k];
      if (np && np.key === k && np.at === at) li.className = 'next';
      else if (at < t) li.className = 'past';
      li.innerHTML = `<span class="n">${PRAYER[k]}</span><span class="v">${clockFmt.format(new Date(at))}</span>`;
      if (li.className === 'next') { const s = document.createElement('span'); s.className = 'in'; s.textContent = until(at - t); li.append(s); }
      return li;
    });
    $('pp-list').replaceChildren(...rows);
  }
  $('slot-prayer').onclick = () => { page = 'prayer'; render(); };
  $('pp-back').onclick = () => { page = 'home'; render(); };
  $('wt-add').onclick = () => { if (water) { water.count += 1; drawDay(); } api.send({ t: 'water', cmd: 'add' }); };

  // ---------- notices ----------
  function showNotice(n) {
    const busy = state !== 'idle' || (n.kind === 'reminder' && (open || (notice && mode() === 'notice')));
    if (busy) {                                                // a Yobi turn keeps the island; gentle ones wait
      if (n.kind === 'reminder') api.send({ t: 'notice_dropped', kind: 'reminder' });
      return;
    }
    const at = n.at ? clockFmt.format(new Date(n.at)) : '';
    let kind = '', text = '', sub = '', buttons = [], ms = 8000, tones = [520], swatch = '';
    if (n.kind === 'adhan' && radio.playing && prefs.radio_pause_prayer !== false) radioStop('وقفت الإذاعة عشان الأذان');
    if (n.kind === 'focus_done') setTimeout(celebrate, 60);
    if (n.kind === 'adhan') {
      kind = 'الصلاة'; text = `حان الآن موعد صلاة ${PRAYER[n.prayer] || ''}`; sub = at + (prayer?.city ? ` · ${prayer.city}` : '');
      ms = 15000; tones = [523, 659];
    } else if (n.kind === 'prayer_soon') {
      text = `${PRAYER[n.prayer] || ''} بعد ${nf.format(n.minutes)} دقايق`; sub = at; ms = 6000;
    } else if (n.kind === 'focus_done') {
      kind = 'تركيز'; text = `خلصت جلسة التركيز ${nf.format(n.round)} 👏`; sub = `الراحة بدأت: ${nf.format(n.next_min)} دقايق`;
      ms = 8000; tones = [659, 784];
    } else if (n.kind === 'break_done') {
      kind = 'تركيز'; text = 'الراحة خلصت'; sub = 'نرجع نركّز؟';
      buttons = [[`ابدأ ${nf.format(n.focus_min)} د`, 'focus_start'], ['مش دلوقتي', 'dismiss']]; ms = 30000;
    } else if (n.kind === 'reminder') {
      kind = { dhikr: 'ذكر', dua: 'دعاء', ayah: 'آية' }[n.sub] || '';
      text = n.sub === 'ayah' ? `﴿ ${n.text} ﴾` : n.text; sub = n.ref || '';
      ms = (n.seconds || 20) * 1000; tones = [];
    } else if (n.kind === 'meeting') {
      kind = 'اجتماع'; text = n.title; sub = `الساعة ${at} — بعد ٥ دقايق`;
      buttons = n.has_link ? [['انضم', 'join'], ['تمام', 'dismiss']] : [['تمام', 'dismiss']]; ms = 60000;
    } else if (n.kind === 'download_done') {
      kind = 'اتحمّل'; text = n.name; sub = n.size ? fmtBytes(n.size) : '';
      buttons = [['افتح', 'dl_open'], ['وريني مكانه', 'dl_folder'], ['تمام', 'dismiss']]; ms = 9000; tones = [587, 784];
      setTimeout(celebrate, 60);
    } else if (n.kind === 'smart') {
      tones = []; ms = 6000;
      if (n.what === 'link') {
        kind = 'لينك اتنسخ'; text = n.value.length > 60 ? n.value.slice(0, 57) + '…' : n.value;
        buttons = [['افتحه', 'open_link'], ['تمام', 'dismiss']];
      } else if (n.what === 'color') {
        kind = 'لون اتنسخ'; text = n.value; swatch = n.value;
      } else if (n.what === 'math') {
        kind = 'حسبتها'; text = `= ${nf.format(Number(n.result))}`; sub = n.value;
        buttons = [['انسخ الناتج', 'copy_result'], ['تمام', 'dismiss']];
      } else if (n.what === 'count') {
        kind = 'نص طويل'; text = `${nf.format(n.words)} كلمة`; sub = `${nf.format(n.chars)} حرف`;
      } else return;
    } else if (n.kind === 'brief') {
      kind = hijriFmt.format(new Date()); text = n.greet;
      const lines = [];
      if (n.weather) lines.push(`الجو ${wxText(n.weather)}، والعظمى ${nf.format(n.weather.hi)}°`);
      if (n.next) lines.push(`${PRAYER[n.next.prayer]} الساعة ${clockFmt.format(new Date(n.next.at))}`);
      if (n.meetings) lines.push(n.meetings === 1 ? `عندك اجتماع النهارده: ${n.first_meeting.title} ${clockFmt.format(new Date(n.first_meeting.start))}` : `عندك ${nf.format(n.meetings)} اجتماعات النهارده، أولهم ${clockFmt.format(new Date(n.first_meeting.start))}`);
      sub = lines.join('\n'); ms = 14000; tones = [523, 659];
    } else if (n.kind === 'welcome') {
      text = 'أهلا رجعت 👋'; kind = `غبت ${until(n.away_min * 60000).replace('بعد ', '')}`;
      sub = (n.events || []).join('\n'); ms = 10000; tones = [523];
    } else if (n.kind === 'care') {
      kind = 'خد بريك'; text = n.title; sub = n.text; buttons = [['تمام', 'dismiss']]; ms = 15000; tones = [];
    } else if (n.kind === 'screenshot') {
      kind = n.h > n.w ? 'صورة اتنسخت' : 'لقطة شاشة'; text = ''; sub = `${nf.format(n.w)}×${nf.format(n.h)}`;
      buttons = [['احفظ على الرف', 'shot_save'], ['تمام', 'dismiss']]; ms = 7000; tones = [];
    } else return;
    $('nt-kind').textContent = kind; $('nt-text').textContent = text; $('nt-sub').textContent = sub;
    $('nt-text').classList.toggle('ayah', n.kind === 'reminder' && n.sub === 'ayah');   // the Mushaf typeface
    $('nt-img').hidden = !n.thumb; if (n.thumb) $('nt-img').src = n.thumb;
    $('nt-swatch').hidden = !swatch; $('nt-swatch').style.background = swatch || '';
    const box = $('nt-buttons');
    box.replaceChildren(...buttons.map(([label, action]) => {
      const b = document.createElement('button'); b.type = 'button'; b.textContent = label;
      if (action === 'dismiss') b.className = 'decline';
      b.onclick = () => {
        if (action === 'join') api.send({ t: 'meeting_join', id: n.id });
        else if (action === 'dl_open' || action === 'dl_folder') api.send({ t: action, id: n.id });
        else if (action === 'open_link' || action === 'copy_result') api.send({ t: 'smart_action', action, value: action === 'open_link' ? n.value : n.result });
        else if (action !== 'dismiss') api.send({ t: 'notice_action', action });
        endNotice();
      };
      return b;
    }));
    box.hidden = !buttons.length;
    const replacing = !!notice && mode() === 'notice';
    // the history keeps what Yobi told you, not reminders or what you copied
    if (!['reminder', 'smart', 'screenshot'].includes(n.kind)) remember('notice', [text, sub.split('\n')[0]].filter(Boolean).join(' — '), kind);
    notice = { ...n, kind: n.kind, total: ms, until: Date.now() + ms, paused: false };
    if (tones.length) tone(tones[0], tones[1]);
    scheduleNoticeEnd();
    render();
    if (replacing) animateIn([noticeEl], 'enter-drop');   // a notice replacing another drops in
  }
  function scheduleNoticeEnd() {
    clearTimeout(noticeTimer);
    if (!notice || notice.paused) return;
    noticeTimer = setTimeout(endNotice, Math.max(0, notice.until - Date.now()) + 20);
  }
  function endNotice() { clearTimeout(noticeTimer); notice = null; render(); }
  function holdNotice(on) {                                    // hovering keeps a notice readable
    if (!notice) return;
    if (on && !notice.paused) { notice.paused = true; notice.left = notice.until - Date.now(); clearTimeout(noticeTimer); }
    else if (!on && notice.paused) { notice.paused = false; notice.until = Date.now() + Math.max(1500, notice.left); scheduleNoticeEnd(); }
  }
  function meterTo(id, v) {
    const b = $(id);
    b.style.width = Math.round(Math.max(0, Math.min(1, v)) * 100) + '%';
    b.classList.toggle('warm', v >= 0.7 && v < 0.9);
    b.classList.toggle('hot', v >= 0.9);
  }
  function drawStats() {
    if (!stats) return;
    meterTo('cpu-fill', stats.cpu); $('cpu-val').textContent = pct(stats.cpu * 100);
    meterTo('ram-fill', stats.ram); $('ram-val').textContent = pct(stats.ram * 100);
    $('ram-val').title = `${(stats.ram_used / 2 ** 30).toFixed(1)} / ${(stats.ram_total / 2 ** 30).toFixed(1)} GB`;
    const bat = stats.battery;
    $('bat-stat').hidden = !bat;
    if (bat) { meterTo('bat-fill', bat.percent / 100); $('bat-fill').classList.toggle('hot', bat.percent <= 20 && !bat.plugged); $('bat-val').textContent = pct(bat.percent) + (bat.plugged ? ' ⚡' : ''); }
  }
  function startPanelTicker() {
    if (panelTicker) return;
    panelTicker = setInterval(() => {
      drawClock(); if (media.playing) drawTimeline(); drawDay();
      if (page === 'prayer') drawPrayerPage();
    }, 500);
  }
  function stopPanelTicker() { clearInterval(panelTicker); panelTicker = null; }

  // ---------- the line ----------
  const N = 56, VW = 520, MID = 12;
  function flat(x0 = 0, x1 = VW) { return `M${x0.toFixed(1)} ${MID} L${x1.toFixed(1)} ${MID}`; }
  function rtl() { const t = statusEl.textContent + words.textContent; return /[؀-ۿ]/.test(t) || !t; }
  function drawMeter(f) {                     // the line as a meter; RTL: it fills from the right
    f = Math.max(0, Math.min(1, f));
    const x = VW * (1 - f);
    path.setAttribute('d', f > 0.004 ? flat(x, VW) : '');
    rest.setAttribute('d', flat(0, x));
  }
  function frame(t0, once) {
    const t = t0 / 1000, m = tab.dataset.mode;
    const shake = Math.max(0, 1 - (t0 - shakeFrom) / 520);
    let ys = null, busy = false, meter = false, loop = true;
    rest.setAttribute('d', '');
    if (m === 'hud' && hud && hud.meter !== null && hud.meter !== undefined) {
      meter = true;
      meterShown += (hud.meter - meterShown) * 0.3;
      drawMeter(meterShown);
      busy = Math.abs(hud.meter - meterShown) > 0.002;
    } else if (m === 'notice' && notice && notice.kind === 'reminder') {
      meter = true;                             // the reminder's time left drains along the line
      drawMeter((notice.paused ? notice.left : notice.until - Date.now()) / notice.total);
      busy = !notice.paused;
    } else if (t0 - celebrateFrom < 900 && state === 'idle') {
      const p = (t0 - celebrateFrom) / 900, c = rtl() ? 1 - p : p;   // one gold crest runs along the line
      ys = i => { const x = i / (N - 1), d = (x - c) / 0.12; return MID - 8 * (1 - p) * Math.exp(-d * d) * Math.cos((x - c) * 30); };
    } else if (m === 'live' && tab.classList.contains('dl-live')) {
      const p = (t % 2.4) / 2.4, c = rtl() ? 1 - p : p;              // a download: a slow pulse, size unknown
      ys = i => { const d = (i / (N - 1) - c) / 0.1; return MID - 4 * Math.exp(-d * d); };
    } else if (m === 'live' && focusActive()) {
      meter = true;                             // redrawn once a second by the focus ticker
      drawMeter(focus.total ? focusLeft() / focus.total : 0);
      liveTime.textContent = mmss(focusLeft());
    } else if (state === 'listening' || state === 'recording') {
      if (t0 - levelAt > 900) levelTarget = 0.18 + 0.12 * Math.sin(t * 2.1);   // no mic data: breathe gently
      level += (levelTarget - level) * 0.22;
      const a = 2 + level * 9;
      ys = i => { const x = i / (N - 1), env = Math.sin(Math.PI * x); return MID + env * (a * 0.65 * Math.sin(x * 19 + t * 7.5) + a * 0.35 * Math.sin(x * 41 - t * 11)); };
    } else if (ACTIVE.has(state)) {
      const p = (t % 1.5) / 1.5, c = rtl() ? 1 - p : p;
      ys = i => { const d = (i / (N - 1) - c) / 0.085; return MID - 7 * Math.exp(-d * d); };
    } else if (shake > 0) {
      ys = i => { const x = i / (N - 1); return MID + 6 * shake * Math.sin(Math.PI * x) * Math.sin(x * 26 + t * 34); };
    } else if (typing && tab.classList.contains('has-face')) {
      ys = i => { const x = i / (N - 1); return MID + Math.sin(Math.PI * x) * 2.2 * Math.sin(t * 14) * Math.sin(x * 9); };   // talking
    } else if (tab.classList.contains('has-face') && ['happy', 'sad'].includes(face.dataset.look)) {
      const k = face.dataset.look === 'happy' ? 4.5 : -3.5;          // a smile, or a frown: only under the eyes
      ys = i => { const d = (i / (N - 1) - 0.5) / 0.075; return MID + k * Math.exp(-d * d); };
      loop = false;
    } else if (m === 'live') {
      if (t0 - musicAt > 1500) musicTarget = 0;
      music += (musicTarget - music) * 0.18;
      const a = 0.6 + music * 4.2;
      ys = i => { const x = i / (N - 1), env = Math.sin(Math.PI * x); return MID + env * a * Math.sin(x * 14 - t * 5); };
    }
    if (ys && (!once || !loop)) {                 // still shapes (smile, frown) draw even when motion is off
      let d = '';
      for (let i = 0; i < N; i++) d += (i ? ' L' : 'M') + (i / (N - 1) * VW).toFixed(1) + ' ' + ys(i).toFixed(2);
      path.setAttribute('d', d);
      busy = loop;
    } else if (!meter) {
      path.setAttribute('d', flat());
    }
    if (busy && !once) requestAnimationFrame(t1 => frame(t1)); else animating = false;
  }
  function kick() {
    if (reducedNow()) {                         // still: meters show their value, waves stay flat
      if (hud && hud.meter != null) meterShown = hud.meter;
      frame(performance.now(), true);
      return;
    }
    if (!animating) { animating = true; requestAnimationFrame(t1 => frame(t1)); }
  }
  setInterval(() => { if (tab.dataset.mode === 'live' && focusActive()) kick(); }, 1000);
  setInterval(() => { if (tab.classList.contains('clocked')) $('idle-clock').textContent = clockFmt.format(new Date()); }, 10000);

  // ---------- sound ----------
  let ctx = null;
  function tone(f1, f2) {
    try {
      ctx = ctx || new AudioContext();
      const o = ctx.createOscillator(), g = ctx.createGain(), n = ctx.currentTime;
      o.type = 'sine'; o.frequency.setValueAtTime(f1, n);
      if (f2) o.frequency.exponentialRampToValueAtTime(f2, n + 0.12);
      g.gain.setValueAtTime(0, n); g.gain.linearRampToValueAtTime(0.045, n + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, n + 0.26);
      o.connect(g).connect(ctx.destination); o.start(n); o.stop(n + 0.3);
    } catch { /* no audio device */ }
  }

  // ---------- hover panel, menu, chat ----------
  function openPanel() {
    clearTimeout(closeDockTimer);
    if (state !== 'idle' || open) return;
    open = true; hud = null; peekUntil = 0;
    render();
  }
  function closePanel(force) {
    if (!open) return;
    if (!force && (!menu.hidden || !chat.hidden || kbOpen)) return;   // opened from the keyboard: Esc closes it
    open = false; menu.hidden = true; page = 'home'; closeChat(true);
    if (kbOpen) { kbOpen = false; api.focus(false); if (!hovering) api.interactive(false); }
    render();
  }
  // ---------- keyboard: the shortcut opens the panel, arrows change pages, Esc closes ----------
  let kbOpen = false;
  const PAGES = ['home', 'apps', 'shelf', 'clips'];
  function kbOpenPanel() {
    if (state !== 'idle') {                      // a question on screen: put the keyboard on its buttons
      choices.querySelector('button')?.focus();
      return;
    }
    kbOpen = true; clearTimeout(closeDockTimer);
    open = true; hud = null; peekUntil = 0; page = 'home'; menu.hidden = true;
    render();
    setTimeout(() => dock.querySelector('button')?.focus(), 30);
  }
  document.addEventListener('keydown', e => {
    if (!open) return;
    const typing = e.target.matches('input, textarea');
    if (e.key === 'Escape' && chat.hidden && menu.hidden) { e.preventDefault(); closePanel(true); return; }
    if (!typing && (e.key === 'ArrowLeft' || e.key === 'ArrowRight') && menu.hidden) {
      e.preventDefault();
      const i = Math.max(0, PAGES.indexOf(page));
      const next = PAGES[(i + (e.key === 'ArrowLeft' ? 1 : PAGES.length - 1)) % PAGES.length];   // RTL: left is forward
      page = next;
      if (page === 'apps') api.send({ t: 'apps_get' });
      render();
    }
  });
  window.addEventListener('blur', () => { if (kbOpen) closePanel(true); });     // clicked somewhere else
  function openMenu() {
    menu.hidden = false; $('open-menu').setAttribute('aria-expanded', 'true');
    api.send({ t: 'menu_open' });
    render();
  }
  function closeMenu() {
    if (menu.hidden) return;
    menu.hidden = true; $('open-menu').setAttribute('aria-expanded', 'false');
    render();
  }
  function openChat() {
    menu.hidden = true;
    chat.hidden = false;
    statusEl.textContent = 'اكتب، وبعدين Enter';
    render(); api.interactive(true); api.focus(true);
    setTimeout(() => chatInput.focus(), 40);
  }
  function closeChat(silent) {
    if (chat.hidden) return;
    chat.hidden = true;
    if (state === 'idle') statusEl.textContent = '';
    chatInput.value = ''; chatInput.blur(); api.focus(false);
    if (!silent) closePanel(true);
  }

  tab.addEventListener('mouseenter', () => { hovering = true; api.interactive(true); holdNotice(true); openPanel(); });
  tab.addEventListener('mouseleave', () => {
    hovering = false;
    holdNotice(false);
    if (chat.hidden) api.interactive(false);
    if (hideTimer && hideAt - Date.now() < 1500) scheduleHide(1500);
    clearTimeout(closeDockTimer);
    closeDockTimer = setTimeout(() => closePanel(false), 450);
  });
  dock.querySelector('[data-quick="listen"]').onclick = () => { closePanel(true); api.send({ t: 'quick', id: 'listen' }); };
  $('open-chat').onclick = openChat;
  $('open-menu').onclick = () => (menu.hidden ? openMenu() : closeMenu());
  menu.addEventListener('click', e => {
    const b = e.target.closest('button[data-menu]'); if (!b) return;
    if (b.dataset.menu === 'settings') api.openSettings();
    else if (b.dataset.menu === 'history') { menu.hidden = true; page = 'history'; drawHistory(); render(); return; }
    else api.send({ t: 'menu', id: b.dataset.menu });
    if (b.getAttribute('role') !== 'menuitemcheckbox') closePanel(true);
  });
  chat.onsubmit = e => {
    e.preventDefault();
    const text = chatInput.value.trim(); if (!text) return;
    closeChat(true); open = false;
    api.send({ t: 'chat', text });
    setState('thinking', text);
  };
  chatInput.addEventListener('keydown', e => { if (e.key === 'Escape') closeChat(false); });
  chatInput.addEventListener('blur', () => { if (!chatInput.value.trim()) setTimeout(() => { if (!chat.hidden && document.activeElement !== chatInput) closeChat(false); }, 150); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !menu.hidden) closeMenu(); });

  // ---------- messages from Python ----------
  api.onMessage(m => {
    switch (m.t) {
      case 'kb_open': kbOpenPanel(); break;
      case 'state': m.state === 'idle' ? hide() : setState(m.state, m.text || ''); break;
      case 'say': say(m.text, m.state || 'info', m.chime !== false); break;
      case 'ask': ask(m.id, m.text, m.options, m.timeout, m.chime !== false); break;
      case 'listening_soft': if (!replyVisible()) setState('listening', m.text || ''); break;
      case 'end_turn': if (!replyVisible() && ACTIVE.has(state)) hide(); break;
      case 'level': levelTarget = Math.max(0, Math.min(1, Number(m.v) || 0)); levelAt = performance.now(); break;
      case 'progress': setProgress(Number(m.v)); break;
      case 'hud': showHud(m); break;
      case 'media': onMedia(m); break;
      case 'music_level': musicTarget = Math.max(0, Math.min(1, Number(m.v) || 0)); musicAt = performance.now(); if (tab.dataset.mode === 'live') kick(); break;
      case 'stats': stats = m; if (open) drawStats(); break;
      case 'prayer': prayer = m; if (open) { drawDay(); render(); } break;
      case 'focus': focus = m; if (focus.ends_at) focus.ends_at = Number(focus.ends_at); drawDay(); render(); break;
      case 'water':
        if (water && water.count < m.goal && m.count >= m.goal) celebrate();     // today's goal reached
        water = { count: m.count, goal: m.goal }; if (open) { drawDay(); render(); } break;
      case 'weather': weather = m; if (open) render(); break;
      case 'apps': apps = { pinned: m.pinned || [], catalog: m.catalog || apps.catalog }; drawApps(); break;
      case 'radio_stations':
        radio.stations = m.items || []; radio.error = !!m.error;
        if (radio.url && !radio.name) radio.name = (radio.stations.find(s => s.url === radio.url) || {}).name || '';
        drawRadio(); if (open && page === 'radio') render(); break;
      case 'battery_saver': saverOn = !!m.on; kick(); break;
      case 'meetings': meetings = m.events || []; if (open) { drawDay(); render(); } break;
      case 'notice': showNotice(m); break;
      case 'downloads': downloads = m.items || []; render(); break;
      case 'shelf': shelf = m.items || []; drawShelf(); if (open) render(); break;
      case 'clips': clips = { enabled: m.enabled !== false, items: m.items || [] }; drawClips(); if (open) render(); break;
      case 'privacy': privacy = { mic: m.mic || [], cam: m.cam || [] }; render(); break;
      case 'fullscreen': fullscreen = !!m.on; maxFront = !!m.max; render(); break;
      case 'island_settings':
        prefs = { ...prefs, ...(m.values || {}) };
        document.documentElement.dataset.theme = prefs.theme || 'faience';
        if (Number.isFinite(prefs.radio_volume)) audio.volume = prefs.radio_volume / 100;
        if (!radio.playing && prefs.radio_station) radio.url = prefs.radio_station;   // the last station you chose
        render(); break;
      case 'menu_state':
        for (const [k, v] of Object.entries({ toggle_listen: m.listen, toggle_voice: m.voice, toggle_companion: m.companion })) {
          const b = menu.querySelector(`[data-menu="${k}"]`);
          if (!b) continue;
          b.hidden = v === null || v === undefined;
          b.setAttribute('aria-checked', String(!!v));
        }
        render(); break;
    }
  });

  // ---------- downloads, shelf, clipboard ----------
  function drawDownloads() {
    const d = downloads[0]; if (!d) return;
    $('dl-name').textContent = (downloads.length > 1 ? `${nf.format(downloads.length)} تحميلات — ` : '') + d.name;
    $('dl-meta').textContent = `${fmtBytes(d.bytes)} · ${fmtBytes(d.speed)}/ث`;
  }
  function drawShelf() {
    $('shelf-empty').hidden = shelf.length > 0;
    $('shelf-clear').hidden = !shelf.length;
    $('shelf-list').replaceChildren(...shelf.map(it => {
      const li = document.createElement('li'); li.className = 'shelf-item';
      const b = document.createElement('button'); b.type = 'button'; b.draggable = true; b.title = it.path;
      const img = document.createElement('img'); img.alt = '';
      api.fileIcon(it.path).then(src => { if (src) img.src = src; });
      const name = document.createElement('span'); name.className = 'name'; name.dir = 'auto'; name.textContent = it.name;
      b.append(img, name);
      b.onclick = () => api.send({ t: 'shelf_open', i: it.i });
      b.addEventListener('dragstart', e => { e.preventDefault(); api.dragOut(it.path); });   // drag it into another app
      const x = document.createElement('button'); x.type = 'button'; x.className = 'x'; x.textContent = '×';
      x.setAttribute('aria-label', `شيل ${it.name} من الرف`);
      x.onclick = () => api.send({ t: 'shelf_remove', i: it.i });
      const loc = document.createElement('button'); loc.type = 'button'; loc.className = 'loc'; loc.textContent = '↗';
      loc.setAttribute('aria-label', `وريني مكان ${it.name}`);
      loc.onclick = () => api.send({ t: 'shelf_folder', i: it.i });
      li.append(b, x, loc);
      return li;
    }));
    if (open && page === 'shelf') fit('panel');
  }
  function drawClips() {
    $('clips-empty').textContent = clips.enabled ? 'أي نص تنسخه هيظهر هنا، ودوسة عليه تنسخه تاني' : 'سجل الحافظة مقفول من الإعدادات';
    $('clips-empty').hidden = clips.enabled && clips.items.length > 0;
    $('clips-clear').hidden = !clips.items.length;
    $('clip-list').replaceChildren(...clips.items.map((text, i) => {
      const li = document.createElement('li');
      const b = document.createElement('button'); b.type = 'button'; b.dir = 'auto';
      b.textContent = text.replace(/\s+/g, ' ').trim(); b.title = 'دوس عشان تنسخه';
      b.onclick = () => { api.send({ t: 'clip_copy', i }); b.classList.add('copied'); };
      li.append(b); return li;
    }));
    if (open && page === 'clips') fit('panel');
  }
  for (const b of document.querySelectorAll('[data-page]')) {
    b.onclick = () => {
      page = page === b.dataset.page ? 'home' : b.dataset.page; menu.hidden = true;
      if (page === 'apps') api.send({ t: 'apps_get' });
      if (page === 'radio') { drawRadio(); if (!radio.stations.length) api.send({ t: 'radio_get' }); }
      render();
    };
  }

  // ---------- apps ----------
  function appTile(app) {
    const li = document.createElement('li'); li.className = 'app-tile';
    const b = document.createElement('button'); b.type = 'button'; b.title = app.name;
    const name = document.createElement('span'); name.className = 'name'; name.dir = 'auto'; name.textContent = app.name;
    const letter = document.createElement('span'); letter.className = 'letter'; letter.textContent = app.name.trim().charAt(0).toUpperCase();
    b.append(letter, name);
    if (app.icon) api.fileIcon(app.icon).then(src => { if (src) { const img = document.createElement('img'); img.alt = ''; img.src = src; letter.replaceWith(img); } });
    b.onclick = () => { if (!appsEdit) { api.send({ t: 'app_open', name: app.name }); closePanel(true); } };
    li.append(b);
    if (app.running) { const dot = document.createElement('i'); dot.className = 'running'; dot.title = 'مفتوح'; li.append(dot); }
    if (appsEdit) {
      const x = document.createElement('button'); x.type = 'button'; x.className = 'x'; x.textContent = '×';
      x.setAttribute('aria-label', `شيل ${app.name}`); x.onclick = () => api.send({ t: 'app_unpin', name: app.name });
      li.append(x);
    }
    return li;
  }
  function drawApps() {
    const tiles = apps.pinned.map(appTile);
    if (appsEdit && apps.pinned.length < 12) {
      const li = document.createElement('li'); li.className = 'app-tile add';
      const b = document.createElement('button'); b.type = 'button';
      b.innerHTML = '<span class="letter">+</span><span class="name">ضيف</span>';
      b.onclick = () => { $('apps-picker').hidden = false; $('apps-grid').hidden = true; drawPicker(); render(); setTimeout(() => $('apps-search').focus(), 30); api.focus(true); };
      li.append(b); tiles.push(li);
    }
    $('apps-grid').replaceChildren(...tiles);
    $('apps-edit').setAttribute('aria-pressed', String(appsEdit));
    $('apps-edit').textContent = appsEdit ? 'خلصت' : 'تعديل';
    if (!appsEdit) $('apps-picker').hidden = true;
    $('apps-grid').hidden = !$('apps-picker').hidden;     // the picker takes the grid's place while it's open
    if (open && page === 'apps') render();
  }
  function drawPicker() {
    const q = $('apps-search').value.trim().toLowerCase();
    const have = new Set(apps.pinned.map(a => a.name.toLowerCase()));
    const list = (apps.catalog || []).filter(n => !have.has(n.toLowerCase()) && (!q || n.toLowerCase().includes(q))).slice(0, 40);
    $('apps-list').replaceChildren(...list.map(n => {
      const li = document.createElement('li'); const b = document.createElement('button');
      b.type = 'button'; b.dir = 'auto'; b.textContent = n;
      b.onclick = () => api.send({ t: 'app_pin', name: n });
      li.append(b); return li;
    }));
  }
  $('apps-edit').onclick = () => { appsEdit = !appsEdit; drawApps(); };
  $('apps-search').addEventListener('input', drawPicker);

  // ---------- Qur'an radio: played by the island itself ----------
  audio.volume = 0.7;
  function drawRadio() {
    const t = $('rd-toggle');
    t.innerHTML = svg(radio.playing ? 'pause' : 'play');
    t.setAttribute('aria-label', radio.playing ? 'وقّف الإذاعة' : 'شغّل الإذاعة');
    t.disabled = !radio.url;
    $('rd-name').textContent = radio.name || 'اختار قارئ من تحت';
    if (!$('rd-state').dataset.msg) $('rd-state').textContent = radio.playing ? 'بث مباشر' : radio.url ? 'واقفة' : '';
    $('rd-volume').value = String(Math.round(audio.volume * 100));
    const q = $('rd-search').value.trim();
    const items = radio.stations.filter(s => !q || s.name.includes(q)).slice(0, 60);
    $('rd-list').replaceChildren(...(radio.error && !radio.stations.length
      ? [Object.assign(document.createElement('li'), { textContent: 'مش قادر أجيب القرّاء دلوقتي، جرّب تاني بعد شوية' })]
      : items.map(s => {
        const li = document.createElement('li'); const b = document.createElement('button');
        b.type = 'button'; b.dir = 'auto'; b.textContent = s.name;
        if (s.url === radio.url) b.setAttribute('aria-current', 'true');
        b.onclick = () => radioPlay(s);
        li.append(b); return li;
      })));
  }
  function radioState(msg) { $('rd-state').dataset.msg = msg ? '1' : ''; $('rd-state').textContent = msg || ''; drawRadio(); }
  function radioPlay(s) {
    if (s) { radio.url = s.url; radio.name = s.name; radio.tries = 0; api.send({ t: 'settings_set', section: 'island', values: { radio_station: s.url } }); }
    if (!radio.url) return;
    audio.src = radio.url;
    radioState('بيوصل…');
    audio.play().then(() => {
      radio.playing = true; radio.tries = 0; radioState('');
      if ('mediaSession' in navigator) navigator.mediaSession.metadata = new MediaMetadata({ title: radio.name, artist: 'إذاعة القرآن الكريم' });
    }).catch(() => { radio.playing = false; radioState('البث مش متاح دلوقتي'); });
  }
  function radioStop(msg) {
    audio.pause(); audio.removeAttribute('src'); audio.load();
    radio.playing = false; radioState(msg || '');
  }
  // a dropped stream reconnects by itself: after 2, 5, then 15 seconds
  audio.addEventListener('error', () => {
    if (!radio.playing) return;
    const wait = [2, 5, 15][Math.min(radio.tries, 2)]; radio.tries++;
    radioState(`البث وقف، هرجّعه بعد ${nf.format(wait)} ثواني`);
    setTimeout(() => { if (radio.playing) radioPlay(); }, wait * 1000);
  });
  $('rd-toggle').onclick = () => (radio.playing ? radioStop() : radioPlay());
  $('rd-volume').addEventListener('input', e => { audio.volume = Number(e.target.value) / 100; });
  $('rd-volume').addEventListener('change', e => api.send({ t: 'settings_set', section: 'island', values: { radio_volume: Number(e.target.value) } }));
  $('rd-search').addEventListener('input', drawRadio);
  if ('mediaSession' in navigator) {
    navigator.mediaSession.setActionHandler('play', () => radioPlay());
    navigator.mediaSession.setActionHandler('pause', () => radioStop());
  }
  $('nt-img').onload = () => { if (notice) render(); };   // size the notice once the thumbnail is in
  $('history-clear').onclick = () => { history.length = 0; drawHistory(); };
  $('shelf-clear').onclick = () => api.send({ t: 'shelf_clear' });
  $('clips-clear').onclick = () => api.send({ t: 'clip_clear' });

  // drop files on the island: they go on the shelf (only their paths are kept)
  const hasFiles = e => [...(e.dataTransfer?.types || [])].includes('Files');
  tab.addEventListener('dragenter', e => {
    if (!hasFiles(e) || state !== 'idle') return;
    e.preventDefault(); hovering = true; api.interactive(true);
    clearTimeout(closeDockTimer); open = true; page = 'shelf'; hud = null; peekUntil = 0;
    tab.classList.add('drop-target'); render();
  });
  tab.addEventListener('dragover', e => { if (hasFiles(e)) { e.preventDefault(); e.dataTransfer.dropEffect = 'link'; } });
  tab.addEventListener('dragleave', e => {
    if (tab.contains(e.relatedTarget)) return;
    tab.classList.remove('drop-target');
  });
  tab.addEventListener('drop', e => {
    e.preventDefault(); tab.classList.remove('drop-target');
    const paths = [...(e.dataTransfer?.files || [])].map(f => api.pathFor(f)).filter(Boolean);
    if (paths.length) api.send({ t: 'shelf_add', paths });
  });
  // anything dropped elsewhere in the window must not navigate
  window.addEventListener('dragover', e => e.preventDefault());
  window.addEventListener('drop', e => e.preventDefault());

  // icon buttons: the tooltip says what the label says
  new MutationObserver(() => {
    for (const b of document.querySelectorAll('button[aria-label]:not([title])')) b.title = b.getAttribute('aria-label');
  }).observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ['aria-label'] });
  for (const b of document.querySelectorAll('button[aria-label]:not([title])')) b.title = b.getAttribute('aria-label');

  // load the Mushaf face now, so the first ayah doesn't show in a fallback font
  document.fonts.load('26px "Yobi Quran"').catch(() => {});

  reduced.addEventListener('change', kick);
  render();
})();
