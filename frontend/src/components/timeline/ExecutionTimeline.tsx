import type { EnrichmentResponse, AuditEvent } from "../../api/types";
import { statusDotColors } from "../../lib/colors";

interface TimelineProps {
  response: EnrichmentResponse | null;
  liveEvents?: AuditEvent[];
}

interface TimelineModule {
  name: string;
  status: string;
  duration: number;
  startTime: number;
  wave: number;
  cached: boolean;
}

export function ExecutionTimeline({ response, liveEvents }: TimelineProps) {
  const events = response?.audit_log || liveEvents || [];
  if (events.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-500 text-sm">
        No timeline data available.
      </div>
    );
  }

  // Extract module timings from audit events
  const modules: TimelineModule[] = [];
  const waveStarts = new Map<number, number>();

  for (const ev of events) {
    if (ev.kind === "wave_started" && ev.wave != null) {
      waveStarts.set(ev.wave, ev.elapsed_s);
    }
    if (
      (ev.kind === "module_completed" || ev.kind === "module_cache_hit") &&
      ev.module &&
      ev.wave != null
    ) {
      const duration =
        typeof ev.detail?.duration_s === "number"
          ? ev.detail.duration_s
          : typeof ev.detail?.cached_duration_s === "number"
            ? ev.detail.cached_duration_s
            : 0;
      const waveStart = waveStarts.get(ev.wave) ?? 0;
      modules.push({
        name: ev.module,
        status: (ev.detail?.status as string) || (ev.kind === "module_cache_hit" ? "cached" : "ok"),
        duration,
        startTime: waveStart,
        wave: ev.wave,
        cached: ev.kind === "module_cache_hit",
      });
    }
  }

  // Total pipeline time
  const totalTime = events.at(-1)?.elapsed_s || 1;
  const scale = (time: number) => (time / totalTime) * 100;

  // Group by wave
  const waves = new Map<number, TimelineModule[]>();
  for (const m of modules) {
    const group = waves.get(m.wave) || [];
    group.push(m);
    waves.set(m.wave, group);
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-sm font-semibold text-zinc-300">Execution Timeline</h2>
        <span className="text-xs text-zinc-500">{totalTime.toFixed(2)}s total</span>
      </div>

      <div className="space-y-6">
        {[...waves.entries()]
          .sort(([a], [b]) => a - b)
          .map(([wave, mods]) => (
            <div key={wave}>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider">
                  Wave {wave}
                </span>
                <div className="flex-1 h-px bg-zinc-800" />
              </div>
              <div className="space-y-1.5">
                {mods.map((m) => (
                  <div key={m.name} className="flex items-center gap-3">
                    <span className="text-xs text-zinc-400 w-32 truncate shrink-0">
                      {m.name}
                    </span>
                    <div className="flex-1 h-7 bg-zinc-800/50 rounded relative overflow-hidden">
                      <div
                        className={`absolute top-0 left-0 h-full rounded flex items-center px-2 transition-all duration-500 ${
                          m.status === "ok" || m.status === "cached"
                            ? "bg-emerald-500/30"
                            : m.status === "error"
                              ? "bg-red-500/30"
                              : m.status === "skipped"
                                ? "bg-zinc-600/30"
                                : "bg-purple-500/30"
                        }`}
                        style={{
                          left: `${scale(m.startTime)}%`,
                          width: `${Math.max(scale(m.duration), 2)}%`,
                        }}
                      >
                        <span className="text-[10px] text-zinc-300 whitespace-nowrap">
                          {m.duration.toFixed(2)}s
                        </span>
                      </div>
                    </div>
                    <span
                      className={`w-2 h-2 rounded-full shrink-0 ${
                        statusDotColors[m.cached ? "cached" : m.status] || "bg-zinc-600"
                      }`}
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}
      </div>

      {/* Time axis */}
      <div className="mt-6 pt-3 border-t border-zinc-800">
        <div className="flex justify-between text-[10px] text-zinc-600">
          <span>0s</span>
          <span>{(totalTime * 0.25).toFixed(1)}s</span>
          <span>{(totalTime * 0.5).toFixed(1)}s</span>
          <span>{(totalTime * 0.75).toFixed(1)}s</span>
          <span>{totalTime.toFixed(1)}s</span>
        </div>
      </div>
    </div>
  );
}
