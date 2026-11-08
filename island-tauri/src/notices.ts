// Notices (interface 6), outside React: which ones show and for how long, the chime, the hover hold,
// the buttons' actions, and the history. Each kind's words, colour and icon live in `noticeLook`.
import {
  BookOpen, Calculator, Camera, CircleCheck, Clock, Coffee, Hand, HandHeart, Link2, MoonStar, Palette,
  PartyPopper, Sparkles, Sunrise, Timer, Type, Video, type LucideIcon,
} from 'lucide-react';
import { bridge } from './bridge';
import { remember, useIsland, type IslandStore } from './store';
import { tone } from './turn';
import { radioStop } from './radio';
import { PRAYER, T, WEATHER, fmt } from './i18n';
import type { NoticeMsg } from './types';

export interface NoticeLook {
  icon: LucideIcon; color: string; kind: string; text: string; sub: string;
  buttons: [string, string][]; ms: number; tones: number[]; swatch?: string; thumb?: string;
  /** a dhikr, du'a or verse: big, centred, in the Qur'an font; quran adds the ornate brackets and verse-end marks */
  ayah?: boolean; quran?: boolean;
}
export interface ShownNotice { msg: NoticeMsg; look: NoticeLook; at: number; total: number; until: number; paused: boolean; left: number }

const GOLD = 'var(--color-gold)', TEAL = 'var(--color-accent)', GREEN = '#7BD88F', BLUE = '#7FA8FF', VIOLET = '#C792EA', SUN = '#F0A43A';
const OK = (): [string, string] => [T('تمام', 'OK'), 'dismiss'];

/** what a notice says and how it looks; null for a kind (or a smart copy) the island doesn't show.
 *  The words come from here in the island's language; dhikr and ayat stay in Arabic. */
export function noticeLook(m: NoticeMsg, s: IslandStore): NoticeLook | null {
  const n = m as Record<string, any>;                       // Python's fields are loose JSON
  const at = n.at ? fmt.clock(new Date(n.at)) : '';
  const base = { sub: '', buttons: [] as [string, string][], ms: 8000, tones: [520] };
  const prayerKind = T('الصلاة', 'Prayer'), focusKind = T('تركيز', 'Focus');
  switch (m.kind) {
    case 'adhan': return { ...base, icon: MoonStar, color: GOLD, kind: prayerKind,
      text: T(`حان الآن موعد صلاة ${PRAYER(n.prayer)}`, `It's time for ${PRAYER(n.prayer)}`),
      sub: at + (s.prayer?.city ? ` · ${s.prayer.city}` : ''), ms: 15000, tones: [523, 659] };
    case 'prayer_soon': return { ...base, icon: Clock, color: GOLD, kind: prayerKind,
      text: T(`${PRAYER(n.prayer)} بعد ${fmt.num(n.minutes)} دقايق`, `${PRAYER(n.prayer)} in ${n.minutes} minutes`), sub: at, ms: 6000 };
    case 'focus_done': return { ...base, icon: PartyPopper, color: TEAL, kind: focusKind,
      text: T(`خلصت جلسة التركيز ${fmt.num(n.round)} 👏`, `Focus session ${n.round} done 👏`),
      sub: T(`الراحة بدأت: ${fmt.num(n.next_min)} دقايق`, `Break started: ${n.next_min} minutes`), tones: [659, 784] };
    case 'break_done': return { ...base, icon: Timer, color: TEAL, kind: focusKind, text: T('الراحة خلصت', 'Break’s over'), sub: T('نرجع نركّز؟', 'Back to focus?'),
      buttons: [[T(`ابدأ ${fmt.num(n.focus_min)} د`, `Start ${n.focus_min} min`), 'focus_start'], [T('مش دلوقتي', 'Not now'), 'dismiss']], ms: 30000 };
    case 'reminder': return { ...base, icon: n.sub === 'ayah' ? BookOpen : n.sub === 'dua' ? HandHeart : Sparkles,
      color: n.sub === 'ayah' ? '#FFD479' : n.sub === 'dua' ? '#A78BFA' : '#5EEAD4',      // each kind its own colour
      kind: ({ dhikr: T('ذكر', 'Dhikr'), dua: T('دعاء', 'Du’a'), ayah: T('آية', 'Ayah') } as Record<string, string>)[n.sub] || '',
      text: n.text, sub: n.ref || '', ms: (n.seconds || 20) * 1000, tones: [], ayah: true, quran: n.sub === 'ayah' || !!n.quran };
    case 'meeting': return { ...base, icon: Video, color: BLUE, kind: T('اجتماع', 'Meeting'), text: n.title,
      sub: T(`الساعة ${at} — بعد ٥ دقايق`, `At ${at} — in 5 minutes`),
      buttons: n.has_link ? [[T('انضم', 'Join'), 'join'], OK()] : [OK()], ms: 60000 };
    case 'download_done': return { ...base, icon: CircleCheck, color: TEAL, kind: T('اتحمّل', 'Downloaded'), text: n.name, sub: n.size ? fmt.bytes(n.size) : '',
      buttons: [[T('افتح', 'Open'), 'dl_open'], [T('وريني مكانه', 'Show in folder'), 'dl_folder'], OK()], ms: 9000, tones: [587, 784] };
    case 'smart': {
      const q = { ...base, tones: [], ms: 6000, color: VIOLET };
      if (n.what === 'link') return { ...q, icon: Link2, kind: T('لينك اتنسخ', 'Link copied'), text: n.value.length > 60 ? n.value.slice(0, 57) + '…' : n.value, buttons: [[T('افتحه', 'Open it'), 'open_link'], OK()] };
      if (n.what === 'color') return { ...q, icon: Palette, color: n.value, kind: T('لون اتنسخ', 'Color copied'), text: n.value, swatch: n.value };
      if (n.what === 'math') return { ...q, icon: Calculator, kind: T('حسبتها', 'Worked it out'), text: `= ${fmt.num(Number(n.result))}`, sub: n.value, buttons: [[T('انسخ الناتج', 'Copy result'), 'copy_result'], OK()] };
      if (n.what === 'count') return { ...q, icon: Type, kind: T('نص طويل', 'Long text'), text: T(`${fmt.num(n.words)} كلمة`, `${n.words} words`), sub: T(`${fmt.num(n.chars)} حرف`, `${n.chars} characters`) };
      return null;
    }
    case 'brief': {
      const lines: string[] = [];
      if (n.weather) lines.push(T(`الجو ${fmt.num(n.weather.temp)}° ${WEATHER(n.weather.code)}، والعظمى ${fmt.num(n.weather.hi)}°`, `${n.weather.temp}° ${WEATHER(n.weather.code)}, high of ${n.weather.hi}°`));
      if (n.next) lines.push(T(`${PRAYER(n.next.prayer)} الساعة ${fmt.clock(new Date(n.next.at))}`, `${PRAYER(n.next.prayer)} at ${fmt.clock(new Date(n.next.at))}`));
      if (n.meetings) {
        const first = fmt.clock(new Date(n.first_meeting.start));
        lines.push(n.meetings === 1 ? T(`عندك اجتماع النهارده: ${n.first_meeting.title} ${first}`, `One meeting today: ${n.first_meeting.title} at ${first}`)
          : T(`عندك ${fmt.num(n.meetings)} اجتماعات النهارده، أولهم ${first}`, `${n.meetings} meetings today, the first at ${first}`));
      }
      return { ...base, icon: Sunrise, color: SUN, kind: fmt.hijri(new Date(), true), text: n.greet, sub: lines.join('\n'), ms: 14000, tones: [523, 659] };
    }
    case 'welcome': return { ...base, icon: Hand, color: SUN, kind: T(`غبت ${fmt.span(n.away_min)}`, `Away ${fmt.span(n.away_min)}`), text: T('أهلا رجعت 👋', 'Welcome back 👋'), sub: (n.events || []).join('\n'), ms: 10000, tones: [523] };
    case 'care': return { ...base, icon: Coffee, color: GREEN, kind: T('خد بريك', 'Take a break'), text: n.title, sub: n.text, buttons: [OK()], ms: 15000, tones: [] };
    case 'screenshot': return { ...base, icon: Camera, color: BLUE, kind: n.h > n.w ? T('صورة اتنسخت', 'Image copied') : T('لقطة شاشة', 'Screenshot'), text: '',
      sub: `${fmt.num(n.w)}×${fmt.num(n.h)}`, thumb: n.thumb, buttons: [[T('احفظ على الرف', 'Save to shelf'), 'shot_save'], OK()], ms: 7000, tones: [] };
    default: return null;
  }
}

const get = () => useIsland.getState();
let timer: ReturnType<typeof setTimeout> | undefined;

function schedule() {
  clearTimeout(timer);
  const n = get().notice;
  if (!n || n.paused) return;
  timer = setTimeout(endNotice, Math.max(0, n.until - Date.now()) + 20);
}
export function endNotice() { clearTimeout(timer); useIsland.setState({ notice: null }); }

/** a notice from Python */
export function showNotice(m: NoticeMsg) {
  const s = get(), now = Date.now();
  const showing = !!s.notice && s.notice.until > now;
  // a Yobi turn keeps the island; a gentle reminder also waits for the panel and another notice
  if (s.state !== 'idle' || (m.kind === 'reminder' && (s.panel.open || showing))) {
    if (m.kind === 'reminder') bridge.send({ t: 'notice_dropped', kind: 'reminder' });   // Python tries again later
    return;
  }
  const look = noticeLook(m, s);
  if (!look) return;
  if (m.kind === 'adhan' && s.radio.playing && s.prefs.radio_pause_prayer !== false) radioStop(T('وقفت الإذاعة عشان الأذان', 'Paused the radio for the adhan'));
  const keep = !['reminder', 'smart', 'screenshot'].includes(m.kind);   // the history keeps what Yobi told you
  useIsland.setState({
    notice: { msg: m, look, at: now, total: look.ms, until: now + look.ms, paused: false, left: look.ms },
    ...(keep ? { history: remember(s.history, 'notice', [look.text, look.sub.split('\n')[0]].filter(Boolean).join(' — '), look.kind) } : {}),
    ...(s.prefs.celebrate && (m.kind === 'focus_done' || m.kind === 'download_done') ? { celebrateAt: now } : {}),
  });
  if (look.tones.length) tone(look.tones[0], look.tones[1]);
  schedule();
}

/** the pointer on the island keeps a notice readable; leaving gives it at least 1.5 s more */
export function holdNotice(on: boolean) {
  const n = get().notice;
  if (!n) return;
  if (on && !n.paused) { clearTimeout(timer); useIsland.setState({ notice: { ...n, paused: true, left: n.until - Date.now() } }); }
  else if (!on && n.paused) { useIsland.setState({ notice: { ...n, paused: false, until: Date.now() + Math.max(1500, n.left) } }); schedule(); }
}

/** a notice's button */
export function noticeAction(action: string) {
  const n = get().notice;
  if (!n) return;
  const msg = n.msg as Record<string, any>;
  if (action === 'join') bridge.send({ t: 'meeting_join', id: msg.id });
  else if (action === 'dl_open' || action === 'dl_folder') bridge.send({ t: action, id: msg.id });
  else if (action === 'open_link' || action === 'copy_result') bridge.send({ t: 'smart_action', action, value: String(action === 'open_link' ? msg.value : msg.result) });
  else if (action !== 'dismiss') bridge.send({ t: 'notice_action', action });
  endNotice();
}
