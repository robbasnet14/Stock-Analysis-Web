interface MetricStripProps {
  items: Array<{ label: string; value: string; tone?: "neutral" | "good" | "warn" }>;
}

export function MetricStrip({ items }: MetricStripProps) {
  return (
    <section className="metric-strip">
      {items.map((item) => (
        <article key={item.label} className={`metric-card tone-${item.tone ?? "neutral"}`}>
          <p className="metric-label">{item.label}</p>
          <p className="metric-value">{item.value}</p>
        </article>
      ))}
    </section>
  );
}
