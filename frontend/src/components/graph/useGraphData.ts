import { useMemo } from "react";
import type { Node, Edge } from "@xyflow/react";
import type { EnrichmentResponse, ModuleInfo, AuditEvent } from "@/api/types";
import { layoutGraph } from "@/lib/dagLayout";

interface ModuleNodeData {
  label: string;
  status: string;
  duration: number;
  signalCount: number;
  factCount: number;
  cached: boolean;
  wave: number | null;
  [key: string]: unknown;
}

export function useGraphData(
  response: EnrichmentResponse | null,
  moduleInfos: ModuleInfo[],
  liveEvents?: AuditEvent[]
) {
  return useMemo(() => {
    if (!response && (!liveEvents || liveEvents.length === 0)) {
      return { nodes: [], edges: [] };
    }

    const moduleMap = new Map(
      (response?.modules || []).map((m) => [m.name, m])
    );

    const cachedSet = new Set(
      (response?.audit_log || liveEvents || [])
        .filter((e) => e.kind === "module_cache_hit")
        .map((e) => e.module)
    );

    const waveMap = new Map<string, number>();
    for (const ev of response?.audit_log || liveEvents || []) {
      if (
        (ev.kind === "module_completed" || ev.kind === "module_cache_hit") &&
        ev.module && ev.wave != null
      ) {
        waveMap.set(ev.module, ev.wave);
      }
    }

    const completedModules = new Set<string>();
    const runningModuleNames = new Set<string>();

    if (liveEvents && !response) {
      const runningWave = liveEvents
        .filter((e) => e.kind === "wave_started")
        .map((e) => e.wave)
        .pop() ?? null;

      for (const ev of liveEvents) {
        if ((ev.kind === "module_completed" || ev.kind === "module_cache_hit") && ev.module) {
          completedModules.add(ev.module);
        }
      }
      if (runningWave != null) {
        const waveModules = liveEvents
          .filter((e) => e.kind === "wave_started" && e.wave === runningWave)
          .flatMap((e) => (e.detail?.modules as string[]) || []);
        for (const name of waveModules) {
          if (!completedModules.has(name)) {
            runningModuleNames.add(name);
          }
        }
      }
    }

    const producesSignal = new Map<string, Set<string>>();
    for (const mod of response?.modules || []) {
      const keys = new Set<string>();
      for (const sig of mod.signals) {
        keys.add(sig.tag ? `${sig.kind}:${sig.tag}` : sig.kind);
      }
      for (const sl of mod.social_links) {
        const tag = sl.platform.toLowerCase();
        keys.add(`contact:${tag === "x" ? "twitter" : tag}`);
      }
      producesSignal.set(mod.name, keys);
    }

    const nodes: Node<ModuleNodeData>[] = [];

    nodes.push({
      id: "__input__",
      type: "moduleNode",
      position: { x: 0, y: 0 },
      data: {
        label: "Case Input",
        status: "ok",
        duration: 0,
        signalCount: 0,
        factCount: 0,
        cached: false,
        wave: 0,
      },
    });

    for (const info of moduleInfos) {
      const result = moduleMap.get(info.name);
      let status = result?.status || "pending";
      if (!response && runningModuleNames.has(info.name)) status = "running";
      if (cachedSet.has(info.name) && status === "ok") status = "cached";

      nodes.push({
        id: info.name,
        type: "moduleNode",
        position: { x: 0, y: 0 },
        data: {
          label: info.name,
          status,
          duration: result?.duration_s || 0,
          signalCount: result?.signals.length || 0,
          factCount: result?.facts.length || 0,
          cached: cachedSet.has(info.name),
          wave: waveMap.get(info.name) ?? null,
        },
      });
    }

    const edges: Edge[] = [];
    const edgeSet = new Set<string>();

    for (const info of moduleInfos) {
      for (const req of info.requires) {
        let foundProducer = false;
        for (const [modName, signals] of producesSignal) {
          if (modName !== info.name && signals.has(req)) {
            const edgeId = `${modName}->${info.name}`;
            if (!edgeSet.has(edgeId)) {
              edgeSet.add(edgeId);
              const targetResult = moduleMap.get(info.name);
              const isActive = targetResult && targetResult.status !== "skipped";
              edges.push({
                id: edgeId,
                source: modName,
                target: info.name,
                animated: !!isActive,
                style: isActive
                  ? { stroke: "#FAFAFA", strokeWidth: 1.5 }
                  : { stroke: "#3F3F46", strokeWidth: 1, strokeDasharray: "5 5" },
              });
              foundProducer = true;
            }
          }
        }
        if (!foundProducer) {
          const edgeId = `__input__->${info.name}`;
          if (!edgeSet.has(edgeId)) {
            edgeSet.add(edgeId);
            edges.push({
              id: edgeId,
              source: "__input__",
              target: info.name,
              style: { stroke: "#27272A", strokeWidth: 1 },
            });
          }
        }
      }

      if (info.requires.length === 0) {
        const edgeId = `__input__->${info.name}`;
        if (!edgeSet.has(edgeId)) {
          edgeSet.add(edgeId);
          edges.push({
            id: edgeId,
            source: "__input__",
            target: info.name,
            style: { stroke: "#27272A", strokeWidth: 1 },
          });
        }
      }
    }

    return layoutGraph(nodes, edges);
  }, [response, moduleInfos, liveEvents]);
}
