import { useMemo } from 'react'
import { ReactFlow, type Node, type Edge, Background, BackgroundVariant } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { ModuleNode } from '@/lib/mock-run'

const statusBorder: Record<string, string> = {
  ok: '#FAFAFA',
  running: '#FAFAFA',
  skipped: '#3F3F46',
  error: '#71717A',
  no_data: '#52525B',
  pending: '#27272A',
}

const statusBg: Record<string, string> = {
  ok: '#19191C',
  running: '#19191C',
  skipped: '#111113',
  error: '#19191C',
  no_data: '#111113',
  pending: '#0E0E10',
}

function ModuleNodeLabel({ data }: { data: ModuleNode }) {
  return (
    <div
      className="px-3 py-2 rounded-lg border text-left min-w-[120px]"
      style={{
        borderColor: statusBorder[data.status] ?? '#27272A',
        backgroundColor: statusBg[data.status] ?? '#111113',
      }}
    >
      <div className="flex items-center gap-2">
        <span
          className={`w-1.5 h-1.5 rounded-full ${data.status === 'running' ? 'animate-pulse' : ''}`}
          style={{ backgroundColor: statusBorder[data.status] ?? '#27272A' }}
        />
        <span className="text-xs font-mono text-[#FAFAFA]">{data.name}</span>
      </div>
      {data.signalCount > 0 && (
        <span className="text-[10px] text-[#A1A1AA] mt-1 block">
          {data.signalCount} signal{data.signalCount !== 1 ? 's' : ''}
        </span>
      )}
    </div>
  )
}

const nodeTypes = {
  module: ModuleNodeLabel,
}

export function ModuleGraph({ modules }: { modules: ModuleNode[] }) {
  const { nodes, edges } = useMemo(() => {
    const cols = 3
    const xGap = 200
    const yGap = 80
    const xOffset = 40
    const yOffset = 40

    const nodes = modules.map((m, i) => ({
      id: m.name,
      type: 'module' as const,
      position: {
        x: xOffset + (i % cols) * xGap,
        y: yOffset + Math.floor(i / cols) * yGap,
      },
      data: m as ModuleNode & Record<string, unknown>,
      draggable: true,
    })) satisfies Node[]

    const edges: Edge[] = []
    return { nodes, edges }
  }, [modules])

  return (
    <div className="h-full bg-bg-surface/40 backdrop-blur-lg rounded-lg border border-border-subtle overflow-hidden">
      <div className="px-4 py-3 border-b border-border-subtle">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Graph</span>
      </div>
      <div className="h-[calc(100%-40px)]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          proOptions={{ hideAttribution: true }}
          panOnDrag
          zoomOnScroll
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="rgba(255,255,255,0.04)" />
        </ReactFlow>
      </div>
    </div>
  )
}
