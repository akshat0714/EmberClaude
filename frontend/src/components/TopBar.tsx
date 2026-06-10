import { useApp } from "../state/store";
import { setMuted } from "../lib/speech";

export default function TopBar() {
  const scenario = useApp((s) => s.scenario);
  const muted = useApp((s) => s.muted);
  const setMutedState = useApp((s) => s.setMutedState);
  const sim = useApp((s) => s.sim);

  return (
    <header className="glass-strong z-30 flex h-14 shrink-0 items-center gap-4 border-b border-white/10 px-4">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-ember-500 to-ember-700 shadow-fire">
          <svg viewBox="0 0 24 24" className="h-5 w-5 fill-white">
            <path d="M12 1.5c1.6 4.6-3.8 6-3 10.4.4 2.7 2 3.8 2 3.8s-4.2-.8-5-4.5c-2.2 2.2-3 5.2-1.5 8.2C6.3 23 9.8 23.3 12 23.3s6-0.8 7.5-4.5-0.8-6.7-2.2-9c-.8 2.2-2.3 3-2.3 3s1.5-5.2-3-11.3z" />
          </svg>
        </div>
        <div>
          <h1 className="font-display text-lg font-bold leading-tight tracking-wide text-white">
            PALISADES FIRE <span className="text-routeblue">3D ESCAPE TWIN</span>
          </h1>
          <p className="text-[11px] leading-tight text-slate-400">
            {scenario?.label ?? "Historical Palisades Fire Replay + Simulated Evacuation"}
          </p>
        </div>
      </div>

      <div className="mx-auto flex items-center gap-2 rounded-full border border-ember-500/40 bg-ember-700/15 px-4 py-1.5">
        <span className="h-2 w-2 animate-pulseSoft rounded-full bg-ember-400" />
        <span className="text-xs font-semibold tracking-wide text-ember-300">
          SIMULATION ONLY — follow official evacuation orders and emergency personnel
        </span>
      </div>

      <div className="flex items-center gap-2">
        <span
          className={`rounded-md px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-wider ${
            sim ? "bg-emerald-500/15 text-emerald-300" : "bg-amber-500/15 text-amber-300"
          }`}
        >
          {sim ? "MODEL LIVE" : "MODEL …"}
        </span>
        <button
          className="btn-ghost"
          onClick={() => {
            setMuted(!muted);
            setMutedState(!muted);
          }}
          title={muted ? "Unmute voice" : "Mute voice"}
        >
          {muted ? "🔇 Voice off" : "🔊 Voice on"}
        </button>
      </div>
    </header>
  );
}
