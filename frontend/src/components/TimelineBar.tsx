import { useApp } from "../state/store";

const TICKS = [0, 5, 10, 15, 20, 30, 45, 60, 75, 90];

function simClock(minute: number): string {
  const total = 10 * 60 + 30 + minute; // 10:30 AM PST + sim minutes
  const h = Math.floor(total / 60);
  const m = Math.floor(total % 60);
  const ampm = h >= 12 ? "PM" : "AM";
  const hh = ((h + 11) % 12) + 1;
  return `${hh}:${String(m).padStart(2, "0")} ${ampm}`;
}

export default function TimelineBar() {
  const simMinute = useApp((s) => s.simMinute);
  const setMinute = useApp((s) => s.setMinute);
  const playing = useApp((s) => s.playing);
  const setPlaying = useApp((s) => s.setPlaying);
  const playbackSpeed = useApp((s) => s.playbackSpeed);
  const setPlaybackSpeed = useApp((s) => s.setPlaybackSpeed);
  const advanceUser = useApp((s) => s.advanceUser);
  const simulateMissedTurn = useApp((s) => s.simulateMissedTurn);
  const simulateVisibilityLost = useApp((s) => s.simulateVisibilityLost);
  const simulateBlockedRoad = useApp((s) => s.simulateBlockedRoad);
  const user = useApp((s) => s.user);
  const placeUser = useApp((s) => s.placeUser);
  const askGuidance = useApp((s) => s.askGuidance);
  const judgeRunning = useApp((s) => s.judge.running);
  const followCam = useApp((s) => s.followCam);
  const setFollowCam = useApp((s) => s.setFollowCam);

  return (
    <footer className="glass-strong z-30 flex h-[88px] shrink-0 items-center gap-4 border-t border-white/10 px-4">
      <div className="flex items-center gap-2">
        <button
          className="flex h-10 w-10 items-center justify-center rounded-full bg-routeblue/15 text-lg text-sky-300 transition hover:bg-routeblue/30"
          onClick={() => setPlaying(!playing)}
          title={playing ? "Pause replay" : "Play replay"}
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <div className="flex flex-col gap-0.5">
          {[1, 2, 4].map((s) => (
            <button
              key={s}
              className={`rounded px-1.5 text-[9px] font-bold ${
                playbackSpeed === s ? "bg-routeblue/30 text-sky-200" : "text-slate-500 hover:text-slate-300"
              }`}
              onClick={() => setPlaybackSpeed(s)}
            >
              {s}×
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1">
        <div className="mb-1 flex items-baseline justify-between">
          <span className="font-display text-xs font-semibold tracking-widest text-slate-400">
            HISTORICAL REPLAY · JAN 7, 2025 (modeled)
          </span>
          <span className="font-mono text-sm font-bold text-white">
            {simClock(simMinute)}
            <span className="ml-2 text-[10px] font-medium text-slate-500">
              T+{Math.floor(simMinute)}:{String(Math.floor((simMinute % 1) * 60)).padStart(2, "0")} min
            </span>
          </span>
        </div>
        <div className="relative">
          <input
            type="range"
            min={0}
            max={90}
            step={0.25}
            value={simMinute}
            onChange={(e) => setMinute(Number(e.target.value))}
          />
          <div className="pointer-events-none relative mt-1 h-4">
            {TICKS.map((t) => (
              <span
                key={t}
                className={`absolute -translate-x-1/2 font-mono text-[9px] ${
                  simMinute >= t ? "text-ember-400" : "text-slate-600"
                }`}
                style={{ left: `${(t / 90) * 100}%` }}
              >
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1.5">
        {!user ? (
          <button
            className="btn-primary"
            disabled={judgeRunning}
            onClick={() => {
              placeUser();
              void askGuidance("Where do I go?");
            }}
          >
            ⬤ Place resident & ask
          </button>
        ) : (
          <>
            <button className="btn-ghost" disabled={judgeRunning} onClick={() => void advanceUser(91.44)}>
              Advance 300 ft
            </button>
            <button className="btn-ghost" disabled={judgeRunning} onClick={() => void simulateMissedTurn()}>
              Missed turn
            </button>
            <button className="btn-ghost" disabled={judgeRunning} onClick={() => void simulateVisibilityLost()}>
              Visibility lost
            </button>
            <button className="btn-ghost" disabled={judgeRunning} onClick={() => void simulateBlockedRoad()}>
              Road blocked
            </button>
            <button
              className={`btn-ghost ${followCam ? "!border-routeblue/60 !bg-routeblue/15 !text-sky-200" : ""}`}
              onClick={() => setFollowCam(!followCam)}
            >
              ⌖ Follow
            </button>
          </>
        )}
      </div>
    </footer>
  );
}
