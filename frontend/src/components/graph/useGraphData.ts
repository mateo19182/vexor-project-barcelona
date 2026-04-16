import { useMemo } from "react";
import type { Node, Edge } from "@xyflow/react";
import type { EnrichmentResponse, ModuleInfo, AuditEvent } from "../../api/types";
import { layoutGraph } from "../../lib/dagLayout";

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

    // Build a map of module results
    const moduleMap = new Map(
      (response?.modules || []).map((m) => [m.name, m])
    );

    // Build cached set from audit log
    const cachedSet = new Set(
      (response?.audit_log || liveEvents || [])
        .filter((e) => e.kind === "module_cache_hit")
        .map((e) => e.module)
    );

    // Build wave assignments from audit log
    const waveMap = new Map<string, number>();
    for (const ev of response?.audit_log || liveEvents || []) {
      if (
        (ev.kind === "module_completed" || ev.kind === "module_cache_hit") &&
        ev.module &&
        ev.wave != null
      ) {
        waveMap.set(ev.module, ev.wave);
      }
    }

    // Determine running modules from live events
    const completedModules = new Set<string>();
    const runningWave =
      liveEvents
        ?.filter((e) => e.kind === "wave_started")
        .map((e) => e.wave)
        .pop() ?? null;
    const runningModuleNames = new Set<string>();

    if (liveEvents && !response) {
      for (const ev of liveEvents) {
        if (
          (ev.kind === "module_completed" || ev.kind === "module_cache_hit") &&
          ev.module
        ) {
          completedModules.add(ev.module);
        }
      }
      // If we have a wave_started event, modules in that wave that aren't completed are running
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

    // Build signal production map: which modules produce which signal kinds
    const producesSignal = new Map<string, Set<string>>(); // module -> set of "kind:tag" or "kind"
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

    // Create nodes
    const nodes: Node<ModuleNodeData>[] = [];

    // Case input root node
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

    // Create edges
    const edges: Edge[] = [];
    const edgeSet = new Set<string>();

    for (const info of moduleInfos) {
      for (const req of info.requires) {
        let foundProducer = false;
        // Check if any module produces this signal
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
                animated: isActive ? true : false,
                style: isActive
                  ? { stroke: "#22c55e", strokeWidth: 2 }
                  : { stroke: "#52525b", strokeWidth: 1, strokeDasharray: "5 5" },
              });
              foundProducer = true;
            }
          }
        }
        // If no specific producer found and it's a base requirement (name, address, etc.),
        // connect to input node
        if (!foundProducer) {
          const edgeId = `__input__->${info.name}`;
          if (!edgeSet.has(edgeId)) {
            edgeSet.add(edgeId);
            edges.push({
              id: edgeId,
              source: "__input__",
              target: info.name,
              style: { stroke: "#3f3f46", strokeWidth: 1 },
            });
          }
        }
      }

      // Modules with no requires also connect to input
      if (info.requires.length === 0) {
        const edgeId = `__input__->${info.name}`;
        if (!edgeSet.has(edgeId)) {
          edgeSet.add(edgeId);
          edges.push({
            id: edgeId,
            source: "__input__",
            target: info.name,
            style: { stroke: "#3f3f46", strokeWidth: 1 },
          });
        }
      }
    }

    return layoutGraph(nodes, edges);
  }, [response, moduleInfos, liveEvents]);
}
