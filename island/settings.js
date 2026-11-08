// Settings window. Python checks every value and answers with the saved settings.
(() => {
  const api = window.yobi;
  const $ = id => document.getElementById(id);
  const THEME_NAMES = { faience: 'فيروزي', night: 'ليل', papyrus: 'بردي', nile: 'نيل', carnelian: 'عقيق' };
  let S = null, savedTimer = null;

  const save = (section, values) => api.send({ t: 'settings_set', section, values });
  const get = key => { const [sec, k] = key.split('.'); return S?.[sec]?.[k]; };

  function draw() {
    document.documentElement.dataset.theme = S.island.theme;
    // themes
    $('themes').replaceChildren(...S.themes.map(name => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'swatch'; b.setAttribute('role', 'radio');
      b.setAttribute('aria-checked', String(S.island.theme === name));
      b.innerHTML = `<span class="mini-tab" data-theme="${name}"></span><span>${THEME_NAMES[name] || name}</span>`;
      b.onclick = () => save('island', { theme: name });
      return b;
    }));
    // plain fields
    for (const el of document.querySelectorAll('[data-s]')) {
      const v = get(el.dataset.s);
      if (el.type === 'checkbox') el.checked = !!v;
      else if (document.activeElement !== el) el.value = v ?? '';
    }
    // city
    const city = $('city');
    const known = S.cities.find(c => c.name === S.daily.city);
    city.replaceChildren(
      ...S.cities.map(c => new Option(c.name, c.name)),
      new Option('مكان تاني (اكتب الإحداثيات)', '__other'),
    );
    city.value = known ? known.name : '__other';
    $('coords').hidden = !!known;
    // quiet hours
    const q = S.daily.quiet_hours || '';
    $('quiet-on').checked = !!q;
    $('quiet-times').hidden = !q;
    if (q) { const [a, b] = q.split('-'); $('quiet-from').value = a; $('quiet-to').value = b; }
    else { $('quiet-from').value ||= '23:00'; $('quiet-to').value ||= '07:00'; }
    // calendar link
    if (document.activeElement !== $('ical')) $('ical').value = S.daily.calendar_ical || '';
    drawDisplays();
    $('form').setAttribute('aria-busy', 'false');
  }

  // the screens the island can sit on
  async function drawDisplays() {
    const list = await api.displays().catch(() => []);
    const sel = $('display');
    sel.replaceChildren(
      new Option('الشاشة الرئيسية', 'primary'),
      new Option('الشاشة اللي فيها الماوس', 'cursor'),
      ...(list.length > 1 ? list.map(d => new Option(`شاشة ${d.n} (${d.w}×${d.h}${d.scale !== 1 ? `، ${Math.round(d.scale * 100)}٪` : ''})${d.primary ? ' — الرئيسية' : ''}`, d.id)) : []),
    );
    sel.value = S.island.display || 'primary';
    if (sel.value === '') sel.value = 'primary';
  }
  $('display').addEventListener('change', e => save('island', { display: e.target.value }));

  // "try it": the island shows a sample right now
  for (const b of document.querySelectorAll('[data-try]')) b.onclick = () => api.send({ t: 'preview', what: b.dataset.try });

  // the section you're reading is marked in the list
  const links = [...document.querySelectorAll('.side a')];
  const spy = new IntersectionObserver(entries => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      for (const a of links) a.setAttribute('aria-current', String(a.getAttribute('href') === `#${e.target.id}`));
    }
  }, { rootMargin: '-10% 0px -70% 0px' });
  for (const s of document.querySelectorAll('main section[id]')) spy.observe(s);

  // search: keep the settings whose words match, and their sections
  $('find').addEventListener('input', e => {
    const q = e.target.value.trim();
    let any = false;
    for (const sec of document.querySelectorAll('main section')) {
      const title = sec.querySelector('h2').textContent;
      let hit = false;
      for (const item of sec.querySelectorAll('.check, .row > label, .row.link, .themes, .preview, .note, .try')) {
        const show = !q || title.includes(q) || item.textContent.includes(q);
        item.classList.toggle('hide-search', !show);
        hit = hit || (show && !!q);
      }
      const keep = !q || hit || title.includes(q);
      sec.classList.toggle('hide-search', !keep);
      if (keep && q && title.includes(q)) for (const el of sec.querySelectorAll('.hide-search')) el.classList.remove('hide-search');
      any = any || keep;
    }
    $('no-match').hidden = any;
  });

  for (const el of document.querySelectorAll('[data-s]')) {
    el.addEventListener('change', () => {
      const [sec, k] = el.dataset.s.split('.');
      let v = el.type === 'checkbox' ? el.checked : el.value;
      if ('num' in el.dataset) { v = Number(v); if (!Number.isFinite(v)) { draw(); return; } }
      save(sec, { [k]: v });
    });
  }
  $('city').addEventListener('change', e => {
    const c = S.cities.find(x => x.name === e.target.value);
    if (c) save('daily', { city: c.name, lat: c.lat, lon: c.lon, method: c.method });
    else { $('coords').hidden = false; save('daily', { city: 'مكان تاني' }); }
  });
  const saveQuiet = () => save('daily', { quiet_hours: $('quiet-on').checked ? `${$('quiet-from').value}-${$('quiet-to').value}` : '' });
  $('quiet-on').addEventListener('change', () => { $('quiet-times').hidden = !$('quiet-on').checked; saveQuiet(); });
  $('quiet-from').addEventListener('change', saveQuiet);
  $('quiet-to').addEventListener('change', saveQuiet);
  $('ical-show').onclick = () => {
    const show = $('ical').type === 'password';
    $('ical').type = show ? 'text' : 'password';
    $('ical-show').textContent = show ? 'إخفاء' : 'إظهار';
  };
  $('ical-save').onclick = () => {
    const v = $('ical').value.trim();
    if (v && !/^(https|webcal):\/\/\S+$/i.test(v)) { flash('الرابط لازم يبدأ بـ https://'); return; }
    save('daily', { calendar_ical: v });
  };

  function flash(text = 'اتحفظ ✓') {
    $('saved').textContent = text;
    clearTimeout(savedTimer);
    savedTimer = setTimeout(() => { $('saved').textContent = ''; }, 1800);
  }

  api.onMessage(m => {
    if (m.t === 'settings') { S = m; draw(); }
    else if (m.t === 'settings_saved') flash();
  });
  api.send({ t: 'settings_get' });
})();
