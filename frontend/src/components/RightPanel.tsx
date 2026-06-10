import { useEffect, useRef, useState } from "react";
import { useApp } from "../state/store";
import { listenOnce, recognitionAvailable } from "../lib/speech";
import { fmtMiles, metersToFeetLabel } from "../lib/geo";
import type { CandidateRoute } from "../types";

const QUICK_ACTIONS = [
  "Where do I go?",
  "I can't see ahead",
  "I missed the turn",
  "Road is blocked",
  "Repeat instruction",
  "Am I safe yet?",
];

function ConfidenceMeter({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const hue = value > 0.7 ? "bg-emerald-400" : value > 0.5 ? "bg-amber-400" : "bg-ember-500";
  return (
    <div>
      <div className="mb-1 flex justify-between">
        <span className="stat-label">Route confidence</span>
        <span className="font-mono text-xs font-bold text-slate-200">{pct}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full ${hue} transition-all duration-700`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function RouteCard({ route, active, recommended, onSelect }: {
  route: CandidateRoute;
  active: boolean;
  recommended: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      onClick={onSelect}
      className={`w-full rounded-xl border p-3 text-left transition ${
        active
          ? "border-routeblue/70 bg-routeblue/10 shadow-glow"
          : "border-white/10 bg-white/[0.03] hover:border-white/25"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold text-slate-100">{route.name}</span>
        <span className="flex gap-1">
          {recommended && (
            <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[9px] font-bold tracking-wide text-emerald-300">
              RECOMMENDED
            </span>
          )}
          {active && (
            <span className="rounded bg-routeblue/25 px-1.5 py-0.5 text-[9px] font-bold tracking-wide text-sky-200">
              ACTIVE
            </span>
          )}
        </span>
      </div>
      <div className="mt-2 grid grid-cols-4 gap-1 text-center">
        <div>
          <div className="stat-label">Time</div>
          <div className="font-mono text-[11px] font-semibold text-slate-200">
            {route.estimatedTravelTimeMinutes.toFixed(0)}m
          </div>
        </div>
        <div>
          <div className="stat-label">Buffer</div>
          <div
            className={`font-mono text-[11px] font-semibold ${
              route.fireArrivalBufferMinutes < 8 ? "text-ember-400" : "text-emerald-300"
            }`}
          >
            {route.fireArrivalBufferMinutes.toFixed(0)}m
          </div>
        </div>
        <div>
          <div className="stat-label">Smoke</div>
          <div
            className={`font-mono text-[11px] font-semibold ${
              route.smokeExposureScore > 50 ? "text-ember-400" : route.smokeExposureScore > 25 ? "text-amber-300" : "text-emerald-300"
            }`}
          >
            {route.smokeExposureScore.toFixed(0)}
          </div>
        </div>
        <div>
          <div className="stat-label">Score</div>
          <div className="font-mono text-[11px] font-semibold text-routeblue">
            {route.score ? route.score.final.toFixed(2) : "—"}
          </div>
        </div>
      </div>
      <div className="mt-1.5 text-[10px] text-slate-500">
        {fmtMiles(route.totalDistanceMeters)} · {route.maneuvers.length} maneuvers
        {route.warnings.length > 0 && (
          <span className="ml-1 text-amber-400/90"> · ⚠ {route.warnings[0]}</span>
        )}
      </div>
    </button>
  );
}

export default function RightPanel() {
  const transcript = useApp((s) => s.transcript);
  const askGuidance = useApp((s) => s.askGuidance);
  const assistantBusy = useApp((s) => s.assistantBusy);
  const status = useApp((s) => s.status);
  const recommendation = useApp((s) => s.recommendation);
  const activeRouteId = useApp((s) => s.activeRouteId);
  const setActiveRoute = useApp((s) => s.setActiveRoute);
  const user = useApp((s) => s.user);
  const [input, setInput] = useState("");
  const [listening, setListening] = useState(false);
  const [showWhy, setShowWhy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    if (typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    } else {
      el.scrollTop = el.scrollHeight;
    }
  }, [transcript.length]);

  const send = (text: string) => {
    const t = text.trim();
    if (!t || assistantBusy) return;
    setInput("");
    void askGuidance(t);
  };

  const pushToTalk = async () => {
    if (!recognitionAvailable() || listening) return;
    setListening(true);
    const heard = await listenOnce();
    setListening(false);
    if (heard) send(heard);
  };

  const best = recommendation?.candidates.find((c) => c.routeId === recommendation.recommendedRouteId);
  const backup = recommendation?.candidates
    .filter((c) => c.routeId !== activeRouteId)
    .sort((a, b) => (b.score?.final ?? 0) - (a.score?.final ?? 0))[0];

  return (
    <aside className="glass z-20 flex w-[370px] shrink-0 flex-col overflow-hidden border-l border-white/10">
      {/* Voice assistant */}
      <div className="flex min-h-0 flex-1 flex-col p-3">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="panel-title">Voice assistant</h2>
          <span className="text-[9px] text-slate-500">simulation-backed · rule engine v1</span>
        </div>
        <div ref={scroller} className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {transcript.length === 0 && (
            <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3 text-[11px] leading-relaxed text-slate-400">
              Ask <span className="text-sky-300">“Where do I go?”</span> or run the Judge Demo.
              Every answer explains the modeled route and always defers to official evacuation
              orders.
            </div>
          )}
          {transcript.map((m) => (
            <div
              key={m.id}
              className={`animate-slideUp rounded-xl px-3 py-2 text-[12px] leading-relaxed ${
                m.who === "user"
                  ? "ml-6 border border-routeblue/30 bg-routeblue/10 text-sky-100"
                  : m.who === "assistant"
                    ? "mr-6 border border-white/10 bg-white/[0.05] text-slate-200"
                    : "border border-amber-400/20 bg-amber-400/5 text-[10px] text-amber-200/80"
              }`}
            >
              <span className="mb-0.5 block text-[9px] font-bold uppercase tracking-wider opacity-50">
                {m.who} · {m.at}
              </span>
              {m.text}
            </div>
          ))}
          {assistantBusy && (
            <div className="mr-6 animate-pulseSoft rounded-xl border border-white/10 bg-white/[0.05] px-3 py-2 text-[12px] text-slate-400">
              analyzing modeled hazards…
            </div>
          )}
        </div>

        <div className="mt-2 flex flex-wrap gap-1">
          {QUICK_ACTIONS.map((q) => (
            <button key={q} className="chip" disabled={assistantBusy} onClick={() => send(q)}>
              {q}
            </button>
          ))}
        </div>
        <div className="mt-2 flex gap-1.5">
          <input
            className="min-w-0 flex-1 rounded-lg border border-white/15 bg-ops-700 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-routeblue/60"
            placeholder="Type to the assistant…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send(input)}
          />
          <button
            className={`rounded-lg border px-3 text-sm transition ${
              listening
                ? "animate-pulseSoft border-ember-500 bg-ember-600/30 text-ember-200"
                : "border-white/15 bg-white/5 text-slate-300 hover:bg-white/10"
            } ${!recognitionAvailable() ? "cursor-not-allowed opacity-35" : ""}`}
            title={recognitionAvailable() ? "Push to talk" : "Speech recognition unavailable — type instead"}
            onClick={() => void pushToTalk()}
          >
            🎙
          </button>
          <button className="btn-primary" disabled={assistantBusy} onClick={() => send(input)}>
            Send
          </button>
        </div>
      </div>

      {/* Status + routes */}
      <div className="max-h-[46%] space-y-3 overflow-y-auto border-t border-white/10 bg-ops-850/60 p-3">
        <div className="rounded-xl border border-routeblue/25 bg-routeblue/5 p-3">
          <div className="stat-label mb-1">
            Current instruction {user?.status === "off_route" && <span className="text-ember-400">· OFF ROUTE</span>}
          </div>
          <div className={`text-sm font-semibold leading-snug ${status.arrived ? "text-emerald-300" : "text-sky-100"}`}>
            {status.instruction}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
            <div>
              <div className="stat-label">Next maneuver</div>
              <div className="stat-value text-[11px]">{metersToFeetLabel(status.distanceToManeuverM)}</div>
            </div>
            <div>
              <div className="stat-label">Remaining</div>
              <div className="stat-value text-[11px]">{fmtMiles(status.remainingM)}</div>
            </div>
            <div>
              <div className="stat-label">Fire buffer</div>
              <div className={`stat-value text-[11px] ${status.bufferMin < 8 ? "text-ember-400" : "text-emerald-300"}`}>
                ~{status.bufferMin.toFixed(0)} min modeled
              </div>
            </div>
            <div>
              <div className="stat-label">Smoke at position</div>
              <div className="stat-value text-[11px]">
                {status.smokeHere > 0.6 ? "HEAVY" : status.smokeHere > 0.3 ? "MODERATE" : status.smokeHere > 0.05 ? "LIGHT" : "CLEAR"}
              </div>
            </div>
          </div>
          {best && <div className="mt-2.5"><ConfidenceMeter value={best.confidence} /></div>}
          {backup && (
            <div className="mt-2 flex items-center justify-between text-[10px] text-slate-400">
              <span>
                Backup: <span className="text-slate-300">{backup.name}</span> (
                {backup.estimatedTravelTimeMinutes.toFixed(0)} min)
              </span>
              <button className="chip !py-0.5" onClick={() => setActiveRoute(backup.routeId)}>
                switch
              </button>
            </div>
          )}
        </div>

        {recommendation && (
          <>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h3 className="panel-title">Candidate routes</h3>
                <span className="text-[9px] text-slate-500">min {recommendation.generatedAtMinute.toFixed(0)}</span>
              </div>
              {recommendation.candidates.map((c) => (
                <RouteCard
                  key={c.routeId}
                  route={c}
                  active={c.routeId === activeRouteId}
                  recommended={c.routeId === recommendation.recommendedRouteId}
                  onSelect={() => setActiveRoute(c.routeId)}
                />
              ))}
            </div>

            <div className="rounded-xl border border-white/10 bg-white/[0.03]">
              <button
                className="flex w-full items-center justify-between px-3 py-2 text-left"
                onClick={() => setShowWhy((v) => !v)}
              >
                <span className="panel-title !text-slate-300">Why this route?</span>
                <span className="text-slate-500">{showWhy ? "▾" : "▸"}</span>
              </button>
              {showWhy && (
                <div className="space-y-2 px-3 pb-3 text-[11px] leading-relaxed text-slate-400">
                  <p>{recommendation.explanation}</p>
                  <p className="border-l-2 border-amber-400/40 pl-2 text-amber-200/80">
                    <span className="font-semibold">Why not the fastest? </span>
                    {recommendation.whyNotFastest}
                  </p>
                  <p className="text-[10px] text-slate-500">{recommendation.safetyReminder}</p>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
