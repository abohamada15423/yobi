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
import type { NoticeMsg } from './types';

export interface NoticeLook {
  icon: LucideIcon; color: string; kind: string; text: string; sub: string;
  buttons: [string, string][]; ms: number; tones: number[]; swatch?: string; thumb?: string; ayah?: boolean;
}
export interface ShownNotice { msg: NoticeMsg; look: NoticeLook; at: number; total: number; until: number; paused: boolean; left: number }

const nf = new Intl.NumberFormat('ar-EG');
const clockFmt = new Intl.DateTimeFormat('ar-EG', { hour: 'numeric', minute: '2-digit' });
const hijriFmt = new Intl.DateTimeFormat('ar-EG-u-ca-islamic-umalqura', { day: 'numeric', month: 'long', year: 'numeric' });
const PRAYER: Record<string, string> = { fajr: 'الفجر', sunrise: 'الشروق', dhuhr: 'الظهر', asr: 'العصر', maghrib: 'المغرب', isha: 'العشاء' };
const WX = (c: number) => c === 0 ? 'صافي' : c <= 2 ? 'غائم جزئيًا' : c === 3 ? 'غائم' : c <= 48 ? 'شبورة' : c <= 57 ? 'رذاذ'
  : c <= 67 ? 'مطر' : c <= 77 ? 'تلج' : c <= 82 ? 'زخات مطر' : c <= 86 ? 'زخات تلج' : 'عاصفة رعدية';
const fmtBytes = (b: number) => b >= 1e9 ? `${nf.format(+(b / 1e9).toFixed(1))} ج.ب` : b >= 1e6 ? `${nf.format(+(b / 1e6).toFixed(1))} م.ب` : `${nf.format(Math.round(b / 1e3))} ك.ب`;
/** "١ س ٢٠ د" */
const span = (min: number) => { const m = Math.max(1, Math.round(min)), h = Math.floor(m / 60), r = m % 60; return h ? `${nf.format(h)} س` + (r ? ` ${nf.format(r)} د` : '') : `${nf.format(r)} د`; };

const GOLD = 'var(--color-gold)', TEAL = 'var(--color-accent)', GREEN = '#7BD88F', BLUE = '#7FA8FF', VIOLET = '#C792EA', SUN = '#F0A43A';

/** what a notice says and how it looks; null for a kind (or a smart copy) the island doesn't show */
export function noticeLook(m: NoticeMsg, s: IslandStore): NoticeLook | null {
  const n = m as Record<string, any>;                       // Python's fields are loose JSON
  const at = n.at ? clockFmt.format(new Date(n.at)) : '';
  const base = { sub: '', buttons: [] as [string, string][], ms: 8000, tones: [520] };
  switch (m.kind) {
    case 'adhan': return { ...base, icon: MoonStar, color: GOLD, kind: 'الصلاة', text: `حان الآن موعد صلاة ${PRAYER[n.prayer] || ''}`,
      sub: at + (s.prayer?.city ? ` · ${s.prayer.city}` : ''), ms: 15000, tones: [523, 659] };
    case 'prayer_soon': return { ...base, icon: Clock, color: GOLD, kind: 'الصلاة', text: `${PRAYER[n.prayer] || ''} بعد ${nf.format(n.minutes)} دقايق`, sub: at, ms: 6000 };
    case 'focus_done': return { ...base, icon: PartyPopper, color: TEAL, kind: 'تركيز', text: `خلصت جلسة التركيز ${nf.format(n.round)} 👏`,
      sub: `الراحة بدأت: ${nf.format(n.next_min)} دقايق`, tones: [659, 784] };
    case 'break_done': return { ...base, icon: Timer, color: TEAL, kind: 'تركيز', text: 'الراحة خلصت', sub: 'نرجع نركّز؟',
      buttons: [[`ابدأ ${nf.format(n.focus_min)} د`, 'focus_start'], ['مش دلوقتي', 'dismiss']], ms: 30000 };
    case 'reminder': return { ...base, icon: n.sub === 'ayah' ? BookOpen : n.sub === 'dua' ? HandHeart : Sparkles, color: GREEN,
      kind: ({ dhikr: 'ذكر', dua: 'دعاء', ayah: 'آية' } as Record<string, string>)[n.sub] || '',
      text: n.sub === 'ayah' ? `﴿ ${n.text} ﴾` : n.text, sub: n.ref || '', ms: (n.seconds || 20) * 1000, tones: [], ayah: n.sub === 'ayah' };
    case 'meeting': return { ...base, icon: Video, color: BLUE, kind: 'اجتماع', text: n.title, sub: `الساعة ${at} — بعد ٥ دقايق`,
      buttons: n.has_link ? [['انضم', 'join'], ['تمام', 'dismiss']] : [['تمام', 'dismiss']], ms: 60000 };
    case 'download_done': return { ...base, icon: CircleCheck, color: TEAL, kind: 'اتحمّل', text: n.name, sub: n.size ? fmtBytes(n.size) : '',
      buttons: [['افتح', 'dl_open'], ['وريني مكانه', 'dl_folder'], ['تمام', 'dismiss']], ms: 9000, tones: [587, 784] };
    case 'smart': {
      const q = { ...base, tones: [], ms: 6000, color: VIOLET };
      if (n.what === 'link') return { ...q, icon: Link2, kind: 'لينك اتنسخ', text: n.value.length > 60 ? n.value.slice(0, 57) + '…' : n.value, buttons: [['افتحه', 'open_link'], ['تمام', 'dismiss']] };
      if (n.what === 'color') return { ...q, icon: Palette, color: n.value, kind: 'لون اتنسخ', text: n.value, swatch: n.value };
      if (n.what === 'math') return { ...q, icon: Calculator, kind: 'حسبتها', text: `= ${nf.format(Number(n.result))}`, sub: n.value, buttons: [['انسخ الناتج', 'copy_result'], ['تمام', 'dismiss']] };
      if (n.what === 'count') return { ...q, icon: Type, kind: 'نص طويل', text: `${nf.format(n.words)} كلمة`, sub: `${nf.format(n.chars)} حرف` };
      return null;
    }
    case 'brief': {
      const lines: string[] = [];
      if (n.weather) lines.push(`الجو ${nf.format(n.weather.temp)}° ${WX(n.weather.code)}، والعظمى ${nf.format(n.weather.hi)}°`);
      if (n.next) lines.push(`${PRAYER[n.next.prayer]} الساعة ${clockFmt.format(new Date(n.next.at))}`);
      if (n.meetings) lines.push(n.meetings === 1 ? `عندك اجتماع النهارده: ${n.first_meeting.title} ${clockFmt.format(new Date(n.first_meeting.start))}`
        : `عندك ${nf.format(n.meetings)} اجتماعات النهارده، أولهم ${clockFmt.format(new Date(n.first_meeting.start))}`);
      return { ...base, icon: Sunrise, color: SUN, kind: hijriFmt.format(new Date()), text: n.greet, sub: lines.join('\n'), ms: 14000, tones: [523, 659] };
    }
    case 'welcome': return { ...base, icon: Hand, color: SUN, kind: `غبت ${span(n.away_min)}`, text: 'أهلا رجعت 👋', sub: (n.events || []).join('\n'), ms: 10000, tones: [523] };
    case 'care': return { ...base, icon: Coffee, color: GREEN, kind: 'خد بريك', text: n.title, sub: n.text, buttons: [['تمام', 'dismiss']], ms: 15000, tones: [] };
    case 'screenshot': return { ...base, icon: Camera, color: BLUE, kind: n.h > n.w ? 'صورة اتنسخت' : 'لقطة شاشة', text: '',
      sub: `${nf.format(n.w)}×${nf.format(n.h)}`, thumb: n.thumb, buttons: [['احفظ على الرف', 'shot_save'], ['تمام', 'dismiss']], ms: 7000, tones: [] };
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
  if (m.kind === 'adhan' && s.radio.playing && s.prefs.radio_pause_prayer !== false) radioStop('وقفت الإذاعة عشان الأذان');
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
