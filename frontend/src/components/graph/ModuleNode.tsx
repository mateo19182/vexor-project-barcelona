import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import { getStatusColor, statusDotColors } from "@/lib/colors";

interface ModuleNodeData {
  label: string;
  status: string;
  duration: number;
  signalCount: number;
  factCount: number;
  cached: boolean;
  wave: number | null;
}

function ModuleNodeComponent({ data }: { data: ModuleNodeData }) {
  const colors = getStatusColor(data.status);
  const isInput = data.label === "Case Input";

  return (
    <div
      className={`
        rounded-lg border px-4 py-3 min-w-[200px]
        ${colors.border} ${colors.bg}
        bg-bg-surface/80 backdrop-blur-sm
        transition-all duration-200
        hover:scale-[1.02] hover:shadow-lg hover:shadow-black/20
      `}
    >
      <Handle type="target" position={Position.Left} className="!bg-zinc-600 !w-2 !h-2 !border-zinc-700" />
      <Handle type="source" position={Position.Right} className="!bg-zinc-600 !w-2 !h-2 !border-zinc-700" />

      <div className="flex items-center gap-2 mb-1">
        <span className={`w-2 h-2 rounded-full shrink-0 ${statusDotColors[data.status] || "bg-zinc-600"}`} />
        <span className="font-semibold text-sm text-text-primary truncate">
          {data.label}
        </span>
        {data.cached && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-700 text-zinc-300 shrink-0">
            cached
          </span>
        )}
      </div>

      {!isInput && (
        <div className="flex items-center gap-3 text-xs text-text-secondary">
          <span className={colors.text}>
            {data.status === "running" ? "running..." : data.status}
          </span>
          {data.duration > 0 && <span>{data.duration.toFixed(2)}s</span>}
          {data.signalCount > 0 && <span>{data.signalCount} sig</span>}
          {data.factCount > 0 && <span>{data.factCount} fact</span>}
        </div>
      )}
    </div>
  );
}

export const ModuleNode = memo(ModuleNodeComponent);
