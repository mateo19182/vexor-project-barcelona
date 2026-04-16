export const statusColors: Record<string, { bg: string; text: string; border: string }> = {
  ok:      { bg: "bg-emerald-500/20", text: "text-emerald-400", border: "border-emerald-500/40" },
  error:   { bg: "bg-red-500/20",     text: "text-red-400",     border: "border-red-500/40" },
  skipped: { bg: "bg-zinc-500/20",    text: "text-zinc-400",    border: "border-zinc-500/40" },
  no_data: { bg: "bg-purple-500/20",  text: "text-purple-400",  border: "border-purple-500/40" },
  cached:  { bg: "bg-blue-500/20",    text: "text-blue-400",    border: "border-blue-500/40" },
  pending: { bg: "bg-zinc-700/20",    text: "text-zinc-500",    border: "border-zinc-700/40" },
  running: { bg: "bg-amber-500/20",   text: "text-amber-400",   border: "border-amber-500/40" },
};

export const statusDotColors: Record<string, string> = {
  ok:      "bg-emerald-400",
  error:   "bg-red-400",
  skipped: "bg-zinc-500",
  no_data: "bg-purple-400",
  cached:  "bg-blue-400",
  pending: "bg-zinc-600",
  running: "bg-amber-400 animate-pulse",
};

export function getStatusColor(status: string) {
  return statusColors[status] || statusColors.pending;
}
