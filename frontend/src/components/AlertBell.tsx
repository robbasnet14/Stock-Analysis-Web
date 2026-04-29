import { useEffect, useMemo, useState } from "react";
import { Bell } from "lucide-react";
import { Link } from "react-router-dom";
import { listAlertHistory } from "../services/api";
import { isAuthenticated } from "../services/auth";
import { createAlertSocket } from "../services/websocket";
import { AlertFire } from "../types";

function label(item: AlertFire | any): string {
  const ticker = String(item.ticker ?? "");
  const summary = String(item.condition_summary ?? item.message ?? "Alert fired");
  return ticker ? `${ticker}: ${summary}` : summary;
}

export default function AlertBell() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AlertFire[]>([]);
  const [unread, setUnread] = useState(0);
  const [toast, setToast] = useState<AlertFire | any | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) return;
    void listAlertHistory(10).then(setItems).catch(() => undefined);
    const ws = createAlertSocket((payload) => {
      const item = {
        id: Number(payload.fire_id ?? Date.now()),
        alert_id: Number(payload.alert_id ?? 0),
        ticker: String(payload.ticker ?? ""),
        condition_type: String(payload.condition_type ?? ""),
        condition_summary: String(payload.condition_summary ?? "Alert fired"),
        message: String(payload.message ?? ""),
        payload,
        channel: String(payload.channel ?? "web"),
        fired_at: String(payload.fired_at ?? new Date().toISOString()),
        read_at: null
      } as AlertFire;
      setItems((current) => [item, ...current].slice(0, 10));
      setUnread((value) => value + 1);
      setToast(item);
      window.setTimeout(() => setToast(null), 5000);
    });
    return () => ws?.close();
  }, []);

  const latest = useMemo(() => items.slice(0, 10), [items]);

  if (!isAuthenticated()) return null;

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => {
          setOpen((value) => !value);
          setUnread(0);
        }}
        className="relative rounded-md border border-slate-300 bg-slate-100 p-2 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
        aria-label="Alerts"
      >
        <Bell size={16} />
        {unread ? <span className="absolute -right-1 -top-1 min-w-4 rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white">{unread}</span> : null}
      </button>
      {open ? (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-lg border border-slate-300 bg-white p-2 shadow-xl dark:border-slate-700 dark:bg-slate-900">
          <div className="flex items-center justify-between px-2 py-1">
            <p className="text-sm font-semibold">Alerts</p>
            <Link to="/account" className="text-xs text-cyan-500" onClick={() => setOpen(false)}>
              Manage
            </Link>
          </div>
          <div className="max-h-80 overflow-y-auto">
            {latest.map((item) => (
              <Link key={`${item.id}-${item.fired_at}`} to={`/signals/${encodeURIComponent(item.ticker)}`} onClick={() => setOpen(false)} className="block rounded-md px-2 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
                <p className="font-medium">{label(item)}</p>
                <p className="text-xs text-slate-500">{new Date(item.fired_at).toLocaleString()}</p>
              </Link>
            ))}
            {latest.length === 0 ? <p className="px-2 py-3 text-sm text-slate-500">No fired alerts yet.</p> : null}
          </div>
        </div>
      ) : null}
      {toast ? (
        <div className="fixed right-4 top-20 z-30 w-80 rounded-lg border border-cyan-400/40 bg-slate-950 p-3 text-sm text-white shadow-xl">
          <p className="font-semibold">{label(toast)}</p>
          <p className="mt-1 text-xs text-slate-400">Triggered {new Date(toast.fired_at).toLocaleTimeString()}</p>
        </div>
      ) : null}
    </div>
  );
}
