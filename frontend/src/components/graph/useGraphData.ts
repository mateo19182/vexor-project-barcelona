import { useMemo } from "react";
import type { Node, Edge } from "@xyflow/react";
import type { EnrichmentResponse, ModuleInfo, AuditEvent } from "@/api/types";

interface ModuleNodeData {
  label: string;
  status: string;
  duration: number;
  signalCount: number;
  factCount: number;
  cached: boolean;
  wave: number | null;
  isNew: boolean;
  [key: string]: unknown;
}

const NODE_WIDTH = 200;
const NODE_HEIGHT = 60;

/**
 * Orbital layout — center node with concentric rings per wave.
 * Each ring's radius grows with the number of nodes in it so
 * cards never overlap.
 */
function orbitLayout(
  modules: { name: string; wave: number }[],
  centerX: number,
  centerY: number,
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();

  // Group by wave
  const waves = new Map<number, string[]>();
  for (const m of modules) {
    const group = waves.get(m.wave) || [];
    group.push(m.name);
    waves.set(m.wave, group);
  }

  const sortedWaves = [...waves.entries()].sort(([a], [b]) => a - b);

  // Each ring needs enough circumference to fit all its nodes without
  // overlapping. minArc = space each node occupies along the ring.
  const minArc = NODE_WIDTH + 40;
  const baseRadius = 280;
  const ringGap = 160;

  for (let wi = 0; wi < sortedWaves.length; wi++) {
    const [, mods] = sortedWaves[wi];
    // Radius is at least baseRadius + ring offset, but grows if there
    // are too many nodes to fit at that distance.
    const minRadius = (mods.length * minArc) / (2 * Math.PI);
    const radius = Math.max(baseRadius + wi * ringGap, minRadius);
    const angleStep = (2 * Math.PI) / Math.max(mods.length, 1);
    const angleOffset = wi * 0.4;

    for (let mi = 0; mi < mods.length; mi++) {
      const angle = angleOffset + mi * angleStep - Math.PI / 2;
      positions.set(mods[mi], {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      });
    }
  }

  return positions;
}

export function useGraphData(
  response: EnrichmentResponse | null,
  moduleInfos: ModuleInfo[],
  liveEvents?: AuditEvent[]
) {
  return useMemo(() => {
    const events = response?.audit_log || liveEvents || [];
    if (events.length === 0 && !response) {
      return { nodes: [], edges: [] };
    }

    const moduleMap = new Map(
      (response?.modules || []).map((m) => [m.name, m])
    );

    // Collect resolved modules (completed or cached) in order
    const resolved: { name: string; wave: number; status: string }[] = [];
    const resolvedSet = new Set<string>();

    for (const ev of events) {
      if (
        (ev.kind === "module_completed" || ev.kind === "module_cache_hit") &&
        ev.module &&
        !resolvedSet.has(ev.module)
      ) {
        resolvedSet.add(ev.module);
        const status = ev.kind === "module_cache_hit"
          ? "cached"
          : (ev.detail?.status as string) || "ok";
        resolved.push({ name: ev.module, wave: ev.wave ?? 1, status });
      }
    }

    // Detect currently running modules
    const runningModules = new Set<string>();
    if (liveEvents && !response) {
      const runningWave = liveEvents
        .filter((e) => e.kind === "wave_started")
        .map((e) => e.wave)
        .pop() ?? null;
      if (runningWave != null) {
        const waveModules = liveEvents
          .filter((e) => e.kind === "wave_started" && e.wave === runningWave)
          .flatMap((e) => (e.detail?.modules as string[]) || []);
        for (const name of waveModules) {
          if (!resolvedSet.has(name)) runningModules.add(name);
        }
      }
    }

    const maxWave = resolved.length > 0 ? Math.max(...resolved.map(r => r.wave)) : 0;

    // Compute orbital positions
    const centerX = 0;
    const centerY = 0;
    const allForLayout = [
      ...resolved,
      ...[...runningModules].map(name => ({ name, wave: maxWave + 1 })),
    ];
    const positions = orbitLayout(allForLayout, centerX, centerY);

    // Build nodes
    const nodes: Node<ModuleNodeData>[] = [];

    nodes.push({
      id: "__input__",
      type: "moduleNode",
      position: { x: centerX - NODE_WIDTH / 2, y: centerY - NODE_HEIGHT / 2 },
      data: {
        label: "Case Input",
        status: "ok",
        duration: 0,
        signalCount: 0,
        factCount: 0,
        cached: false,
        wave: 0,
        isNew: false,
      },
    });

    for (const r of resolved) {
      const pos = positions.get(r.name)!;
      const result = moduleMap.get(r.name);
      nodes.push({
        id: r.name,
        type: "moduleNode",
        position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
        data: {
          label: r.name,
          status: r.status,
          duration: result?.duration_s || 0,
          signalCount: result?.signals.length || 0,
          factCount: result?.facts.length || 0,
          cached: r.status === "cached",
          wave: r.wave,
          isNew: true,
        },
      });
    }

    for (const name of runningModules) {
      const pos = positions.get(name)!;
      nodes.push({
        id: name,
        type: "moduleNode",
        position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
        data: {
          label: name,
          status: "running",
          duration: 0,
          signalCount: 0,
          factCount: 0,
          cached: false,
          wave: maxWave + 1,
          isNew: true,
        },
      });
    }

    // Build edges — connect modules to their signal producers
    const edges: Edge[] = [];
    const edgeSet = new Set<string>();
    const infoMap = new Map(moduleInfos.map(m => [m.name, m]));

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

    const visibleNodes = new Set(nodes.map(n => n.id));

    for (const node of nodes) {
      if (node.id === "__input__") continue;
      const info = infoMap.get(node.id);
      if (!info) {
        const edgeId = `__input__->${node.id}`;
        if (!edgeSet.has(edgeId)) {
          edgeSet.add(edgeId);
          edges.push({
            id: edgeId,
            source: "__input__",
            target: node.id,
            style: { stroke: "#27272A", strokeWidth: 1 },
          });
        }
        continue;
      }

      let connected = false;
      for (const req of info.requires) {
        for (const [modName, signals] of producesSignal) {
          if (modName !== node.id && signals.has(req) && visibleNodes.has(modName)) {
            const edgeId = `${modName}->${node.id}`;
            if (!edgeSet.has(edgeId)) {
              edgeSet.add(edgeId);
              const data = node.data as ModuleNodeData;
              const isActive = data.status !== "skipped" && data.status !== "pending";
              edges.push({
                id: edgeId,
                source: modName,
                target: node.id,
                animated: isActive,
                style: isActive
                  ? { stroke: "#FAFAFA", strokeWidth: 1.5 }
                  : { stroke: "#3F3F46", strokeWidth: 1, strokeDasharray: "5 5" },
              });
              connected = true;
            }
          }
        }
      }

      if (!connected) {
        const edgeId = `__input__->${node.id}`;
        if (!edgeSet.has(edgeId)) {
          edgeSet.add(edgeId);
          edges.push({
            id: edgeId,
            source: "__input__",
            target: node.id,
            style: { stroke: "#27272A", strokeWidth: 1 },
          });
        }
      }
    }

    return { nodes, edges };
  }, [response, moduleInfos, liveEvents]);
}
