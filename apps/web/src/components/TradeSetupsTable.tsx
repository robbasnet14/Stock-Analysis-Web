import { TradeSetup } from "../types/api";

interface TradeSetupsTableProps {
  setups: TradeSetup[];
}

export function TradeSetupsTable({ setups }: TradeSetupsTableProps) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Entry / Target / Risk</h2>
        <span>Data-backed setups for short and long horizon</span>
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Horizon</th>
              <th>Entry</th>
              <th>Target</th>
              <th>Stop</th>
              <th>R/R</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {setups.slice(0, 10).map((setup) => (
              <tr key={`${setup.symbol}-${setup.horizon}`}>
                <td>{setup.symbol}</td>
                <td>{setup.horizon}</td>
                <td>${setup.entry}</td>
                <td>${setup.target}</td>
                <td>${setup.stopLoss}</td>
                <td>{setup.riskReward}</td>
                <td>{Math.round(setup.confidence * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
