import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PricePoint } from "../../types";

function formatTs(value: string) {
  const dt = new Date(value);
  return `${dt.getMonth() + 1}/${dt.getDate()} ${dt.getHours()}:${String(dt.getMinutes()).padStart(2, "0")}`;
}

export function PortfolioChart({
  data,
  onHover
}: {
  data: PricePoint[];
  onHover?: (point: PricePoint | null) => void;
}) {
  return (
    <div className="h-[320px] w-full overflow-hidden rounded-xl border border-slate-800 bg-[#020b2d] p-2 md:h-[420px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          onMouseMove={(state) => {
            if (!onHover) return;
            const active = state?.activePayload?.[0]?.payload as PricePoint | undefined;
            onHover(active ?? null);
          }}
          onMouseLeave={() => onHover?.(null)}
        >
          <defs>
            <linearGradient id="portfolioFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#2dd4bf" stopOpacity={0.35} />
              <stop offset="95%" stopColor="#2dd4bf" stopOpacity={0.03} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(76, 110, 164, 0.25)" />
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatTs}
            minTickGap={30}
            tick={{ fill: "#8ea4c7", fontSize: 11 }}
            stroke="#22487f"
          />
          <YAxis tick={{ fill: "#8ea4c7", fontSize: 11 }} stroke="#22487f" domain={["auto", "auto"]} width={80} />
          <Tooltip
            labelFormatter={(label) => new Date(String(label)).toLocaleString()}
            formatter={(value: number) => [`$${Number(value).toFixed(2)}`, "Portfolio"]}
            contentStyle={{ background: "#06163d", border: "1px solid #1f4b85", color: "#d9e4f8" }}
          />
          <Area type="monotone" dataKey="price" stroke="#2dd4bf" fill="url(#portfolioFill)" strokeWidth={2} dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
