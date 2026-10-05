"use client";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
type Row = Record<string, number | string | null>;
export function TrendChart({
  data,
  keys,
  height = 200,
  x = "t",
  area = false,
}: {
  data: Row[];
  keys: { key: string; color: string; name: string }[];
  height?: number;
  x?: string;
  area?: boolean;
}) {
  const Chart = area ? AreaChart : LineChart;
  return (
    <div style={{ height, width: "100%", minWidth: 0 }}>
      <ResponsiveContainer width="100%" height="100%">
        <Chart data={data}>
          <defs>
            {keys.map((k) => (
              <linearGradient
                key={k.key}
                id={`gradient-${k.key}`}
                x1="0"
                y1="0"
                x2="0"
                y2="1"
              >
                <stop offset="0%" stopColor={k.color} stopOpacity={0.2} />
                <stop offset="100%" stopColor={k.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid
            stroke="#263239"
            strokeDasharray="3 6"
            vertical={false}
          />
          <XAxis
            dataKey={x}
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#71838d", fontSize: 10 }}
            minTickGap={35}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fill: "#71838d", fontSize: 10 }}
            width={30}
          />
          <Tooltip
            contentStyle={{
              background: "#132129",
              border: "1px solid #34444d",
              borderRadius: 8,
              fontSize: 12,
            }}
          />
          {keys.map((k) =>
            area ? (
              <Area
                key={k.key}
                type="monotone"
                dataKey={k.key}
                name={k.name}
                stroke={k.color}
                fill={`url(#gradient-${k.key})`}
                strokeWidth={2}
                isAnimationActive={false}
              />
            ) : (
              <Line
                key={k.key}
                type="monotone"
                dataKey={k.key}
                name={k.name}
                stroke={k.color}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            ),
          )}
        </Chart>
      </ResponsiveContainer>
    </div>
  );
}
