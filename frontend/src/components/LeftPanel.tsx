import { useApp } from "../state/store";
import { runJudgeDemo, stopJudgeDemo } from "../lib/director";

const CLOSURE_OPTIONS: Array<[string, string]> = [
  ["temescal", "Temescal Canyon Rd"],
  ["chautauqua", "Chautauqua Blvd"],
  ["pch_south", "PCH (southbound)"],
  ["sunset_east", "Sunset Blvd (east)"],
  ["inland", "San Vicente corridor"],
];

function Slider(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="stat-label">{props.label}</span>
        <span className="font-mono text-xs font-semibold text-routeblue">
          {props.value}
          {props.unit}
        </span>
      </div>
      <input
        type="range"
        min={props.min}
        max={props.max}
        step={props.step}
        value={props.value}
        onChange={(e) => props.onChange(Number(e.target.value))}
      />
    </label>
  );
}

export default function LeftPanel() {
  const simParams = useApp((s) => s.simParams);
  const setSimParam = useApp((s) => s.setSimParam);
  const layers = useApp((s) => s.layers);
  const toggleLayer = useApp((s) => s.toggleLayer);
  const closures = useApp((s) => s.closures);
  const toggleClosure = useApp((s) => s.toggleClosure);
  const profiles = useApp((s) => s.profiles);
  const profileId = useApp((s) => s.profileId);
  const setProfile = useApp((s) => s.setProfile);
  const judge = useApp((s) => s.judge);
  const visibilityLost = useApp((s) => s.visibilityLost);
  const exportScenario = useApp((s) => s.exportScenario);
  const resetScenario = useApp((s) => s.resetScenario);
  const loading = useApp((s) => s.loading);
  const applyLiveWind = useApp((s) => s.applyLiveWind);
  const startFromMyLocation = useApp((s) => s.startFromMyLocation);

  const windDirLabel = (d: number) => {
    const dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
    return dirs[Math.round(((d % 360) / 22.5)) % 16];
  };

  return (
    <aside className="glass z-20 flex w-72 shrink-0 flex-col gap-4 overflow-y-auto border-r border-white/10 p-4">
      <div>
        <button
          className={`w-full rounded-xl px-4 py-3 font-display text-base font-bold tracking-wider transition active:scale-[0.98] ${
            judge.running
              ? "border border-white/20 bg-white/10 text-white"
              : "bg-gradient-to-r from-ember-600 via-ember-500 to-amber-500 text-white shadow-fire hover:brightness-110"
          }`}
          disabled={loading}
          onClick={() => (judge.running ? stopJudgeDemo() : void runJudgeDemo())}
          data-testid="judge-demo-button"
        >
          {judge.running ? "■ STOP JUDGE DEMO" : "▶ RUN JUDGE DEMO"}
        </button>
        <p className="mt-1.5 text-center text-[10px] text-slate-500">
          Auto-replay: fire spread → guidance → live re-route → safe zone
        </p>
      </div>

      <section className="space-y-3">
        <h2 className="panel-title">Scenario conditions</h2>
        <Slider
          label="Wind speed"
          value={simParams.windSpeedMph}
          min={5}
          max={70}
          step={1}
          unit=" mph"
          onChange={(v) => void setSimParam("windSpeedMph", v)}
        />
        <Slider
          label={`Wind from (${windDirLabel(simParams.windFromDeg)})`}
          value={simParams.windFromDeg}
          min={0}
          max={359}
          step={1}
          unit="°"
          onChange={(v) => void setSimParam("windFromDeg", v)}
        />
        <Slider
          label="Fire intensity"
          value={simParams.fireIntensity}
          min={0.2}
          max={1}
          step={0.05}
          unit=""
          onChange={(v) => void setSimParam("fireIntensity", v)}
        />
        <button className="btn-ghost w-full" onClick={() => void applyLiveWind()}>
          🌬 Use live wind (Open-Meteo)
        </button>
        <div className="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2">
          <span className="stat-label">Visibility condition</span>
          <span
            className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold ${
              visibilityLost ? "bg-ember-600/30 text-ember-300" : "bg-emerald-500/15 text-emerald-300"
            }`}
          >
            {visibilityLost ? "LOST — re-weighted" : "NOMINAL"}
          </span>
        </div>
      </section>

      <section className="space-y-2">
        <h2 className="panel-title">Simulated resident</h2>
        <select
          className="w-full rounded-lg border border-white/10 bg-ops-700 px-3 py-2 text-sm text-slate-200 outline-none focus:border-routeblue/60"
          value={profileId}
          onChange={(e) => setProfile(e.target.value)}
        >
          {profiles.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <p className="text-[10px] leading-snug text-slate-500">
          {profiles.find((p) => p.id === profileId)?.description ?? ""}
        </p>
        <button className="btn-ghost w-full" onClick={() => startFromMyLocation()}>
          ⊕ Start from my location
        </button>
        <p className="text-center text-[9px] text-slate-600">
          Uses browser geolocation if you are inside the scenario area.
        </p>
      </section>

      <section className="space-y-1.5">
        <h2 className="panel-title">Road closures (official)</h2>
        {CLOSURE_OPTIONS.map(([group, label]) => (
          <label
            key={group}
            className="flex cursor-pointer items-center justify-between rounded-lg border border-white/5 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300 hover:bg-white/[0.06]"
          >
            <span>{label}</span>
            <input
              type="checkbox"
              className="h-3.5 w-3.5 accent-ember-500"
              checked={closures.includes(group)}
              onChange={() => void toggleClosure(group)}
            />
          </label>
        ))}
      </section>

      <section className="space-y-1.5">
        <h2 className="panel-title">Map layers</h2>
        <div className="grid grid-cols-2 gap-1.5">
          {(
            [
              ["buildings", "Buildings"],
              ["vegetation", "Fuel zones"],
              ["smoke", "Smoke"],
              ["risk", "Risk zones"],
              ["uncertainty", "Uncertainty"],
              ["predicted", "Predicted"],
              ["labels", "Labels"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              className={`rounded-md border px-2 py-1 text-[11px] font-medium transition ${
                layers[key]
                  ? "border-routeblue/50 bg-routeblue/15 text-sky-200"
                  : "border-white/10 bg-white/[0.03] text-slate-500"
              }`}
              onClick={() => toggleLayer(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      <section className="mt-auto space-y-2 border-t border-white/10 pt-3">
        <button className="btn-ghost w-full" onClick={() => exportScenario()}>
          ⤓ Export scenario JSON
        </button>
        <button className="btn-ghost w-full" onClick={() => void resetScenario()}>
          ↺ Reset scenario
        </button>
        <p className="text-center text-[9px] leading-snug text-slate-600">
          Synthetic demo data approximating public reports of the Jan 7, 2025 Palisades Fire.
          Not for real navigation.
        </p>
      </section>
    </aside>
  );
}
