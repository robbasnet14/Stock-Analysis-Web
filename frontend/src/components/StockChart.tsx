import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { PricePoint } from "../types";

interface Props {
  data: PricePoint[];
  range?: "1D" | "1W" | "1M" | "1Y";
  onHoverPoint?: (point: PricePoint | null) => void;
  strokeColor?: string;
}

export function StockChart({ data, range = "1D", onHoverPoint, strokeColor = "#22c55e" }: Props) {
  const chartData = data.map((row) => ({
    ...row,
    time:
      range === "1Y"
        ? new Date(row.timestamp).toLocaleDateString(undefined, { month: "short", day: "numeric" })
        : new Date(row.timestamp).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
  }));

  return (
    <div className="h-[320px] w-full select-none rounded-xl border border-slate-700/40 bg-slate-950/80 p-2 shadow-sm touch-pan-y md:h-[380px] dark:border-slate-700/40 dark:bg-slate-950/90">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={chartData}
          onMouseMove={(state) => {
            const payload = state?.activePayload?.[0]?.payload as PricePoint | undefined;
            onHoverPoint?.(payload ?? null);
          }}
          onMouseLeave={() => onHoverPoint?.(null)}
        >
          <defs>
            <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={strokeColor} stopOpacity={0.42} />
              <stop offset="95%" stopColor={strokeColor} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <XAxis dataKey="time" hide />
          <YAxis hide domain={["dataMin - 1", "dataMax + 1"]} />
          <Tooltip
            cursor={{ stroke: "#94a3b8", strokeWidth: 1, strokeDasharray: "3 3" }}
            content={() => null}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke={strokeColor}
            fill="url(#priceGradient)"
            strokeWidth={2.6}
            dot={false}
            activeDot={{ r: 5, fill: strokeColor, stroke: "#0f172a", strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
