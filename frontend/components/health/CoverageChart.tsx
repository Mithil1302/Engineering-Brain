/**
 * CoverageChart - Recharts BarChart for service coverage
 * Task 4.5: Create CoverageChart (Recharts BarChart)
 */

import { useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { useRouter } from "next/navigation";
import { getHealthColor, truncate } from "@/lib/utils";
import type { CoverageEntry } from "@/lib/types";

interface CoverageChartProps {
  coverage?: CoverageEntry[];
}

export function CoverageChart({ coverage }: CoverageChartProps) {
  const router = useRouter();
  const [showAll, setShowAll] = useState(false);

  if (!coverage || coverage.length === 0) {
    return (
      <div className="glass rounded-2xl p-4">
        <div className="text-sm font-semibold text-white mb-4">Service Coverage</div>
        <div className="h-[200px] flex items-center justify-center">
          <p className="text-xs text-slate-500">No coverage data available</p>
        </div>
      </div>
    );
  }

  // Sort by coverage ascending (worst at top)
  const sortedCoverage = [...coverage].sort(
    (a, b) => a.coverage_percentage - b.coverage_percentage
  );

  // Show top 15 by default
  const displayData = showAll ? sortedCoverage : sortedCoverage.slice(0, 15);

  // Calculate height: 32px per service, clamped to 200-500px
  const height = Math.max(200, Math.min(500, displayData.length * 32));

  const handleBarClick = (data: CoverageEntry) => {
    router.push(`/graph?selected=${encodeURIComponent(data.service_id)}`);
  };

  return (
    <div className="glass rounded-2xl p-4">
      <div className="text-sm font-semibold text-white mb-4">Service Coverage</div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={displayData} layout="vertical">
          <XAxis
            type="number"
            domain={[0, 100]}
            tick={{ fontSize: 10, fill: "#94a3b8" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => `${value}%`}
          />

          <YAxis
            type="category"
            dataKey="service_name"
            tick={{ fontSize: 12, fill: "#94a3b8", textAnchor: "end" }}
            tickLine={false}
            axisLine={false}
            width={120}
            tickFormatter={(value) => truncate(value, 20)}
          />

          <Tooltip
            contentStyle={{
              background: "#1e293b",
              border: "1px solid #334155",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "#94a3b8" }}
            formatter={(value: any) => value !== undefined ? [`${Number(value).toFixed(1)}%`, "Coverage"] : ["", ""]}
          />

          <Bar
            dataKey="coverage_percentage"
            radius={[0, 4, 4, 0]}
            cursor="pointer"
            onClick={(data) => handleBarClick(data as unknown as CoverageEntry)}
          >
            {displayData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={getHealthColor(entry.coverage_percentage)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      {!showAll && sortedCoverage.length > 15 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-3 text-xs text-blue-400 hover:text-blue-300"
        >
          Show all {sortedCoverage.length} services
        </button>
      )}
    </div>
  );
}
