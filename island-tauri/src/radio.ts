// The Qur'an radio (interface 7), played by the island itself: one <audio>, the station and volume
// remembered in the settings, a dropped stream reconnecting by itself, Windows' media keys, and the
// adhan pausing it. Python only lists the stations (from allowed hosts; the CSP allows only those).
import { bridge } from './bridge';
import { useIsland, type IslandStore } from './store';
import type { Station } from './types';
import { T, fmt } from './i18n';

const audio = new Audio();
audio.preload = 'none';
let tries = 0;
const get = () => useIsland.getState();
const set = (p: Partial<IslandStore['radio']>) => useIsland.setState(s => ({ radio: { ...s.radio, ...p } }));

export function radioPlay(st?: Station) {
  if (st) {
    set({ url: st.url, name: st.name });
    tries = 0;
    bridge.send({ t: 'settings_set', section: 'island', values: { radio_station: st.url } });
  }
  const url = get().radio.url;
  if (!url) return;
  audio.src = url;
  set({ msg: T('بيوصل…', 'Connecting…') });
  audio.play().then(() => {
    tries = 0;
    set({ playing: true, msg: '' });
    if ('mediaSession' in navigator) navigator.mediaSession.metadata = new MediaMetadata({ title: get().radio.name, artist: T('إذاعة القرآن الكريم', 'Quran Radio') });
  }).catch(() => set({ playing: false, msg: T('البث مش متاح دلوقتي', 'The stream isn’t available right now') }));
}

export function radioStop(msg = '') {
  audio.pause(); audio.removeAttribute('src'); audio.load();
  set({ playing: false, msg });
}

/** while dragging the slider: the sound follows at once; letting go saves it */
export function radioVolume(v: number, save: boolean) {
  audio.volume = Math.max(0, Math.min(1, v / 100));
  if (save) bridge.send({ t: 'settings_set', section: 'island', values: { radio_volume: Math.round(v) } });
}
export const radioVolumeNow = () => Math.round(audio.volume * 100);

// a dropped stream reconnects by itself: after 2, 5, then 15 seconds
audio.addEventListener('error', () => {
  if (!get().radio.playing) return;
  const wait = [2, 5, 15][Math.min(tries, 2)];
  tries++;
  set({ msg: T(`البث وقف، هرجّعه بعد ${fmt.num(wait)} ثواني`, `The stream dropped, retrying in ${wait} s`) });
  setTimeout(() => { if (get().radio.playing) radioPlay(); }, wait * 1000);
});

if ('mediaSession' in navigator) {
  navigator.mediaSession.setActionHandler('play', () => radioPlay());
  navigator.mediaSession.setActionHandler('pause', () => radioStop());
}

// the saved volume and the last station you chose
useIsland.subscribe((s, p) => {
  if (s.prefs === p.prefs) return;
  const v = s.prefs.radio_volume;
  if (typeof v === 'number' && v !== p.prefs.radio_volume) audio.volume = Math.max(0, Math.min(1, v / 100));
  const st = s.prefs.radio_station;
  if (typeof st === 'string' && st && !s.radio.playing && !s.radio.url) {
    set({ url: st, name: s.radio.stations.find(x => x.url === st)?.name || '' });
  }
});
