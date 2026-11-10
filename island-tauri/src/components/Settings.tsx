// Interface 9: the settings window (design A, "the side list"): sections with coloured icons on the
// side, a search, a live island at the top that takes the chosen theme, and every setting the
// Electron window had. Python checks every value and answers with the saved settings.
import { motion } from 'motion/react';
import { Bell, BookOpen, Calendar, Eye, Keyboard, MoonStar, Palette, Search, Sparkles, Timer, type LucideIcon } from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { bridge, type Screen } from '../bridge';
import { spring } from '../motion';
import type { InMsg } from '../types';
import { Bars } from './CompactIsland';
import { useIsland } from '../store';
import { T, dir, fmt } from '../i18n';

type Sec = 'island' | 'daily';
interface City { name: string; lat: number; lon: number; method: string }
interface S { island: Record<string, unknown>; daily: Record<string, unknown>; themes: string[]; methods: string[]; cities: City[] }

const THEME_COLORS: Record<string, [string, string]> = {
  faience: ['#3CC2B4', '#E3B04B'], night: ['#45D0C1', '#E3B04B'], papyrus: ['#D8B56A', '#E3B04B'], nile: ['#7FD6C2', '#E3B04B'], carnelian: ['#E8A25B', '#E9C46A'],
};
type Sw = [string, string, string?];   // key, label, small print
// every word here follows the island's language (Settings → Look → Language), so they're built at render time
function words() {
  const THEME_NAMES: Record<string, string> = { faience: T('فيروزي', 'Faience'), night: T('ليل', 'Night'), papyrus: T('بردي', 'Papyrus'), nile: T('نيل', 'Nile'), carnelian: T('عقيق', 'Carnelian') };
  const METHODS: Record<string, string> = {
    EGYPT: T('الهيئة المصرية العامة للمساحة', 'Egyptian General Authority of Survey'), MAKKAH: T('أم القرى، مكة', 'Umm al-Qura, Makkah'),
    MWL: T('رابطة العالم الإسلامي', 'Muslim World League'), KARACHI: T('جامعة العلوم الإسلامية، كراتشي', 'University of Islamic Sciences, Karachi'), ISNA: T('أمريكا الشمالية (ISNA)', 'North America (ISNA)'),
  };
  const SHORTCUTS: [string, string][] = [['Ctrl+Alt+I', 'Ctrl + Alt + I'], ['Ctrl+Alt+Space', 'Ctrl + Alt + Space'], ['Ctrl+Shift+Space', 'Ctrl + Shift + Space'], ['Alt+Shift+Y', 'Alt + Shift + Y'], ['', T('من غير اختصار', 'No shortcut')]];
  const SECTIONS: { id: string; title: string; icon: LucideIcon; color: string; tryIt?: [string, string] }[] = [
    { id: 'look', title: T('الشكل', 'Look'), icon: Palette, color: '#C792EA', tryIt: ['reply', T('جرّب على الجزيرة', 'Try it on the island')] },
    { id: 'shows', title: T('الجزيرة بتعرض إيه', 'What the island shows'), icon: Eye, color: '#3CC2B4' },
    { id: 'moments', title: T('لحظات وإضافات', 'Moments and extras'), icon: Sparkles, color: '#F0A43A', tryIt: ['brief', T('جرّب صباح الخير', 'Try good morning')] },
    { id: 'prayer', title: T('الصلاة', 'Prayer'), icon: MoonStar, color: '#E3B04B', tryIt: ['adhan', T('جرّب تنبيه الأذان', 'Try the adhan alert')] },
    { id: 'focus', title: T('التركيز', 'Focus'), icon: Timer, color: '#5AA9FF' },
    { id: 'remind', title: T('الأذكار والأدعية والآيات', 'Dhikr, duas and verses'), icon: BookOpen, color: '#7BD88F', tryIt: ['reminder', T('جرّب تذكير', 'Try a reminder')] },
    { id: 'meet', title: T('الاجتماعات', 'Meetings'), icon: Calendar, color: '#7FA8FF' },
    { id: 'keys', title: T('الاختصار والشاشة', 'Shortcut and screen'), icon: Keyboard, color: '#A1A1A6' },
  ];
  const SHOWS: Sw[] = [
    ['island.idle_clock', T('الساعة على الجزيرة وهي هادية', 'The clock while the island is idle')],
    ['island.idle_info', T('وجنبها الطقس والمعالج والرامات والصلاة الجاية', 'With the weather, CPU, RAM and the next prayer beside it')], ['island.music_tab', T('الأغنية اللي شغالة', 'The song that’s playing')],
    ['island.track_peek', T('اسم الأغنية لما تتغير', 'The song’s name when it changes')],
    ['island.downloads', T('التحميلات اللي في فولدر التحميلات', 'Downloads in the Downloads folder')], ['island.screenshot_toast', T('لقطات الشاشة والصور اللي بتنسخها', 'Screenshots and images you copy')],
    ['island.clipboard_history', T('سجل الحافظة', 'Clipboard history'), T('بيتحفظ في الذاكرة بس لحد ما يوبي يتقفل، وبيتجاهل كلمات السر', 'Kept in memory only until Yobi closes, and skips passwords')],
    ['island.privacy_dots', T('نقطة لما برنامج يستخدم المايك أو الكاميرا', 'A dot when an app uses the microphone or camera')],
    ['island.hide_fullscreen', T('تستخبى وقت الألعاب والأفلام اللي على الشاشة كلها', 'Hide during full-screen games and movies'), T('يوبي والأذان والاجتماعات بيظهروا برضه', 'Yobi, the adhan and meetings still show')],
  ];
  const MOMENTS: Sw[] = [
    ['island.weather', T('الطقس في مدينة الصلاة', 'Weather in the prayer city')], ['island.net_toasts', T('قولّي لما النت يفصل أو يرجع', 'Tell me when the internet drops or comes back')],
    ['island.smart_clipboard', T('الحافظة الذكية', 'Smart clipboard'), T('لينك تفتحه، لون تشوفه، حسبة تتحل، أو عدد كلمات النص الطويل', 'A link to open, a colour to see, a sum solved, or a long text’s word count')],
    ['island.morning_brief', T('صباح الخير أول ما تقعد على الجهاز', 'Good morning when you first sit down')], ['island.welcome_back', T('أهلا رجعت، باللي حصل وإنت مش موجود', 'Welcome back, with what happened while you were away')],
    ['island.wellbeing', T('فكّرني آخد بريك بعد ٥٠ دقيقة شغل', 'Remind me to take a break after 50 minutes of work')], ['island.celebrate', T('احتفال صغير لما أكمّل هدف', 'A small celebration when I reach a goal')],
    ['island.radio_pause_prayer', T('وقّف إذاعة القرآن وقت الأذان', 'Pause the Quran radio during the adhan')], ['island.battery_saver', T('توفير البطارية: من غير حركة لما البطارية تقل', 'Battery saver: no animation when the battery is low')],
  ];
  return { THEME_NAMES, METHODS, SHORTCUTS, SECTIONS, SHOWS, MOMENTS };
}

/* ── the building blocks ── */
function Switch({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} onClick={() => onChange(!on)}
            className="flex h-[24px] w-[42px] shrink-0 items-center rounded-full p-[3px] transition-colors" style={{ background: on ? 'var(--color-accent)' : 'rgba(255,255,255,.14)' }}>
      <motion.i layout transition={spring.micro} className={`size-[18px] rounded-full bg-white shadow ${on ? 'ms-auto' : 'me-auto'}`} />
    </button>
  );
}
const Group = ({ children }: { children: ReactNode }) => <div className="divide-y divide-white/5 overflow-hidden rounded-[14px] bg-white/[.04] ring-1 ring-white/5">{children}</div>;
/** A key press as a wake key as hotkey.py names it ("f8", "y", "ctrl+alt+y"); null = a key
 *  it has no name for. Python checks it again (wake_key_ok in island_tools.py). */
const KEY_NAMES: Record<string, string> = {
  Pause: 'pause', ScrollLock: 'scroll lock', Space: 'space', Insert: 'insert', Home: 'home', End: 'end', PageUp: 'page up', PageDown: 'page down',
  Tab: 'tab', Enter: 'enter', Backspace: 'backspace', Delete: 'delete', CapsLock: 'caps lock', PrintScreen: 'print screen', NumLock: 'num lock',
  ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', ContextMenu: 'menu',
  Minus: '-', Equal: '=', BracketLeft: '[', BracketRight: ']', Backslash: 'backslash', Comma: 'comma', Period: '.', Slash: '/', Semicolon: 'semicolon', Quote: 'quote', Backquote: 'backquote',
  NumpadDecimal: 'decimal', NumpadMultiply: 'multiply', NumpadAdd: 'add', NumpadSubtract: 'subtract', NumpadDivide: 'divide', NumpadEnter: 'enter',
};
function comboOf(e: KeyboardEvent): string | null {
  const c = e.code;
  const key = /^F([1-9]|1\d|2[0-4])$/.test(c) ? c.toLowerCase() : /^Key[A-Z]$/.test(c) ? c[3].toLowerCase() : /^Digit\d$/.test(c) ? c[5]
    : /^Numpad\d$/.test(c) ? `num ${c[6]}` : KEY_NAMES[c];
  if (!key) return null;
  return [e.ctrlKey && 'ctrl', e.altKey && 'alt', e.shiftKey && 'shift', e.metaKey && 'windows', key].filter(Boolean).join('+');
}
const showKey = (k: string) => k.split('+').map(p => p.replace(/\b\w/g, ch => ch.toUpperCase())).join(' + ');

function KeyPicker({ value, taken, label, onPick }: { value: string; taken: string; label: string; onPick: (k: string) => void }) {
  const [waiting, setWaiting] = useState(false);
  const [bad, setBad] = useState(false);
  useEffect(() => {
    if (!waiting) return;
    const down = (e: KeyboardEvent) => {
      e.preventDefault(); e.stopPropagation();
      if (e.key === 'Escape') { setWaiting(false); return; }
      if (['Control', 'Alt', 'Shift', 'Meta'].includes(e.key)) return;
      const k = comboOf(e);
      if (!k || k === taken) { setBad(true); return; }
      setWaiting(false); onPick(k);
    };
    window.addEventListener('keydown', down, true);
    return () => window.removeEventListener('keydown', down, true);
  }, [waiting, taken, onPick]);
  return (
    <button type="button" className={field} aria-label={label} aria-live="polite" onClick={() => { setBad(false); setWaiting(w => !w); }} onBlur={() => setWaiting(false)}>
      {!waiting ? <bdi dir="ltr">{showKey(value)}</bdi> : bad ? T('الزرار ده مينفعش، جرّب غيره', 'That key won’t work, try another') : T('دوس الزرار اللي عايزه…', 'Press the key you want…')}
    </button>
  );
}

function Row({ label, sub, children, hide }: { label: string; sub?: string; children: ReactNode; hide?: boolean }) {
  if (hide) return null;
  return (
    <label className="flex min-h-12 items-center gap-4 px-4 py-2.5">
      <span className="min-w-0 flex-1 text-[13px]">{label}{sub && <small className="block text-[11px] text-ink-3">{sub}</small>}</span>
      {children}
    </label>
  );
}
const field = 'rounded-[9px] bg-white/[.07] px-2.5 py-1.5 text-[13px] text-ink outline-none ring-1 ring-white/10 focus:ring-accent/70';
/** a number that saves when you leave the box (Python clamps it to its range) */
function NumberBox({ value, min, max, step, unit, label, onSave }: { value: unknown; min: number; max: number; step?: number; unit?: string; label: string; onSave: (v: number) => void }) {
  return (
    <span className="flex items-center gap-1.5 text-[12px] text-ink-2">
      <input key={String(value)} type="number" defaultValue={value as number} min={min} max={max} step={step} aria-label={label} dir="ltr"
             className={`${field} w-24 text-center tabular-nums`}
             onBlur={e => { const v = Number(e.target.value); if (e.target.value !== '' && Number.isFinite(v) && v !== value) onSave(v); }}
             onKeyDown={e => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />
      {unit}
    </span>
  );
}

/* ── the window ── */
export function SettingsWindow() {
  const [S, setS] = useState<S | null>(null);
  const [saved, setSaved] = useState('');
  const [q, setQ] = useState('');
  const [current, setCurrent] = useState('look');
  const [screens, setScreens] = useState<Screen[]>([]);
  const [showIcal, setShowIcal] = useState(false);
  const [ical, setIcal] = useState('');
  const main = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const flash = (text = T('اتحفظ ✓', 'Saved ✓')) => { setSaved(text); clearTimeout(timer.current); timer.current = setTimeout(() => setSaved(''), 1800); };
  const save = (section: Sec, values: Record<string, unknown>) => bridge.send({ t: 'settings_set', section, values });
  const get = (key: string) => { const [s, k] = key.split('.') as [Sec, string]; return S?.[s]?.[k]; };
  const put = (key: string, v: unknown) => { const [s, k] = key.split('.') as [Sec, string]; save(s, { [k]: v }); };
  const wakeKey = String(get('island.wake_key') || 'ctrl+alt+y');

  useEffect(() => {
    let got = false, retry: ReturnType<typeof setInterval> | undefined;
    // ask only once we're listening (Python answers in milliseconds), and again until the answer comes
    void bridge.onMessage((m: InMsg) => {
      if (m.t === 'settings') {
        got = true; clearInterval(retry); const s = m as unknown as S;
        useIsland.setState(st => ({ prefs: { ...st.prefs, lang: s.island.lang } }));   // T() reads the language from here
        setS(s); setIcal(String(s.daily.calendar_ical || '')); }
      else if (m.t === 'settings_saved') flash();
    }).then(() => {
      bridge.send({ t: 'settings_get' });
      retry = setInterval(() => { if (!got) bridge.send({ t: 'settings_get' }); }, 2000);
    });
    void bridge.displays().then(setScreens);
    return () => clearInterval(retry);
  }, []);
  useEffect(() => { if (S) document.documentElement.dataset.theme = String(S.island.theme || 'faience'); }, [S]);

  // the section you're reading is marked in the list
  useEffect(() => {
    const root = main.current;
    if (!root || !S) return;
    const spy = new IntersectionObserver(es => { for (const e of es) if (e.isIntersecting) setCurrent(e.target.id.slice(2)); }, { root, rootMargin: '-10% 0px -70% 0px' });
    root.querySelectorAll('section[id]').forEach(s => spy.observe(s));
    return () => spy.disconnect();
  }, [S]);

  const { THEME_NAMES, METHODS, SHORTCUTS, SECTIONS, SHOWS, MOMENTS } = words();
  // search: a setting shows when its words (or its section's title) match
  const match = (...ws: (string | undefined)[]) => !q.trim() || ws.some(w => w?.toLowerCase().includes(q.trim().toLowerCase()));
  const visible = useMemo(() => {
    const ws: Record<string, string[]> = {
      look: [T('حركة أقل', 'Less motion'), T('اللغة', 'Language'), 'English', 'عربي', ...Object.values(THEME_NAMES)], shows: SHOWS.flatMap(([, l, s]) => [l, s || '']),
      moments: [...MOMENTS.flatMap(([, l, s]) => [l, s || '']), T('لما البطارية توصل', 'battery saver at')],
      prayer: [T('المدينة', 'City'), T('الطريقة', 'Method'), T('العصر', 'Asr'), T('نبّهني قبلها', 'Alert me before'), T('نبّهني بمواعيد الصلاة', 'Prayer time alerts'), T('خط العرض', 'Latitude'), T('خط الطول', 'Longitude')],
      focus: [T('التركيز', 'Focus'), T('الراحة', 'Break'), T('الراحة الطويلة', 'Long break')], remind: [T('فكّرني', 'Remind me'), T('كل', 'Every'), T('ساعات هادية', 'Quiet hours')], meet: ['iCal', T('الرابط', 'Link'), T('تقويم', 'Calendar')],
      keys: [T('تنده على يوبي إزاي', 'Wake Yobi with'), T('النداء', 'wake word'), T('الزرار بس', 'Key only'), T('زرار النداء', 'Wake key'), T('اختصار', 'Shortcut'),T('الشاشة', 'Screen'), T('مكان الجزيرة', 'Island position'), T('على جنب', 'side edge'), T('شغّل يوبي لما أفتح الويندوز', 'Start Yobi with Windows')],
    };
    return Object.fromEntries(SECTIONS.map(s => [s.id, match(s.title, ...ws[s.id])]));
  }, [q, S?.island.lang]);   // match only reads q; the words follow the language

  if (!S) return <div dir={dir()} className="grid h-full place-items-center bg-[#0c0c0f] font-ui text-ink-2" aria-busy="true">{T('بجيب الإعدادات…', 'Loading settings…')}</div>;

  const sw = ([key, label, sub]: Sw) => (
    <Row key={key} label={label} sub={sub} hide={!match(label, sub, SECTIONS.find(s => s.id === 'shows')!.title, SECTIONS.find(s => s.id === 'moments')!.title)}>
      <Switch on={!!get(key)} onChange={v => put(key, v)} label={label} />
    </Row>
  );
  const city = S.cities.find(c => c.name === S.daily.city);
  const quiet = String(S.daily.quiet_hours || '');
  const [qFrom, qTo] = quiet ? quiet.split('-') : ['23:00', '07:00'];
  const accent = THEME_COLORS[String(S.island.theme)]?.[0] || '#3CC2B4';
  const MIN = T('دقيقة', 'min');
  const go = (id: string) => main.current?.querySelector(`#s-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const sections: Record<string, ReactNode> = {
    look: (
      <>
        <div className="grid grid-cols-5 gap-2.5" role="radiogroup" aria-label={T('شكل الجزيرة', 'Island theme')}>
          {S.themes.map(name => {
            const [a, g] = THEME_COLORS[name] || ['#3CC2B4', '#E3B04B'], on = S.island.theme === name;
            return (
              <button key={name} type="button" role="radio" aria-checked={on} onClick={() => save('island', { theme: name })}
                      className="flex flex-col items-center gap-2 rounded-[14px] p-2.5 text-[12px] transition-colors"
                      style={on ? { background: `${a}1f`, boxShadow: `inset 0 0 0 1.5px ${a}` } : { background: 'rgba(255,255,255,.04)' }}>
                <span className="flex h-7 w-20 items-center gap-1.5 rounded-full bg-black px-2.5"><i className="h-1 flex-1 rounded-full" style={{ background: a }} /><i className="size-1.5 rounded-full" style={{ background: g }} /></span>
                {THEME_NAMES[name] || name}
              </button>
            );
          })}
        </div>
        <Group>
          <Row label={T('اللغة', 'Language')} sub={T('كلام الجزيرة والإعدادات', 'The island’s and settings’ words')}>
            <span className="flex rounded-[10px] bg-white/[.07] p-0.5 ring-1 ring-white/10" role="radiogroup" aria-label={T('اللغة', 'Language')}>
              {([['ar', 'عربي'], ['en', 'English']] as const).map(([v, l]) => (
                <button key={v} type="button" role="radio" aria-checked={(S.island.lang || 'ar') === v} onClick={() => put('island.lang', v)}
                        className={`rounded-[8px] px-3 py-1 text-[12.5px] ${(S.island.lang || 'ar') === v ? 'bg-accent font-semibold text-island' : 'text-ink-2 hover:text-ink'}`}>{l}</button>
              ))}
            </span>
          </Row>
          <Row label={T('حركة أقل', 'Less motion')} sub={T('من غير موجات ونبض، والكلام بيظهر مرة واحدة', 'No waves or pulses, and text appears at once')}><Switch on={!!S.island.reduce_motion} onChange={v => put('island.reduce_motion', v)} label={T('حركة أقل', 'Less motion')} /></Row>
        </Group>
      </>
    ),
    shows: <Group>{SHOWS.map(sw)}</Group>,
    moments: (
      <Group>
        {MOMENTS.map(sw)}
        <Row label={T('توفير البطارية لما توصل', 'Battery saver at')} hide={!match(T('لما البطارية توصل', 'battery saver at'), SECTIONS[2].title)}>
          <NumberBox value={S.island.battery_saver_at} min={10} max={100} unit={T('٪', '%')} label={T('نسبة توفير البطارية', 'Battery saver level')} onSave={v => put('island.battery_saver_at', v)} />
        </Row>
      </Group>
    ),
    prayer: (
      <Group>
        <Row label={T('المدينة', 'City')}>
          <select className={field} aria-label={T('المدينة', 'City')} value={city ? city.name : '__other'} onChange={e => {
            const c = S.cities.find(x => x.name === e.target.value);
            if (c) save('daily', { city: c.name, lat: c.lat, lon: c.lon, method: c.method });
            else save('daily', { city: 'مكان تاني' });
          }}>
            {S.cities.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
            <option value="__other">{T('مكان تاني (اكتب الإحداثيات)', 'Somewhere else (enter coordinates)')}</option>
          </select>
        </Row>
        {!city && <Row label={T('خط العرض', 'Latitude')}><NumberBox value={S.daily.lat} min={-66} max={66} step={0.0001} label={T('خط العرض', 'Latitude')} onSave={v => put('daily.lat', v)} /></Row>}
        {!city && <Row label={T('خط الطول', 'Longitude')}><NumberBox value={S.daily.lon} min={-180} max={180} step={0.0001} label={T('خط الطول', 'Longitude')} onSave={v => put('daily.lon', v)} /></Row>}
        <Row label={T('طريقة الحساب', 'Calculation method')}>
          <select className={`${field} max-w-64`} aria-label={T('طريقة الحساب', 'Calculation method')} value={String(S.daily.method)} onChange={e => put('daily.method', e.target.value)}>
            {(S.methods || Object.keys(METHODS)).map(m => <option key={m} value={m}>{METHODS[m] || m}</option>)}
          </select>
        </Row>
        <Row label={T('العصر', 'Asr')}>
          <select className={field} aria-label={T('العصر', 'Asr')} value={String(S.daily.asr)} onChange={e => put('daily.asr', e.target.value)}>
            <option value="standard">{T('الجمهور (شافعي، مالكي، حنبلي)', 'Standard (Shafi‘i, Maliki, Hanbali)')}</option><option value="hanafi">{T('الحنفي', 'Hanafi')}</option>
          </select>
        </Row>
        <Row label={T('نبّهني قبلها بـ', 'Alert me before by')}><NumberBox value={S.daily.prayer_soon_min} min={0} max={30} unit={MIN} label={T('التنبيه قبل الصلاة', 'Alert before the prayer')} onSave={v => put('daily.prayer_soon_min', v)} /></Row>
        <Row label={T('نبّهني بمواعيد الصلاة', 'Prayer time alerts')}><Switch on={!!S.daily.prayer_alerts} onChange={v => put('daily.prayer_alerts', v)} label={T('نبّهني بمواعيد الصلاة', 'Prayer time alerts')} /></Row>
      </Group>
    ),
    focus: (
      <>
        <Group>
          <Row label={T('التركيز', 'Focus')}><NumberBox value={S.daily.focus_min} min={5} max={120} unit={MIN} label={T('مدة التركيز', 'Focus length')} onSave={v => put('daily.focus_min', v)} /></Row>
          <Row label={T('الراحة', 'Break')}><NumberBox value={S.daily.break_min} min={1} max={60} unit={MIN} label={T('مدة الراحة', 'Break length')} onSave={v => put('daily.break_min', v)} /></Row>
          <Row label={T('الراحة الطويلة', 'Long break')} sub={T('كل رابع راحة بتبقى طويلة', 'Every fourth break is a long one')}><NumberBox value={S.daily.long_break_min} min={5} max={60} unit={MIN} label={T('مدة الراحة الطويلة', 'Long break length')} onSave={v => put('daily.long_break_min', v)} /></Row>
        </Group>
      </>
    ),
    remind: (
      <Group>
        <Row label={T('فكّرني بذكر أو دعاء أو آية', 'Remind me with a dhikr, dua or verse')}><Switch on={!!S.daily.reminders} onChange={v => put('daily.reminders', v)} label={T('فكّرني', 'Remind me')} /></Row>
        {([['ayah', T('آيات', 'Verses')], ['dua', T('أدعية', 'Du’as')], ['dhikr', T('أذكار', 'Dhikr')]] as const).map(([k, l]) => (
          <Row key={k} label={l} sub={k === 'ayah' ? T('بالرسم العثماني من مجمع الملك فهد', 'In the Uthmani script of the King Fahd Complex') : undefined}>
            <Switch on={S.daily[`remind_${k}`] !== false} onChange={v => put(`daily.remind_${k}`, v)} label={l} />
          </Row>
        ))}
        <Row label={T('كل', 'Every')}><NumberBox value={S.daily.remind_every_min} min={1} max={240} unit={MIN} label={T('كل كام دقيقة', 'Every how many minutes')} onSave={v => put('daily.remind_every_min', v)} /></Row>
        <Row label={T('وتفضل ظاهرة', 'Shown for')}><NumberBox value={S.daily.remind_for_s} min={5} max={300} unit={T('ثانية', 'seconds')} label={T('تفضل ظاهرة كام ثانية', 'Shown for how many seconds')} onSave={v => put('daily.remind_for_s', v)} /></Row>
        <Row label={T('ساعات هادية من غير تذكير', 'Quiet hours without reminders')}><Switch on={!!quiet} onChange={v => save('daily', { quiet_hours: v ? `${qFrom}-${qTo}` : '' })} label={T('ساعات هادية', 'Quiet hours')} /></Row>
        {!!quiet && (
          <Row label={T('من … لحد', 'From … to')}>
            <span className="flex items-center gap-2 text-[12px] text-ink-2" dir="ltr">
              <input type="time" defaultValue={qFrom} key={`f${qFrom}`} aria-label={T('من', 'From')} className={field} onChange={e => e.target.value && save('daily', { quiet_hours: `${e.target.value}-${qTo}` })} />
              <span>→</span>
              <input type="time" defaultValue={qTo} key={`t${qTo}`} aria-label={T('لحد', 'To')} className={field} onChange={e => e.target.value && save('daily', { quiet_hours: `${qFrom}-${e.target.value}` })} />
            </span>
          </Row>
        )}
      </Group>
    ),
    meet: (
      <>
        <p className="m-0 text-[12px] leading-relaxed text-ink-2">{T('حط الرابط السري بصيغة iCal من تقويم جوجل أو Outlook، ويوبي هينبهك قبل كل اجتماع بخمس دقايق. الرابط بيتحفظ على جهازك بس.', 'Paste the secret iCal link from Google Calendar or Outlook, and Yobi will alert you five minutes before each meeting. The link stays on this PC.')}</p>
        <div className="flex gap-2">
          <input type={showIcal ? 'text' : 'password'} value={ical} onChange={e => setIcal(e.target.value)} dir="ltr" autoComplete="off" spellCheck={false}
                 placeholder="https://calendar.google.com/calendar/ical/…/basic.ics" aria-label={T('رابط iCal', 'iCal link')} className={`${field} min-w-0 flex-1`} />
          <button type="button" onClick={() => setShowIcal(!showIcal)} className="rounded-[9px] bg-white/[.07] px-3 text-[12.5px] hover:bg-white/[.12]">{showIcal ? T('إخفاء', 'Hide') : T('إظهار', 'Show')}</button>
          <button type="button" className="rounded-[9px] bg-accent px-4 text-[12.5px] font-semibold text-island" onClick={() => {
            const v = ical.trim();
            if (v && !/^(https|webcal):\/\/\S+$/i.test(v)) { flash(T('الرابط لازم يبدأ بـ https://', 'The link must start with https://')); return; }
            save('daily', { calendar_ical: v });
          }}>{T('احفظ', 'Save')}</button>
        </div>
      </>
    ),
    keys: (
      <>
        <Group>
          <Row label={T('تنده على يوبي إزاي', 'Wake Yobi with')} sub={T('بالزرار بس: مفيش حاجة بتسمعك وهو نايم، وبيوفّر ذاكرة كارت الشاشة', 'Key only: nothing listens while Yobi sleeps, and it saves graphics memory')}>
            <select className={field} aria-label={T('تنده على يوبي إزاي', 'Wake Yobi with')} value={String(S.island.wake || 'voice')} onChange={e => put('island.wake', e.target.value)}>
              <option value="voice">{T('الصوت «يا يوبي» أو الزرار', 'Voice “Ya Yobi” or the key')}</option>
              <option value="key">{T('الزرار بس ({k})', 'Key only ({k})').replace('{k}', showKey(wakeKey))}</option>
            </select>
          </Row>
          <Row label={T('زرار النداء', 'Wake key')} sub={T('الزرار اللي يخلّي يوبي يسمعك. دوس هنا وبعدين دوس أي زرار تختاره', 'The key that makes Yobi listen. Click here, then press any key you like')}>
            <KeyPicker value={wakeKey} taken={String(S.island.shortcut ?? '').toLowerCase()} label={T('زرار النداء', 'Wake key')} onPick={k => put('island.wake_key', k)} />
          </Row>
          <Row label={T('اختصار فتح الجزيرة', 'Shortcut to open the island')}>
            <select className={field} aria-label={T('اختصار فتح الجزيرة', 'Shortcut to open the island')} value={String(S.island.shortcut ?? '')} onChange={e => put('island.shortcut', e.target.value)} dir="ltr">
              {SHORTCUTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Row>
          <Row label={T('الجزيرة تظهر على', 'Show the island on')}>
            <select className={field} aria-label={T('الجزيرة تظهر على', 'Show the island on')} value={String(S.island.display || 'primary')} onChange={e => put('island.display', e.target.value)}>
              <option value="primary">{T('الشاشة الرئيسية', 'The main screen')}</option>
              <option value="cursor">{T('الشاشة اللي فيها الماوس', 'The screen with the mouse')}</option>
              {screens.length > 1 && screens.map(d => (
                <option key={d.id} value={d.id}>{`${T('شاشة', 'Screen')} ${d.n} (${d.w}×${d.h}${d.scale !== 1 ? `${T('، ', ', ')}${fmt.pct(d.scale * 100)}` : ''})${d.primary ? T(' — الرئيسية', ' — main') : ''}`}</option>
              ))}
            </select>
          </Row>
          <Row label={T('مكان الجزيرة', 'Island position')} sub={T('على جنب: شريط طويل على حافة الشاشة، بيفتح لجوّه', 'On a side: a tall strip on the screen’s edge that opens inward')}>
            <select className={field} aria-label={T('مكان الجزيرة', 'Island position')} value={String(S.island.position || 'top')} onChange={e => put('island.position', e.target.value)}>
              <option value="top">{T('فوق في النص', 'Top centre')}</option>
              <option value="right">{T('على الحافة اليمين', 'Right edge')}</option>
              <option value="left">{T('على الحافة الشمال', 'Left edge')}</option>
            </select>
          </Row>
          <Row label={T('شغّل يوبي لما أفتح الويندوز', 'Start Yobi with Windows')} sub={T('لحسابك بس، ومن غير شباك أسود', 'For your account only, with no black window')}><Switch on={!!S.island.autostart} onChange={v => put('island.autostart', v)} label={T('شغّل يوبي مع الويندوز', 'Start Yobi with Windows')} /></Row>
        </Group>
        <p className="m-0 text-[12px] leading-relaxed text-ink-3">{T('بعد الاختصار: الأسهم يمين وشمال بتقلّب الصفحات، و Tab بيتنقل بين الأزرار، و Esc بيقفل. اتكلم مع يوبي من غير ما تنده: {k}.', 'After the shortcut: the left and right arrows flip pages, Tab moves between buttons, and Esc closes. Talk to Yobi without the wake word: {k}.').replace('{k}', showKey(wakeKey))}</p>
      </>
    ),
  };

  return (
    <div dir={dir()} className="flex h-full bg-[#0c0c0f] font-ui text-ink">
      <nav aria-label={T('أقسام الإعدادات', 'Settings sections')} className="flex w-60 shrink-0 flex-col gap-1 border-s border-white/5 bg-white/[.02] p-3">
        <b className="mb-2 px-2 font-display text-[17px]">{T('إعدادات يوبي', 'Yobi settings')}</b>
        <label className="mb-2 flex items-center gap-2 rounded-[10px] bg-white/[.06] px-2.5 py-1.5 text-[12.5px] focus-within:ring-1 focus-within:ring-accent/70">
          <Search className="size-3.5 text-ink-3" aria-hidden="true" />
          <input type="search" value={q} onChange={e => setQ(e.target.value)} placeholder={T('دوّر في الإعدادات…', 'Search settings…')} aria-label={T('دوّر في الإعدادات', 'Search settings')} className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-ink-3" />
        </label>
        {SECTIONS.filter(s => visible[s.id]).map(({ id, title, icon: I, color }) => (
          <button key={id} type="button" onClick={() => go(id)} aria-current={current === id}
                  className={`flex items-center gap-2.5 rounded-[10px] px-2 py-1.5 text-start text-[13px] transition-colors ${current === id ? 'bg-white/[.09]' : 'hover:bg-white/[.05]'}`}>
            <span className="grid size-6 place-items-center rounded-[7px]" style={{ background: color }}><I className="size-3.5 text-white" /></span>{title}
          </button>
        ))}
        {!SECTIONS.some(s => visible[s.id]) && <p className="m-0 px-2 text-[12px] text-ink-3">{T('مفيش إعداد بالاسم ده', 'No setting by that name')}</p>}
        <p role="status" aria-live="polite" className="m-0 mt-auto px-2 text-[12.5px] font-semibold text-accent">{saved}</p>
      </nav>
      <main ref={main} className="min-w-0 flex-1 overflow-y-auto">
        {/* the island, live, in the chosen theme */}
        <div className="sticky top-0 z-10 grid place-items-center bg-[#0c0c0f]/85 py-5 backdrop-blur" style={{ backgroundImage: `radial-gradient(circle at 50% 140%, ${accent}33, transparent 60%)` }}>
          <div className="flex items-center gap-3 rounded-full bg-black px-4 py-2.5 shadow-[0_8px_24px_rgba(0,0,0,.5)] ring-1 ring-white/5" style={{ width: 280 }}>
            <span className="flex-1 text-[13px] font-semibold">{T('تمام، فتحت ديسكورد', 'Done, Discord is open')}</span>
            <Bars level={0.7} />
          </div>
        </div>
        <div className="mx-auto flex max-w-[640px] flex-col gap-8 px-8 pb-16">
          {SECTIONS.filter(s => visible[s.id]).map(({ id, title, icon: I, color, tryIt }) => (
            <section key={id} id={`s-${id}`} className="flex scroll-mt-24 flex-col gap-3">
              <h2 className="m-0 flex items-center gap-2.5 font-display text-[17px]">
                <span className="grid size-7 place-items-center rounded-[8px]" style={{ background: color }}><I className="size-4 text-white" /></span>{title}
              </h2>
              {sections[id]}
              {tryIt && (
                <button type="button" onClick={() => bridge.send({ t: 'preview', what: tryIt[0] })}
                        className="flex items-center gap-1.5 self-start rounded-full px-4 py-1.5 text-[12.5px] font-semibold text-island" style={{ background: color }}>
                  <Bell className="size-3.5" />{tryIt[1]}
                </button>
              )}
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}
