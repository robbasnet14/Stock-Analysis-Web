import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "./context/ThemeContext";
import "./styles.css";

const App = lazy(() => import("./App"));

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ThemeProvider>
      <Suspense fallback={<main className="min-h-screen bg-slate-950 p-6 text-slate-200">Loading dashboard...</main>}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </Suspense>
    </ThemeProvider>
  </React.StrictMode>
);
