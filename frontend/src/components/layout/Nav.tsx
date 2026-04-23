import { Link, useLocation } from "react-router-dom";

function Item({ to, label }: { to: string; label: string }) {
  const { pathname } = useLocation();
  const active = pathname === to;
  return (
    <Link
      to={to}
      className={`rounded-md px-3 py-1 text-sm ${
        active ? "bg-cyan-500 text-slate-950" : "bg-slate-200 text-slate-700 hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-200"
      }`}
    >
      {label}
    </Link>
  );
}

export default function Nav() {
  return (
    <nav className="flex flex-wrap items-center gap-2">
      <Item to="/" label="Dashboard" />
      <Item to="/portfolio" label="Portfolio" />
      <Item to="/signals" label="Signals" />
      <Item to="/news" label="News" />
      <Item to="/account" label="Account" />
    </nav>
  );
}
