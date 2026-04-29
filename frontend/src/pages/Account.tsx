import { useEffect, useState } from "react";
import { AuthPanel } from "../components/AuthPanel";
import { deleteAlert, listAdminUsers, listAlertHistory, listAlerts, me, setAdminUserRole, updateAlert } from "../services/api";
import { isAuthenticated } from "../services/auth";
import { AdminUser, AlertFire, AlertSubscription, UserProfile } from "../types";

export default function Account() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [alerts, setAlerts] = useState<AlertSubscription[]>([]);
  const [alertHistory, setAlertHistory] = useState<AlertFire[]>([]);
  const [alertTab, setAlertTab] = useState<"active" | "history">("active");
  const [error, setError] = useState("");

  async function refresh() {
    if (!isAuthenticated()) {
      setUser(null);
      setUsers([]);
      return;
    }

    try {
      const profile = await me();
      setUser(profile);
      if (profile.role === "admin") {
        setUsers(await listAdminUsers());
      } else {
        setUsers([]);
      }
      const [nextAlerts, nextHistory] = await Promise.all([listAlerts(), listAlertHistory(50)]);
      setAlerts(nextAlerts);
      setAlertHistory(nextHistory);
    } catch {
      setUser(null);
      setUsers([]);
      setAlerts([]);
      setAlertHistory([]);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function updateRole(targetUserId: number, role: "admin" | "trader" | "viewer") {
    try {
      setError("");
      await setAdminUserRole(targetUserId, role);
      setUsers(await listAdminUsers());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Role update failed");
    }
  }

  async function toggleAlert(row: AlertSubscription) {
    try {
      setError("");
      await updateAlert(row.id, { enabled: !row.enabled });
      setAlerts(await listAlerts());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Alert update failed");
    }
  }

  async function removeAlert(id: number) {
    try {
      setError("");
      await deleteAlert(id);
      setAlerts(await listAlerts());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Alert delete failed");
    }
  }

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between rounded-xl border border-slate-300 bg-white/80 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
        <div>
          <h1 className="text-2xl font-bold">Account</h1>
          <p className="text-sm text-slate-600 dark:text-slate-300">Profile and access management.</p>
        </div>
        <AuthPanel user={user} onAuthChange={refresh} />
      </header>

      {!user ? <p className="text-sm text-slate-500 dark:text-slate-400">Sign in to access account settings.</p> : null}

      {user && user.role !== "admin" ? (
        <div className="rounded-xl border border-slate-300 bg-white/80 p-4 text-sm dark:border-slate-700 dark:bg-slate-900/70">
          Signed in as <strong>{user.email}</strong> ({user.role}). Admin tools are only visible for admin users.
        </div>
      ) : null}

      {user ? (
        <section className="rounded-xl border border-slate-300 bg-white/80 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">My Alerts</h2>
              <p className="text-sm text-slate-600 dark:text-slate-300">Autonomous triggers for prices, signals, news, and earnings.</p>
            </div>
            <div className="flex gap-2">
              {(["active", "history"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setAlertTab(tab)}
                  className={`rounded-md px-3 py-1 text-sm ${alertTab === tab ? "bg-cyan-500 text-slate-950" : "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-200"}`}
                >
                  {tab === "active" ? "Active alerts" : "Recent fires"}
                </button>
              ))}
            </div>
          </div>
          {error ? <p className="mt-3 text-xs text-rose-500">{error}</p> : null}

          {alertTab === "active" ? (
            <div className="mt-4 space-y-2">
              {alerts.map((alert) => (
                <div key={alert.id} className="flex flex-wrap items-center justify-between gap-3 rounded border border-slate-300 p-3 dark:border-slate-700">
                  <div>
                    <p className="font-semibold">{alert.ticker} · {alert.condition_type.replace("_", " ")}</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">{JSON.stringify(alert.condition_params)} · {alert.channel} · {alert.enabled ? "enabled" : "disabled"}</p>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" onClick={() => void toggleAlert(alert)} className="rounded border border-slate-300 px-2 py-1 text-xs dark:border-slate-600">
                      {alert.enabled ? "Disable" : "Enable"}
                    </button>
                    <button type="button" onClick={() => void removeAlert(alert.id)} className="rounded border border-rose-400/50 px-2 py-1 text-xs text-rose-500">
                      Delete
                    </button>
                  </div>
                </div>
              ))}
              {alerts.length === 0 ? <p className="text-sm text-slate-500 dark:text-slate-400">No alerts yet. Open a signal detail page to create one.</p> : null}
            </div>
          ) : (
            <div className="mt-4 space-y-2">
              {alertHistory.map((fire) => (
                <div key={fire.id} className="rounded border border-slate-300 p-3 dark:border-slate-700">
                  <p className="font-semibold">{fire.ticker} · {fire.condition_summary}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{new Date(fire.fired_at).toLocaleString()} · {fire.channel}</p>
                </div>
              ))}
              {alertHistory.length === 0 ? <p className="text-sm text-slate-500 dark:text-slate-400">No fired alerts yet.</p> : null}
            </div>
          )}
        </section>
      ) : null}

      {user?.role === "admin" ? (
        <section className="rounded-xl border border-slate-300 bg-white/80 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/70">
          <h2 className="mb-3 text-lg font-semibold">User Access Control</h2>
          {error ? <p className="mb-2 text-xs text-rose-500">{error}</p> : null}
          <div className="space-y-2">
            {users.map((u) => (
              <div key={u.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-300 p-3 dark:border-slate-700">
                <div>
                  <p className="font-semibold">{u.email}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">Current role: {u.role}</p>
                </div>
                <div className="flex gap-2">
                  {(["viewer", "trader", "admin"] as const).map((role) => (
                    <button
                      key={role}
                      onClick={() => void updateRole(u.id, role)}
                      className="rounded border border-slate-300 px-2 py-1 text-xs dark:border-slate-600"
                    >
                      {role}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            {users.length === 0 ? <p className="text-sm text-slate-500 dark:text-slate-400">No users found.</p> : null}
          </div>
        </section>
      ) : null}
    </section>
  );
}
