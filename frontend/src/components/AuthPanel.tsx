import { FormEvent, useState } from "react";
import { clearTokens, isAuthenticated, setTokens } from "../services/auth";
import { login, logout, register } from "../services/api";
import { UserProfile } from "../types";

interface Props {
  user: UserProfile | null;
  onAuthChange: () => Promise<void>;
}

type FieldErrors = Partial<Record<"email" | "first_name" | "last_name" | "date_of_birth" | "password" | "password_confirm", string>>;

export function AuthPanel({ user, onAuthChange }: Props) {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [dob, setDob] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordConfirm, setPasswordConfirm] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});

  function passwordHint(pw: string): string {
    if (pw.length < 8) return "Password needs at least 8 characters.";
    if (!/[A-Z]/.test(pw)) return "Add an uppercase letter.";
    if (!/[a-z]/.test(pw)) return "Add a lowercase letter.";
    if (!/[0-9]/.test(pw)) return "Add a number.";
    if (!/[^A-Za-z0-9]/.test(pw)) return "Add a special character.";
    return "";
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      setError("");
      setFieldErrors({});
      if (mode === "register") {
        if (!firstName.trim() || !lastName.trim()) {
          setFieldErrors({
            first_name: !firstName.trim() ? "First name is required." : undefined,
            last_name: !lastName.trim() ? "Last name is required." : undefined
          });
          return;
        }
        if (!dob) {
          setFieldErrors({ date_of_birth: "Date of birth is required." });
          return;
        }
        const pwHint = passwordHint(password);
        if (pwHint) {
          setFieldErrors({ password: pwHint });
          return;
        }
        if (password !== passwordConfirm) {
          setFieldErrors({ password_confirm: "Passwords must match." });
          return;
        }
      }

      const tokens =
        mode === "login"
          ? await login(email, password)
          : await register({
              first_name: firstName.trim(),
              last_name: lastName.trim(),
              date_of_birth: dob,
              email,
              password,
              password_confirm: passwordConfirm
            });
      setTokens(tokens.access_token, tokens.refresh_token);
      await onAuthChange();
      setPassword("");
      setPasswordConfirm("");
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      if (Array.isArray(detail)) {
        const next: FieldErrors = {};
        for (const item of detail) {
          const loc = Array.isArray((item as { loc?: unknown }).loc) ? ((item as { loc?: unknown[] }).loc as unknown[]) : [];
          const msg = typeof (item as { msg?: unknown }).msg === "string" ? String((item as { msg?: string }).msg) : "";
          const field = String(loc[loc.length - 1] || "");
          if (msg && (field === "email" || field === "first_name" || field === "last_name" || field === "date_of_birth" || field === "password" || field === "password_confirm")) {
            next[field] = msg;
          }
        }
        if (Object.keys(next).length) {
          setFieldErrors(next);
          setError("");
          return;
        }
      }
      setError(err instanceof Error ? err.message : "Auth failed");
    }
  }

  async function handleLogout() {
    try {
      await logout();
    } catch {
      clearTokens();
    }
    await onAuthChange();
  }

  if (user) {
    return (
      <div className="rounded-md border border-emerald-400/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">
        <p>
          {user.email} ({user.role})
        </p>
        <button onClick={handleLogout} className="mt-1 text-rose-200 hover:text-rose-100">
          Logout
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="rounded-md border border-slate-600 bg-slate-900/70 p-2 text-xs text-slate-200">
      <div className="mb-2 flex gap-1">
        <button type="button" onClick={() => setMode("login")} className={`rounded px-2 py-1 ${mode === "login" ? "bg-cyan-500 text-slate-950" : "bg-slate-800"}`}>
          Login
        </button>
        <button type="button" onClick={() => setMode("register")} className={`rounded px-2 py-1 ${mode === "register" ? "bg-cyan-500 text-slate-950" : "bg-slate-800"}`}>
          Register
        </button>
      </div>
      <input
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="email"
        className="mb-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1"
      />
      {fieldErrors.email ? <p className="mb-1 text-[11px] text-rose-300">{fieldErrors.email}</p> : null}
      {mode === "register" ? (
        <>
          <input
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            placeholder="first name"
            className="mb-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1"
          />
          {fieldErrors.first_name ? <p className="mb-1 text-[11px] text-rose-300">{fieldErrors.first_name}</p> : null}
          <input
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            placeholder="last name"
            className="mb-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1"
          />
          {fieldErrors.last_name ? <p className="mb-1 text-[11px] text-rose-300">{fieldErrors.last_name}</p> : null}
          <input
            type="date"
            value={dob}
            onChange={(e) => setDob(e.target.value)}
            className="mb-1 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1"
          />
          {fieldErrors.date_of_birth ? <p className="mb-1 text-[11px] text-rose-300">{fieldErrors.date_of_birth}</p> : null}
        </>
      ) : null}
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="password"
        className="mb-2 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1"
      />
      {fieldErrors.password ? <p className="mb-1 text-[11px] text-rose-300">{fieldErrors.password}</p> : null}
      {mode === "register" ? (
        <>
          <input
            type="password"
            value={passwordConfirm}
            onChange={(e) => setPasswordConfirm(e.target.value)}
            placeholder="confirm password"
            className="mb-2 w-full rounded border border-slate-600 bg-slate-950 px-2 py-1"
          />
          {fieldErrors.password_confirm ? <p className="mb-1 text-[11px] text-rose-300">{fieldErrors.password_confirm}</p> : null}
        </>
      ) : null}
      <button className="w-full rounded bg-cyan-500 px-2 py-1 font-semibold text-slate-950">{mode === "login" ? "Sign in" : "Create account"}</button>
      {error ? <p className="mt-1 text-[11px] text-rose-300">{error}</p> : null}
      {!isAuthenticated() ? <p className="mt-1 text-[11px] text-slate-400">Sign in to save portfolios & watchlist</p> : null}
    </form>
  );
}
