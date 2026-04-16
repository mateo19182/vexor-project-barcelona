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
  isNew: boolean;
}

function ModuleNodeComponent({ data }: { data: ModuleNodeData }) {
  const colors = getStatusColor(data.status);
  const isInput = data.label === "Case Input";

  return (
    <div
      className={`
        rounded-xl border px-4 py-3 min-w-[180px]
        ${colors.border} ${colors.bg}
        bg-bg-surface/80 backdrop-blur-sm
        hover:shadow-lg hover:shadow-black/30
        ${data.isNew ? 'animate-[popIn_0.4s_cubic-bezier(0.34,1.56,0.64,1)_forwards]' : ''}
      `}
      style={{
        opacity: data.isNew ? 0 : 1,
        transform: data.isNew ? 'scale(0)' : 'scale(1)',
      }}
    >
      <Handle type="target" position={Position.Left} className="!bg-zinc-600 !w-1.5 !h-1.5 !border-0" />
      <Handle type="source" position={Position.Right} className="!bg-zinc-600 !w-1.5 !h-1.5 !border-0" />

      <div className="flex items-center gap-2 mb-0.5">
        <span className={`w-2 h-2 rounded-full shrink-0 ${statusDotColors[data.status] || "bg-zinc-600"}`} />
        <span className="font-semibold text-xs text-text-primary truncate">
          {data.label}
        </span>
        {data.cached && (
          <span className="text-[9px] px-1 py-0.5 rounded bg-zinc-700 text-zinc-400 shrink-0">
            cached
          </span>
        )}
      </div>

      {!isInput && (
        <div className="flex items-center gap-2 text-[10px] text-text-secondary">
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
