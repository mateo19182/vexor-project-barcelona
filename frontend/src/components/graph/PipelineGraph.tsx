import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { EnrichmentResponse, ModuleInfo, AuditEvent } from "../../api/types";
import { useGraphData } from "./useGraphData";
import { ModuleNode } from "./ModuleNode";

const nodeTypes: NodeTypes = {
  moduleNode: ModuleNode as unknown as NodeTypes["moduleNode"],
};

interface PipelineGraphProps {
  response: EnrichmentResponse | null;
  moduleInfos: ModuleInfo[];
  liveEvents?: AuditEvent[];
  onNodeClick?: (moduleName: string) => void;
}

export function PipelineGraph({
  response,
  moduleInfos,
  liveEvents,
  onNodeClick,
}: PipelineGraphProps) {
  const { nodes, edges } = useGraphData(response, moduleInfos, liveEvents);

  if (nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-500">
        Select a case run or submit a new case to see the pipeline graph.
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodeClick={(_event, node) => {
        if (node.id !== "__input__" && onNodeClick) {
          onNodeClick(node.id);
        }
      }}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      minZoom={0.3}
      maxZoom={2}
      proOptions={{ hideAttribution: true }}
    >
      <Background gap={20} size={1} color="#27272a" />
      <Controls showInteractive={false} />
      <MiniMap
        nodeColor={(node) => {
          const status = (node.data as { status?: string })?.status;
          if (status === "ok") return "#22c55e";
          if (status === "cached") return "#3b82f6";
          if (status === "error") return "#ef4444";
          if (status === "running") return "#f59e0b";
          return "#52525b";
        }}
        maskColor="rgba(0,0,0,0.7)"
      />
    </ReactFlow>
  );
}
