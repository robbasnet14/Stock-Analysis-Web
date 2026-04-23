import { AlertEvent } from "../types/api";

interface AlertStreamProps {
  alerts: AlertEvent[];
}

export function AlertStream({ alerts }: AlertStreamProps) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Live Alerts</h2>
        <span>Bull breakouts, volume spikes, and catalysts</span>
      </div>
      <div className="alerts">
        {alerts.slice(0, 8).map((alert) => (
          <article key={alert.id} className={`alert alert-${alert.severity}`}>
            <p className="alert-meta">
              <strong>{alert.symbol}</strong> · {new Date(alert.createdAt).toLocaleTimeString()}
            </p>
            <p>{alert.message}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
