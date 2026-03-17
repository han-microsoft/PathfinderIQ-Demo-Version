/** Metric row — label left, value right, monospace at 12.5px. */
export function MetricRow({
  label,
  value,
  color = "text-text-secondary",
}: {
  label: string;
  value: string | number;
  color?: string;
}) {
  const display = typeof value === "number" ? value.toLocaleString() : value;
  return (
    <div className="flex items-center justify-between text-[15px] font-mono">
      <span className="text-text-muted">{label}</span>
      <span className={color}>{display}</span>
    </div>
  );
}
