// Yobi's turn, outside React: how long it stays on screen, the chime, and what Python is told
// (`view`, so agent.py's is_free() knows when Yobi is done, and `answer` for a question).
import { bridge } from './bridge';
import { isActive, isReply, replyVisible, useIsland, type IslandStore } from './store';
import type { YobiState } from './types';

let timer: ReturnType<typeof setTimeout> | undefined;
let hovering = false;

/** the pointer is on the island: a reply waits until it leaves */
export const setHovering = (on: boolean) => { hovering = on; };
export const isHovering = () => hovering;

/** how long a reply stays, by its length (the same numbers Python uses for reply_visible) */
export function readingTime(text: string, st: YobiState) {
  const n = text.length;
  if (st === 'success') return 3800 + Math.min(4000, n * 25);
  if (st === 'error') return 4500 + Math.min(4000, n * 25);
  return Math.min(10000, Math.max(4000, n * 45));
}

function schedule(ms: number) {
  clearTimeout(timer);
  timer = setTimeout(() => {
    timer = undefined;
    if (hovering) { schedule(1500); return; }
    useIsland.getState().hide();
  }, ms);
  if (!useIsland.getState().replyHeld) useIsland.setState({ replyHeld: true });
}
function clear() {
  clearTimeout(timer); timer = undefined;
  if (useIsland.getState().replyHeld) useIsland.setState({ replyHeld: false });
}

/** a button under Yobi's question was chosen */
export function answer(id: string, value: string) {
  const s = useIsland.getState();
  if (s.question?.id !== id) return;              // only the latest question is live
  bridge.send({ t: 'answer', id, value });
  useIsland.setState({ question: null });
  schedule(1800);
}

let ctx: AudioContext | null = null;
export function tone(f1: number, f2?: number) {
  try {
    ctx ??= new AudioContext();
    const o = ctx.createOscillator(), g = ctx.createGain(), n = ctx.currentTime;
    o.type = 'sine'; o.frequency.setValueAtTime(f1, n);
    if (f2) o.frequency.exponentialRampToValueAtTime(f2, n + 0.12);
    g.gain.setValueAtTime(0, n); g.gain.linearRampToValueAtTime(0.045, n + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, n + 0.26);
    o.connect(g).connect(ctx.destination); o.start(n); o.stop(n + 0.3);
  } catch { /* no audio device */ }
}

let told = '';
function report(s: IslandStore) {
  const v = { t: 'view' as const, state: s.state, reply: replyVisible(s) };
  const key = `${v.state}:${v.reply}`;
  if (key !== told) { told = key; bridge.send(v); }
}

useIsland.subscribe((s, p) => {
  if (s.chime && s.chime !== p.chime) tone(s.chime.f1, s.chime.f2);
  if (s.state === 'idle') { if (timer) clear(); }
  else if (s.seq !== p.seq || s.typing !== p.typing || s.words !== p.words || s.status !== p.status) {
    if (isActive(s.state)) schedule(60_000);                        // a safety net if a turn never ends
    else if (s.question && s.question !== p.question) schedule(s.question.timeout || 30_000);
    else if (s.typing) { clearTimeout(timer); timer = undefined; }   // still typing: the clock starts after
    else if (isReply(s.state) && !s.question) schedule(readingTime(s.words, s.state));
  }
  report(useIsland.getState());
});
