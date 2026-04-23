import { BullCaseSignal } from "../types/api";

interface BullCaseBoardProps {
  signals: BullCaseSignal[];
}

export function BullCaseBoard({ signals }: BullCaseBoardProps) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Bull Cases</h2>
        <span>Scored by momentum, volume, sentiment, and insider proxy</span>
      </div>
      <div className="bull-grid">
        {signals.slice(0, 6).map((signal) => (
          <article key={signal.symbol} className="bull-card">
            <header>
              <h3>{signal.symbol}</h3>
              <p>{signal.horizon.toUpperCase()}</p>
            </header>
            <p className="score">Score {signal.score}</p>
            <p className="rr">R/R {signal.riskReward}</p>
            <p className="entry">Entry ${signal.entry}</p>
            <ul>
              {signal.notes.slice(0, 2).map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
