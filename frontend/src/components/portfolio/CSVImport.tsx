import { useState } from "react";
import { importPositionsCsv } from "../../services/api";

export function CSVImport({ onDone }: { onDone: () => Promise<void> }) {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState("");

  const runImport = async () => {
    if (!file) return;
    setStatus("Importing...");
    try {
      const result = await importPositionsCsv(file);
      setStatus(`Imported ${result.imported_positions} holdings. ${result.lines_with_errors} row(s) had issues.`);
      await onDone();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "CSV import failed");
    }
  };

  return (
    <div className="rounded-xl border border-slate-300 bg-white/80 p-4 dark:border-slate-700 dark:bg-slate-900/70">
      <h3 className="text-sm font-semibold">Import Holdings CSV</h3>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Use columns like ticker/symbol, quantity/shares, avg cost or cost basis.</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} className="text-xs" />
        <button type="button" onClick={() => void runImport()} className="rounded bg-cyan-500 px-3 py-1 text-xs font-semibold text-slate-950" disabled={!file}>
          Import
        </button>
      </div>
      {status ? <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{status}</p> : null}
    </div>
  );
}
