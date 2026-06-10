import { useApp } from "../state/store";
import { stopJudgeDemo } from "../lib/director";

export function LoadingScreen() {
  const stage = useApp((s) => s.loadingStage);
  const error = useApp((s) => s.bootError);
  return (
    <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-ops-900">
      <div className="relative mb-8 h-28 w-28">
        <div className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-ember-500 border-r-ember-400" style={{ animationDuration: "2.6s" }} />
        <div className="absolute inset-2 animate-spin rounded-full border-2 border-transparent border-t-routeblue" style={{ animationDuration: "1.8s", animationDirection: "reverse" }} />
        <div className="absolute inset-0 flex items-center justify-center">
          <svg viewBox="0 0 24 24" className="h-10 w-10 fill-ember-500 drop-shadow-[0_0_12px_rgba(255,90,31,0.8)]">
            <path d="M12 1.5c1.6 4.6-3.8 6-3 10.4.4 2.7 2 3.8 2 3.8s-4.2-.8-5-4.5c-2.2 2.2-3 5.2-1.5 8.2C6.3 23 9.8 23.3 12 23.3s6-0.8 7.5-4.5-0.8-6.7-2.2-9c-.8 2.2-2.3 3-2.3 3s1.5-5.2-3-11.3z" />
          </svg>
        </div>
      </div>
      <h1 className="font-display text-2xl font-bold tracking-[0.25em] text-white">
        PALISADES FIRE <span className="text-routeblue">3D ESCAPE TWIN</span>
      </h1>
      <p className="mt-1 text-xs tracking-widest text-slate-500">WILDFIRE EVACUATION DIGITAL TWIN · DEMO</p>
      {error ? (
        <div className="mt-6 max-w-md rounded-xl border border-ember-500/40 bg-ember-700/10 p-4 text-center text-xs leading-relaxed text-ember-200">
          {error}
        </div>
      ) : (
        <p className="mt-6 animate-pulseSoft font-mono text-xs text-slate-400">{stage}</p>
      )}
      <p className="absolute bottom-6 max-w-lg text-center text-[10px] leading-relaxed text-slate-600">
        Simulation only. Synthetic demo data approximating public reports of the January 7, 2025
        Palisades Fire. Always follow official evacuation orders and emergency personnel.
      </p>
    </div>
  );
}

export function JudgeOverlay() {
  const judge = useApp((s) => s.judge);
  const script = useApp((s) => s.datasets.judgeScript);
  if (!judge.running && !judge.summary) return null;

  return (
    <>
      {judge.running && (
        <div className="pointer-events-none absolute inset-x-0 top-3 z-30 flex justify-center">
          <div className="glass-strong pointer-events-auto flex items-center gap-3 rounded-full px-4 py-1.5">
            <span className="h-2 w-2 animate-pulseSoft rounded-full bg-ember-400" />
            <span className="font-display text-xs font-bold tracking-[0.2em] text-white">JUDGE DEMO</span>
            <div className="flex gap-1">
              {script?.steps.map((s, i) => (
                <span
                  key={s.id}
                  className={`h-1.5 w-3.5 rounded-full transition ${
                    i < judge.stepIndex ? "bg-ember-500" : i === judge.stepIndex ? "animate-pulseSoft bg-routeblue" : "bg-white/15"
                  }`}
                />
              ))}
            </div>
            <button className="text-[10px] text-slate-400 hover:text-white" onClick={stopJudgeDemo}>
              ✕ stop
            </button>
          </div>
        </div>
      )}

      {judge.running && judge.caption && (
        <div className="pointer-events-none absolute inset-x-0 bottom-6 z-30 flex justify-center px-8">
          <div className="animate-slideUp max-w-3xl rounded-xl border border-white/15 bg-black/70 px-6 py-3 text-center backdrop-blur-md">
            <p className="text-sm font-medium leading-relaxed text-slate-100">{judge.caption}</p>
          </div>
        </div>
      )}

      {judge.summary && (
        <div className="absolute inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="glass-strong animate-slideUp w-[560px] rounded-2xl p-6">
            <h2 className="font-display text-xl font-bold tracking-wider text-white">
              JUDGE DEMO COMPLETE
            </h2>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Everything below ran through the live simulation + routing APIs — no canned geometry.
            </p>
            <ul className="mt-4 space-y-2.5">
              {judge.summary.map((line, i) => (
                <li key={i} className="flex items-start gap-2.5 text-[13px] leading-snug text-slate-200">
                  <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-500/20 text-[10px] text-emerald-300">
                    ✓
                  </span>
                  {line}
                </li>
              ))}
            </ul>
            <div className="mt-5 rounded-lg border border-ember-500/30 bg-ember-700/10 px-3 py-2 text-[11px] leading-relaxed text-ember-200/90">
              Simulation-backed decision support, not a guarantee. In a real emergency: follow
              official evacuation orders, emergency personnel, and never enter closed roads.
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="btn-ghost"
                onClick={() => useApp.getState().setJudge({ summary: null, running: false, stepIndex: -1 })}
              >
                Close
              </button>
              <button className="btn-primary" onClick={() => useApp.getState().exportScenario()}>
                Export scenario JSON
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function Toast() {
  const toast = useApp((s) => s.toast);
  if (!toast) return null;
  return (
    <div className="pointer-events-none absolute left-1/2 top-16 z-30 -translate-x-1/2">
      <div className="animate-slideUp rounded-full border border-routeblue/40 bg-ops-800/90 px-4 py-1.5 text-xs font-medium text-sky-200 shadow-glow backdrop-blur">
        {toast}
      </div>
    </div>
  );
}
