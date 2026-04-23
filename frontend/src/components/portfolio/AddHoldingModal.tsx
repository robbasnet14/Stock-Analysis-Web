import { FormEvent, useEffect, useMemo, useState } from "react";
import { Position } from "../../types";

type AddHoldingInput = {
  lotId?: number;
  ticker: string;
  shares: number;
  buyPrice: number;
  buyTs?: string;
  mergeMode?: "ask" | "merge" | "new_lot";
};

export function AddHoldingModal({
  initialTicker,
  editRow,
  onEditClosed,
  onSubmit
}: {
  initialTicker: string;
  editRow?: Position | null;
  onEditClosed?: () => void;
  onSubmit: (row: AddHoldingInput) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [ticker, setTicker] = useState(initialTicker.toUpperCase());
  const [shares, setShares] = useState("1");
  const [buyPrice, setBuyPrice] = useState("");
  const [buyTs, setBuyTs] = useState("");
  const [error, setError] = useState("");
  const [duplicateChoiceOpen, setDuplicateChoiceOpen] = useState(false);

  const isEditMode = useMemo(() => Boolean(editRow), [editRow]);

  useEffect(() => {
    if (!editRow) return;
    setTicker(editRow.ticker.toUpperCase());
    setShares(String(editRow.quantity));
    setBuyPrice(String(editRow.avg_cost));
    setBuyTs(editRow.updated_at ? editRow.updated_at.slice(0, 10) : "");
    setError("");
    setOpen(true);
  }, [editRow]);

  const persist = async (mergeMode: "ask" | "merge" | "new_lot" = "ask") => {
    const parsedShares = Number(shares);
    const parsedPrice = Number(buyPrice);
    if (!Number.isFinite(parsedShares) || parsedShares < 0) {
      setError("Shares must be a valid number.");
      return;
    }
    if (!Number.isFinite(parsedPrice) || parsedPrice <= 0) {
      setError("Buy price must be greater than 0.");
      return;
    }

    if (isEditMode && parsedShares === 0) {
      const confirmed = window.confirm("Shares are set to 0. This will remove the holding. Continue?");
      if (!confirmed) return;
    }

    try {
      setError("");
      await onSubmit({
        lotId: editRow?.id,
        ticker: ticker.trim().toUpperCase(),
        shares: parsedShares,
        buyPrice: parsedPrice,
        buyTs: buyTs || undefined,
        mergeMode
      });
      setOpen(false);
      setDuplicateChoiceOpen(false);
      setShares("1");
      setBuyPrice("");
      setBuyTs("");
      if (onEditClosed) onEditClosed();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Unable to save holding.";
      if (!isEditMode && msg.toLowerCase().includes("already hold")) {
        setDuplicateChoiceOpen(true);
        setError("You already hold this ticker. Choose merge or add as new lot.");
      } else {
        setError(msg);
      }
    }
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    await persist("ask");
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md bg-cyan-500 px-3 py-2 text-sm font-semibold text-slate-950"
      >
        {isEditMode ? "Edit Holding" : "Add Holding"}
      </button>

      {open ? (
        <div className="fixed inset-0 z-40 grid place-items-center bg-slate-950/60 p-4">
          <form onSubmit={(e) => void submit(e)} className="w-full max-w-md space-y-3 rounded-xl border border-slate-300 bg-white p-4 shadow-xl dark:border-slate-700 dark:bg-slate-900">
            <h3 className="text-lg font-semibold">{isEditMode ? "Edit Portfolio Holding" : "Add Portfolio Holding"}</h3>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              placeholder="Ticker"
              required={!isEditMode}
              disabled={isEditMode}
            />
            <input
              value={shares}
              onChange={(e) => setShares(e.target.value)}
              type="number"
              step="0.0001"
              min="0"
              className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              placeholder="Shares"
              required
            />
            <input
              value={buyPrice}
              onChange={(e) => setBuyPrice(e.target.value)}
              type="number"
              step="0.0001"
              min="0.0001"
              className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              placeholder="Average buy price"
              required
            />
            <input
              value={buyTs}
              onChange={(e) => setBuyTs(e.target.value)}
              type="date"
              className="w-full rounded border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
              placeholder="Buy date"
            />
            {duplicateChoiceOpen ? (
              <div className="rounded border border-amber-400/40 bg-amber-500/10 p-2 text-xs text-amber-700 dark:text-amber-300">
                <p className="mb-2">You already hold {ticker}. Choose how to proceed:</p>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      void persist("new_lot");
                    }}
                    className="rounded border border-cyan-300 px-2 py-1"
                  >
                    Add as new lot
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      void persist("merge");
                    }}
                    className="rounded border border-emerald-300 px-2 py-1"
                  >
                    Merge into existing
                  </button>
                  <button
                    type="button"
                    onClick={() => setDuplicateChoiceOpen(false)}
                    className="rounded border border-slate-400 px-2 py-1"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : null}
            {error ? <p className="text-xs text-rose-500">{error}</p> : null}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  setDuplicateChoiceOpen(false);
                  if (onEditClosed) onEditClosed();
                }}
                className="rounded border border-slate-300 px-3 py-2 text-sm dark:border-slate-700"
              >
                Cancel
              </button>
              <button type="submit" className="rounded bg-cyan-500 px-3 py-2 text-sm font-semibold text-slate-950">
                Save
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );
}

export type { AddHoldingInput };
