import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "./context/ThemeContext";
import Navbar from "./components/Navbar";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const News = lazy(() => import("./pages/News"));
const Signals = lazy(() => import("./pages/Signals"));
const Portfolio = lazy(() => import("./pages/Portfolio"));
const Account = lazy(() => import("./pages/Account"));

export default function App() {
  const { theme, toggleTheme } = useTheme();

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-100 via-cyan-50 to-slate-200 p-4 text-slate-900 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950 dark:text-slate-100">
      <div className="mx-auto max-w-7xl space-y-4">
        <header className="flex items-center justify-between rounded-xl border border-slate-300 bg-white/80 p-3 shadow-sm backdrop-blur dark:border-slate-700 dark:bg-slate-900/70">
          <Navbar />
          <button
            onClick={toggleTheme}
            className="rounded-md border border-slate-300 bg-slate-100 p-2 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          </button>
        </header>

        <Suspense fallback={<div className="rounded-xl border border-slate-700/60 bg-slate-900/70 p-6 text-sm text-slate-300">Loading page...</div>}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/news" element={<News />} />
            <Route path="/signals" element={<Signals />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/account" element={<Account />} />
            <Route path="/admin" element={<Navigate to="/account" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </div>
    </main>
  );
}
