// Design options for interface 2 (Yobi's turn). A review page only: ?turn
import { Check, Mic, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { YobiFace, type Look } from '../components/YobiFace';

type Variant = 'line' | 'card' | 'glow';
type Frame = { label: string; look: Look; status?: string; words?: string; tail?: 'mic' | 'dots' | 'ring' | 'ok' | 'err'; progress?: number; ask?: [string, boolean][] };

const FRAMES: Frame[] = [
  { label: 'سامعك', look: 'listening', status: 'سامعك.. اتكلم', tail: 'mic' },
  { label: 'بيفكّر', look: 'thinking', status: 'بفكر في طلبك…', tail: 'dots' },
  { label: 'بينفّذ', look: 'thinking', status: 'بفتح Discord', tail: 'ring', progress: 0.6 },
  { label: 'تمام', look: 'happy', words: 'تمام، فتحت ديسكورد', tail: 'ok' },
  { label: 'غلط', look: 'sad', words: 'مش لاقي البرنامج ده على الجهاز', tail: 'err' },
  { label: 'رد طويل', look: 'talking', words: 'الساعة ١٠:٤٥ بالليل. لو هتلعب كمان، اشرب مياه الأول وخد بريك صغير.' },
  { label: 'سؤال', look: 'question', words: 'قصدك Euro Truck Simulator 2 ولا Rocket League؟', ask: [['Euro Truck Simulator 2', true], ['Rocket League', false], ['لا، ولا حاجة', false]] },
];

function Bars({ n = 5 }: { n?: number }) {
  return <span className="flex h-4 items-center gap-[2px]">{[7, 13, 9, 15, 8].slice(0, n).map((h, i) => <i key={i} className="w-[3px] rounded-pill bg-accent" style={{ height: h }} />)}</span>;
}
function Tail({ f }: { f: Frame }) {
  if (f.tail === 'mic') return <Bars />;
  if (f.tail === 'dots') return <span className="flex gap-1">{[1, .6, .3].map((o, i) => <i key={i} className="size-1.5 rounded-pill bg-ink-2" style={{ opacity: o }} />)}</span>;
  if (f.tail === 'ok') return <Check className="size-4 text-gold" strokeWidth={2.6} />;
  if (f.tail === 'err') return <X className="size-4 text-alert" strokeWidth={2.6} />;
  if (f.tail === 'ring') {
    const c = 2 * Math.PI * 7;
    return <svg className="size-4 -rotate-90" viewBox="0 0 18 18"><circle cx="9" cy="9" r="7" fill="none" stroke="var(--color-line)" strokeWidth="2.2" /><circle cx="9" cy="9" r="7" fill="none" stroke="var(--color-accent)" strokeWidth="2.2" strokeLinecap="round" strokeDasharray={`${c * (f.progress ?? 0)} ${c}`} /></svg>;
  }
  return null;
}
function Choices({ ask }: { ask: [string, boolean][] }) {
  return (
    <div className="flex flex-wrap gap-2">
      {ask.map(([t, main]) => <span key={t} dir="auto" className={`rounded-pill px-3.5 py-1.5 text-[12px] font-semibold ${main ? 'bg-gold text-island' : 'bg-fill-1 text-ink'}`}>{t}</span>)}
    </div>
  );
}
const shell = (w: number, children: ReactNode, card = false) => (
  <div className="relative overflow-hidden bg-island" style={{ width: w, borderRadius: card ? 26 : 22, boxShadow: '0 10px 28px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.05)' }}>{children}</div>
);
const text = (f: Frame, big = false) => f.words
  ? <p className={`m-0 font-display font-semibold leading-snug ${big ? 'text-[16px]' : 'text-[14px]'}`}>{f.words}</p>
  : <p className="m-0 text-[13px] text-ink-2">{f.status}</p>;

/** A: one line, face first, a small sign at the end. Grows only for long replies and questions. */
function Line({ f }: { f: Frame }) {
  return shell(f.ask ? 380 : 300, <div className="flex flex-col gap-2.5 px-3.5 py-2">
    <div className="flex min-h-7 items-center gap-3">
      <YobiFace look={f.look} size={26} level={0.6} />
      <div className="min-w-0 flex-1">{text(f)}</div>
      <Tail f={f} />
    </div>
    {f.ask && <Choices ask={f.ask} />}
  </div>);
}
/** B: a card with a bigger face, a small status title and the reply in large type. */
function Card({ f }: { f: Frame }) {
  return shell(380, <div className="flex items-start gap-3.5 px-5 py-4">
    <span className="grid size-11 shrink-0 place-items-center rounded-[14px] bg-fill-1"><YobiFace look={f.look} size={30} level={0.6} /></span>
    <div className="flex min-w-0 flex-1 flex-col gap-1.5">
      <span className="flex items-center gap-1.5 text-[11px] text-ink-3">
        {f.tail === 'mic' && <Mic className="size-3 text-accent" />}{f.words ? 'يوبي' : f.status}
      </span>
      {f.words ? text(f, true) : f.tail === 'mic' ? <Bars /> : <span className="h-1.5 w-full overflow-hidden rounded-pill bg-line"><span className="block h-full rounded-pill bg-accent" style={{ width: `${(f.progress ?? 0.3) * 100}%` }} /></span>}
      {f.ask && <div className="mt-1.5"><Choices ask={f.ask} /></div>}
    </div>
  </div>, true);
}
/** C: like A, plus Yobi's old line: a thin light at the bottom that listens, thinks and fills. */
function Glow({ f }: { f: Frame }) {
  const tone = f.tail === 'err' ? 'var(--color-alert)' : f.tail === 'ok' ? 'var(--color-gold)' : 'var(--color-accent)';
  const width = f.tail === 'ring' ? f.progress ?? 0 : f.tail === 'dots' ? 0.25 : f.tail === 'mic' ? 0.7 : 1;
  return shell(f.ask ? 380 : 300, <>
    <div className="flex flex-col gap-2.5 px-3.5 pt-2 pb-3">
      <div className="flex min-h-7 items-center gap-3">
        <YobiFace look={f.look} size={26} level={0.6} />
        <div className="min-w-0 flex-1">{text(f)}</div>
      </div>
      {f.ask && <Choices ask={f.ask} />}
    </div>
    <span className="absolute inset-x-6 bottom-[4px] h-[2px] rounded-pill bg-line/60">
      <span className="absolute inset-y-0 rounded-pill" style={{ insetInlineStart: f.tail === 'dots' ? '35%' : 0, width: `${width * 100}%`, background: tone, boxShadow: `0 0 8px ${tone}` }} />
    </span>
  </>);
}

const NAMES: Record<Variant, [string, string, (p: { f: Frame }) => ReactNode]> = {
  line: ['أ. السطر', 'الوش في الأول، الكلام في النص، وعلامة صغيرة في الآخر (مايك، تفكير، تقدّم، صح، غلط). الأخف والأقرب لـ Apple.', Line],
  card: ['ب. الكارت', 'كارت بوش أكبر، عنوان صغير بالحالة والرد بخط كبير. أوضح للقراية بس بياخد مساحة أكتر.', Card],
  glow: ['ج. السطر + الخط المضيء', 'زي "أ" بس من غير علامة في الآخر: خط يوبي المنوّر تحت هو اللي بيسمع ويفكر ويتملي.', Glow],
};

export function TurnOptions() {
  return (
    <div dir="rtl" className="h-full overflow-auto bg-[#1b1b1e] p-7 font-ui text-ink">
      {(['line', 'card', 'glow'] as Variant[]).map(v => {
        const [name, about, View] = NAMES[v];
        return (
          <section key={v} className="mb-8">
            <h2 className="font-display text-lg font-semibold">{name}</h2>
            <p className="mb-3 text-[13px] text-ink-2">{about}</p>
            <div className="flex flex-wrap items-start gap-x-5 gap-y-4">
              {FRAMES.map(f => (
                <figure key={f.label} className="m-0 flex flex-col items-center gap-1.5">
                  <View f={f} /><figcaption className="text-[11px] text-ink-3">{f.label}</figcaption>
                </figure>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
