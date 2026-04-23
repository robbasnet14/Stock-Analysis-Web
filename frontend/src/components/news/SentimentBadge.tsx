export function SentimentBadge({ label }: { label: string }) {
  const key = label.toLowerCase();
  const cls = key.includes("bull") || key.includes("pos")
    ? "bg-emerald-500/20 text-emerald-600 dark:text-emerald-300"
    : key.includes("bear") || key.includes("neg")
      ? "bg-rose-500/20 text-rose-600 dark:text-rose-300"
      : "bg-slate-400/20 text-slate-600 dark:text-slate-300";

  return <span className={`rounded-full px-2 py-1 text-xs font-semibold ${cls}`}>{label}</span>;
}
