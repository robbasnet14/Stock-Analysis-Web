import { useEffect, useState } from "react";
import { AuthPanel } from "../components/AuthPanel";
import { listAdminUsers, me, setAdminUserRole } from "../services/api";
import { isAuthenticated } from "../services/auth";
import { AdminUser, UserProfile } from "../types";

export default function Account() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [users, setUsers] = useState<AdminUser[]>([]);
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
    } catch {
      setUser(null);
      setUsers([]);
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
