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

type Sec = 'island' | 'daily';
interface City { name: string; lat: number; lon: number; method: string }
interface S { island: Record<string, unknown>; daily: Record<string, unknown>; themes: string[]; methods: string[]; cities: City[] }

const THEME_NAMES: Record<string, string> = { faience: 'فيروزي', night: 'ليل', papyrus: 'بردي', nile: 'نيل', carnelian: 'عقيق' };
const THEME_COLORS: Record<string, [string, string]> = {
  faience: ['#3CC2B4', '#E3B04B'], night: ['#45D0C1', '#E3B04B'], papyrus: ['#D8B56A', '#E3B04B'], nile: ['#7FD6C2', '#E3B04B'], carnelian: ['#E8A25B', '#E9C46A'],
};
const METHODS: Record<string, string> = {
  EGYPT: 'الهيئة المصرية العامة للمساحة', MAKKAH: 'أم القرى، مكة', MWL: 'رابطة العالم الإسلامي', KARACHI: 'جامعة العلوم الإسلامية، كراتشي', ISNA: 'أمريكا الشمالية (ISNA)',
};
const SHORTCUTS: [string, string][] = [['Ctrl+Alt+I', 'Ctrl + Alt + I'], ['Ctrl+Alt+Space', 'Ctrl + Alt + Space'], ['Ctrl+Shift+Space', 'Ctrl + Shift + Space'], ['Alt+Shift+Y', 'Alt + Shift + Y'], ['', 'من غير اختصار']];
const SECTIONS: { id: string; title: string; icon: LucideIcon; color: string; tryIt?: [string, string] }[] = [
  { id: 'look', title: 'الشكل', icon: Palette, color: '#C792EA', tryIt: ['reply', 'جرّب على الجزيرة'] },
  { id: 'shows', title: 'الجزيرة بتعرض إيه', icon: Eye, color: '#3CC2B4' },
  { id: 'moments', title: 'لحظات وإضافات', icon: Sparkles, color: '#F0A43A', tryIt: ['brief', 'جرّب صباح الخير'] },
  { id: 'prayer', title: 'الصلاة', icon: MoonStar, color: '#E3B04B', tryIt: ['adhan', 'جرّب تنبيه الأذان'] },
  { id: 'focus', title: 'التركيز', icon: Timer, color: '#5AA9FF' },
  { id: 'remind', title: 'الأذكار والأدعية والآيات', icon: BookOpen, color: '#7BD88F', tryIt: ['reminder', 'جرّب تذكير'] },
  { id: 'meet', title: 'الاجتماعات', icon: Calendar, color: '#7FA8FF' },
  { id: 'keys', title: 'الاختصار والشاشة', icon: Keyboard, color: '#A1A1A6' },
];
type Sw = [string, string, string?];   // key, label, small print
const SHOWS: Sw[] = [
  ['island.idle_clock', 'الساعة على الجزيرة وهي هادية'], ['island.music_tab', 'الأغنية اللي شغالة'], ['island.track_peek', 'اسم الأغنية لما تتغير'],
  ['island.downloads', 'التحميلات اللي في فولدر التحميلات'], ['island.screenshot_toast', 'لقطات الشاشة والصور اللي بتنسخها'],
  ['island.clipboard_history', 'سجل الحافظة', 'بيتحفظ في الذاكرة بس لحد ما يوبي يتقفل، وبيتجاهل كلمات السر'],
  ['island.privacy_dots', 'نقطة لما برنامج يستخدم المايك أو الكاميرا'],
  ['island.hide_fullscreen', 'تستخبى وقت الألعاب والأفلام اللي على الشاشة كلها', 'يوبي والأذان والاجتماعات بيظهروا برضه'],
];
const MOMENTS: Sw[] = [
  ['island.weather', 'الطقس في مدينة الصلاة'], ['island.net_toasts', 'قولّي لما النت يفصل أو يرجع'],
  ['island.smart_clipboard', 'الحافظة الذكية', 'لينك تفتحه، لون تشوفه، حسبة تتحل، أو عدد كلمات النص الطويل'],
  ['island.morning_brief', 'صباح الخير أول ما تقعد على الجهاز'], ['island.welcome_back', 'أهلا رجعت، باللي حصل وإنت مش موجود'],
  ['island.wellbeing', 'فكّرني آخد بريك بعد ٥٠ دقيقة شغل'], ['island.celebrate', 'احتفال صغير لما أكمّل هدف'],
  ['island.radio_pause_prayer', 'وقّف إذاعة القرآن وقت الأذان'], ['island.battery_saver', 'توفير البطارية: من غير حركة لما البطارية تقل'],
];

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

  const flash = (text = 'اتحفظ ✓') => { setSaved(text); clearTimeout(timer.current); timer.current = setTimeout(() => setSaved(''), 1800); };
  const save = (section: Sec, values: Record<string, unknown>) => bridge.send({ t: 'settings_set', section, values });
  const get = (key: string) => { const [s, k] = key.split('.') as [Sec, string]; return S?.[s]?.[k]; };
  const put = (key: string, v: unknown) => { const [s, k] = key.split('.') as [Sec, string]; save(s, { [k]: v }); };

  useEffect(() => {
    bridge.onMessage((m: InMsg) => {
      if (m.t === 'settings') { const s = m as unknown as S; setS(s); setIcal(String(s.daily.calendar_ical || '')); }
      else if (m.t === 'settings_saved') flash();
    });
    bridge.send({ t: 'settings_get' });
    void bridge.displays().then(setScreens);
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

  // search: a setting shows when its words (or its section's title) match
  const match = (...words: (string | undefined)[]) => !q.trim() || words.some(w => w?.includes(q.trim()));
  const visible = useMemo(() => {
    const words: Record<string, string[]> = {
      look: ['الشكل', 'حركة أقل', ...Object.values(THEME_NAMES)], shows: SHOWS.flatMap(([, l, s]) => [l, s || '']),
      moments: [...MOMENTS.flatMap(([, l, s]) => [l, s || '']), 'لما البطارية توصل'],
      prayer: ['المدينة', 'الطريقة', 'العصر', 'نبّهني قبلها', 'نبّهني بمواعيد الصلاة', 'خط العرض', 'خط الطول'],
      focus: ['التركيز', 'الراحة', 'الراحة الطويلة'], remind: ['فكّرني', 'كل', 'ساعات هادية'], meet: ['iCal', 'الرابط', 'تقويم'],
      keys: ['اختصار', 'الشاشة', 'شغّل يوبي لما أفتح الويندوز'],
    };
    return Object.fromEntries(SECTIONS.map(s => [s.id, match(s.title, ...words[s.id])]));
  }, [q]);   // match only reads q

  if (!S) return <div dir="rtl" className="grid h-full place-items-center bg-[#0c0c0f] font-ui text-ink-2" aria-busy="true">بجيب الإعدادات…</div>;

  const sw = ([key, label, sub]: Sw) => (
    <Row key={key} label={label} sub={sub} hide={!match(label, sub, SECTIONS.find(s => s.id === 'shows')!.title, SECTIONS.find(s => s.id === 'moments')!.title)}>
      <Switch on={!!get(key)} onChange={v => put(key, v)} label={label} />
    </Row>
  );
  const city = S.cities.find(c => c.name === S.daily.city);
  const quiet = String(S.daily.quiet_hours || '');
  const [qFrom, qTo] = quiet ? quiet.split('-') : ['23:00', '07:00'];
  const accent = THEME_COLORS[String(S.island.theme)]?.[0] || '#3CC2B4';
  const go = (id: string) => main.current?.querySelector(`#s-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  const sections: Record<string, ReactNode> = {
    look: (
      <>
        <div className="grid grid-cols-5 gap-2.5" role="radiogroup" aria-label="شكل الجزيرة">
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
        <Group><Row label="حركة أقل" sub="من غير موجات ونبض، والكلام بيظهر مرة واحدة"><Switch on={!!S.island.reduce_motion} onChange={v => put('island.reduce_motion', v)} label="حركة أقل" /></Row></Group>
      </>
    ),
    shows: <Group>{SHOWS.map(sw)}</Group>,
    moments: (
      <Group>
        {MOMENTS.map(sw)}
        <Row label="توفير البطارية لما توصل" hide={!match('لما البطارية توصل', 'لحظات وإضافات')}>
          <NumberBox value={S.island.battery_saver_at} min={10} max={100} unit="٪" label="نسبة توفير البطارية" onSave={v => put('island.battery_saver_at', v)} />
        </Row>
      </Group>
    ),
    prayer: (
      <Group>
        <Row label="المدينة">
          <select className={field} aria-label="المدينة" value={city ? city.name : '__other'} onChange={e => {
            const c = S.cities.find(x => x.name === e.target.value);
            if (c) save('daily', { city: c.name, lat: c.lat, lon: c.lon, method: c.method });
            else save('daily', { city: 'مكان تاني' });
          }}>
            {S.cities.map(c => <option key={c.name} value={c.name}>{c.name}</option>)}
            <option value="__other">مكان تاني (اكتب الإحداثيات)</option>
          </select>
        </Row>
        {!city && <Row label="خط العرض"><NumberBox value={S.daily.lat} min={-66} max={66} step={0.0001} label="خط العرض" onSave={v => put('daily.lat', v)} /></Row>}
        {!city && <Row label="خط الطول"><NumberBox value={S.daily.lon} min={-180} max={180} step={0.0001} label="خط الطول" onSave={v => put('daily.lon', v)} /></Row>}
        <Row label="طريقة الحساب">
          <select className={`${field} max-w-64`} aria-label="طريقة الحساب" value={String(S.daily.method)} onChange={e => put('daily.method', e.target.value)}>
            {(S.methods || Object.keys(METHODS)).map(m => <option key={m} value={m}>{METHODS[m] || m}</option>)}
          </select>
        </Row>
        <Row label="العصر">
          <select className={field} aria-label="العصر" value={String(S.daily.asr)} onChange={e => put('daily.asr', e.target.value)}>
            <option value="standard">الجمهور (شافعي، مالكي، حنبلي)</option><option value="hanafi">الحنفي</option>
          </select>
        </Row>
        <Row label="نبّهني قبلها بـ"><NumberBox value={S.daily.prayer_soon_min} min={0} max={30} unit="دقيقة" label="التنبيه قبل الصلاة" onSave={v => put('daily.prayer_soon_min', v)} /></Row>
        <Row label="نبّهني بمواعيد الصلاة"><Switch on={!!S.daily.prayer_alerts} onChange={v => put('daily.prayer_alerts', v)} label="نبّهني بمواعيد الصلاة" /></Row>
      </Group>
    ),
    focus: (
      <>
        <Group>
          <Row label="التركيز"><NumberBox value={S.daily.focus_min} min={5} max={120} unit="دقيقة" label="مدة التركيز" onSave={v => put('daily.focus_min', v)} /></Row>
          <Row label="الراحة"><NumberBox value={S.daily.break_min} min={1} max={60} unit="دقيقة" label="مدة الراحة" onSave={v => put('daily.break_min', v)} /></Row>
          <Row label="الراحة الطويلة" sub="كل رابع راحة بتبقى طويلة"><NumberBox value={S.daily.long_break_min} min={5} max={60} unit="دقيقة" label="مدة الراحة الطويلة" onSave={v => put('daily.long_break_min', v)} /></Row>
        </Group>
      </>
    ),
    remind: (
      <Group>
        <Row label="فكّرني بذكر أو دعاء أو آية"><Switch on={!!S.daily.reminders} onChange={v => put('daily.reminders', v)} label="فكّرني" /></Row>
        <Row label="كل"><NumberBox value={S.daily.remind_every_min} min={1} max={240} unit="دقيقة" label="كل كام دقيقة" onSave={v => put('daily.remind_every_min', v)} /></Row>
        <Row label="وتفضل ظاهرة"><NumberBox value={S.daily.remind_for_s} min={5} max={300} unit="ثانية" label="تفضل ظاهرة كام ثانية" onSave={v => put('daily.remind_for_s', v)} /></Row>
        <Row label="ساعات هادية من غير تذكير"><Switch on={!!quiet} onChange={v => save('daily', { quiet_hours: v ? `${qFrom}-${qTo}` : '' })} label="ساعات هادية" /></Row>
        {!!quiet && (
          <Row label="من … لحد">
            <span className="flex items-center gap-2 text-[12px] text-ink-2" dir="ltr">
              <input type="time" defaultValue={qFrom} key={`f${qFrom}`} aria-label="من" className={field} onChange={e => e.target.value && save('daily', { quiet_hours: `${e.target.value}-${qTo}` })} />
              <span>→</span>
              <input type="time" defaultValue={qTo} key={`t${qTo}`} aria-label="لحد" className={field} onChange={e => e.target.value && save('daily', { quiet_hours: `${qFrom}-${e.target.value}` })} />
            </span>
          </Row>
        )}
      </Group>
    ),
    meet: (
      <>
        <p className="m-0 text-[12px] leading-relaxed text-ink-2">حط الرابط السري بصيغة iCal من تقويم جوجل أو Outlook، ويوبي هينبهك قبل كل اجتماع بخمس دقايق. الرابط بيتحفظ على جهازك بس.</p>
        <div className="flex gap-2">
          <input type={showIcal ? 'text' : 'password'} value={ical} onChange={e => setIcal(e.target.value)} dir="ltr" autoComplete="off" spellCheck={false}
                 placeholder="https://calendar.google.com/calendar/ical/…/basic.ics" aria-label="رابط iCal" className={`${field} min-w-0 flex-1`} />
          <button type="button" onClick={() => setShowIcal(!showIcal)} className="rounded-[9px] bg-white/[.07] px-3 text-[12.5px] hover:bg-white/[.12]">{showIcal ? 'إخفاء' : 'إظهار'}</button>
          <button type="button" className="rounded-[9px] bg-accent px-4 text-[12.5px] font-semibold text-island" onClick={() => {
            const v = ical.trim();
            if (v && !/^(https|webcal):\/\/\S+$/i.test(v)) { flash('الرابط لازم يبدأ بـ https://'); return; }
            save('daily', { calendar_ical: v });
          }}>احفظ</button>
        </div>
      </>
    ),
    keys: (
      <>
        <Group>
          <Row label="اختصار فتح الجزيرة">
            <select className={field} aria-label="اختصار فتح الجزيرة" value={String(S.island.shortcut ?? '')} onChange={e => put('island.shortcut', e.target.value)} dir="ltr">
              {SHORTCUTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Row>
          <Row label="الجزيرة تظهر على">
            <select className={field} aria-label="الجزيرة تظهر على" value={String(S.island.display || 'primary')} onChange={e => put('island.display', e.target.value)}>
              <option value="primary">الشاشة الرئيسية</option>
              <option value="cursor">الشاشة اللي فيها الماوس</option>
              {screens.length > 1 && screens.map(d => (
                <option key={d.id} value={d.id}>{`شاشة ${d.n} (${d.w}×${d.h}${d.scale !== 1 ? `، ${Math.round(d.scale * 100)}٪` : ''})${d.primary ? ' — الرئيسية' : ''}`}</option>
              ))}
            </select>
          </Row>
          <Row label="شغّل يوبي لما أفتح الويندوز" sub="لحسابك بس، ومن غير شباك أسود"><Switch on={!!S.island.autostart} onChange={v => put('island.autostart', v)} label="شغّل يوبي مع الويندوز" /></Row>
        </Group>
        <p className="m-0 text-[12px] leading-relaxed text-ink-3">بعد الاختصار: الأسهم يمين وشمال بتقلّب الصفحات، و Tab بيتنقل بين الأزرار، و Esc بيقفل. اتكلم مع يوبي من غير ما تنده: Ctrl + Alt + Y.</p>
      </>
    ),
  };

  return (
    <div dir="rtl" className="flex h-full bg-[#0c0c0f] font-ui text-ink">
      <nav aria-label="أقسام الإعدادات" className="flex w-60 shrink-0 flex-col gap-1 border-s border-white/5 bg-white/[.02] p-3">
        <b className="mb-2 px-2 font-display text-[17px]">إعدادات يوبي</b>
        <label className="mb-2 flex items-center gap-2 rounded-[10px] bg-white/[.06] px-2.5 py-1.5 text-[12.5px] focus-within:ring-1 focus-within:ring-accent/70">
          <Search className="size-3.5 text-ink-3" aria-hidden="true" />
          <input type="search" value={q} onChange={e => setQ(e.target.value)} placeholder="دوّر في الإعدادات…" aria-label="دوّر في الإعدادات" className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-ink-3" />
        </label>
        {SECTIONS.filter(s => visible[s.id]).map(({ id, title, icon: I, color }) => (
          <button key={id} type="button" onClick={() => go(id)} aria-current={current === id}
                  className={`flex items-center gap-2.5 rounded-[10px] px-2 py-1.5 text-start text-[13px] transition-colors ${current === id ? 'bg-white/[.09]' : 'hover:bg-white/[.05]'}`}>
            <span className="grid size-6 place-items-center rounded-[7px]" style={{ background: color }}><I className="size-3.5 text-white" /></span>{title}
          </button>
        ))}
        {!SECTIONS.some(s => visible[s.id]) && <p className="m-0 px-2 text-[12px] text-ink-3">مفيش إعداد بالاسم ده</p>}
        <p role="status" aria-live="polite" className="m-0 mt-auto px-2 text-[12.5px] font-semibold text-accent">{saved}</p>
      </nav>
      <main ref={main} className="min-w-0 flex-1 overflow-y-auto">
        {/* the island, live, in the chosen theme */}
        <div className="sticky top-0 z-10 grid place-items-center bg-[#0c0c0f]/85 py-5 backdrop-blur" style={{ backgroundImage: `radial-gradient(circle at 50% 140%, ${accent}33, transparent 60%)` }}>
          <div className="flex items-center gap-3 rounded-full bg-black px-4 py-2.5 shadow-[0_8px_24px_rgba(0,0,0,.5)] ring-1 ring-white/5" style={{ width: 280 }}>
            <span className="flex-1 text-[13px] font-semibold">تمام، فتحت ديسكورد</span>
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
