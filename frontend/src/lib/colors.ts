export const statusColors: Record<string, { bg: string; text: string; border: string }> = {
  ok:      { bg: "bg-white/5",      text: "text-white",       border: "border-white/20" },
  error:   { bg: "bg-zinc-500/10",  text: "text-zinc-400",    border: "border-zinc-500/30" },
  skipped: { bg: "bg-zinc-700/10",  text: "text-zinc-500",    border: "border-zinc-700/30" },
  no_data: { bg: "bg-zinc-600/10",  text: "text-zinc-400",    border: "border-zinc-600/30" },
  cached:  { bg: "bg-zinc-400/10",  text: "text-zinc-300",    border: "border-zinc-400/30" },
  pending: { bg: "bg-zinc-800/20",  text: "text-zinc-600",    border: "border-zinc-800/30" },
  running: { bg: "bg-white/5",      text: "text-white",       border: "border-white/20" },
};

export const statusDotColors: Record<string, string> = {
  ok:      "bg-white",
  error:   "bg-zinc-400",
  skipped: "bg-zinc-600",
  no_data: "bg-zinc-500",
  cached:  "bg-zinc-300",
  pending: "bg-zinc-700",
  running: "bg-white animate-pulse",
};

export function getStatusColor(status: string) {
  return statusColors[status] || statusColors.pending;
}
