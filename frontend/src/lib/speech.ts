/**
 * Voice I/O on browser-native APIs only (no keys, no cloud).
 * - Synthesis: queued, interruptible, calm pacing.
 * - Recognition: push-to-talk via webkitSpeechRecognition when the browser
 *   has it (Chrome/Edge); the UI falls back to typed commands otherwise.
 */

type SpeakOptions = { interrupt?: boolean };

const hasSynth = typeof window !== "undefined" && "speechSynthesis" in window;

let voice: SpeechSynthesisVoice | null = null;
let muted = false;

function pickVoice(): SpeechSynthesisVoice | null {
  if (!hasSynth) return null;
  const voices = window.speechSynthesis.getVoices();
  const prefer = ["Samantha", "Google US English", "Microsoft Aria", "Karen", "Daniel"];
  for (const name of prefer) {
    const v = voices.find((v) => v.name.includes(name));
    if (v) return v;
  }
  return voices.find((v) => v.lang.startsWith("en")) ?? voices[0] ?? null;
}

if (hasSynth) {
  window.speechSynthesis.onvoiceschanged = () => {
    voice = pickVoice();
  };
  voice = pickVoice();
}

export function setMuted(m: boolean): void {
  muted = m;
  if (m && hasSynth) window.speechSynthesis.cancel();
}

export function isMuted(): boolean {
  return muted;
}

export function speak(text: string, opts: SpeakOptions = {}): Promise<void> {
  if (!hasSynth || muted || !text) return Promise.resolve();
  return new Promise((resolve) => {
    if (opts.interrupt) window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    if (!voice) voice = pickVoice();
    if (voice) u.voice = voice;
    u.rate = 1.04;
    u.pitch = 1.0;
    u.volume = 1.0;
    let done = false;
    const finish = () => {
      if (!done) {
        done = true;
        window.clearTimeout(watchdog);
        resolve();
      }
    };
    // Some engines never fire onend (headless, broken voices): never stall
    // the demo — resolve after a duration estimate.
    const watchdog = window.setTimeout(finish, Math.max(3000, text.length * 95));
    u.onend = finish;
    u.onerror = finish;
    window.speechSynthesis.speak(u);
  });
}

export function stopSpeaking(): void {
  if (hasSynth) window.speechSynthesis.cancel();
}

// ---- recognition -----------------------------------------------------------

interface RecognitionLike {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((ev: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
}

function recognitionCtor(): (new () => RecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as
    | (new () => RecognitionLike)
    | null;
}

export function recognitionAvailable(): boolean {
  return recognitionCtor() !== null;
}

/** One-shot push-to-talk capture. Resolves with the transcript or null. */
export function listenOnce(): Promise<string | null> {
  const Ctor = recognitionCtor();
  if (!Ctor) return Promise.resolve(null);
  return new Promise((resolve) => {
    const rec = new Ctor();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    let done = false;
    rec.onresult = (ev) => {
      done = true;
      resolve(ev.results[0]?.[0]?.transcript ?? null);
    };
    rec.onerror = () => {
      if (!done) resolve(null);
      done = true;
    };
    rec.onend = () => {
      if (!done) resolve(null);
      done = true;
    };
    try {
      rec.start();
    } catch {
      resolve(null);
    }
  });
}
