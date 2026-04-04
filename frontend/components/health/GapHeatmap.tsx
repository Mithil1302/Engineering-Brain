/**
 * GapHeatmap - Custom SVG heatmap for documentation gaps
 * Task 4.6: Create GapHeatmap (custom SVG 53x7 grid)
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getGapColor } from "@/lib/utils";
import type { GapDay } from "@/lib/types";

interface GapHeatmapProps {
  gapTimeline?: GapDay[];
}

export function GapHeatmap({ gapTimeline }: GapHeatmapProps) {
  const router = useRouter();
  const [hoveredCell, setHoveredCell] = useState<{ date: string; count: number; x: number; y: number } | null>(
    null
  );

  if (!gapTimeline || gapTimeline.length === 0) {
    return (
      <div className="glass rounded-2xl p-4">
        <div className="text-sm font-semibold text-white mb-4">Gap Timeline (52 weeks)</div>
        <div className="h-[200px] flex items-center justify-center">
          <p className="text-xs text-slate-500">No gap data available</p>
        </div>
      </div>
    );
  }

  // Detect dark mode
  const isDark = true; // TODO: Use theme context or matchMedia

  // Build 53 weeks x 7 days grid
  const cellSize = 12;
  const cellGap = 3;
  const cellTotal = cellSize + cellGap;

  // Get last 371 days (53 weeks)
  const today = new Date();
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - 371);

  // Create grid data
  const gridData: Array<{ date: Date; gapCount: number; week: number; day: number }> = [];
  const gapMap = new Map(gapTimeline.map((g) => [g.date, g.gap_count]));

  for (let i = 0; i < 371; i++) {
    const date = new Date(startDate);
    date.setDate(date.getDate() + i);
    const dateStr = date.toISOString().split("T")[0];
    const gapCount = gapMap.get(dateStr) ?? 0;
    const dayOfWeek = date.getDay(); // 0 = Sunday
    const week = Math.floor(i / 7);

    gridData.push({
      date,
      gapCount,
      week,
      day: dayOfWeek === 0 ? 6 : dayOfWeek - 1, // Convert to Monday=0, Sunday=6
    });
  }

  // Calculate month labels
  const monthLabels: Array<{ month: string; week: number }> = [];
  let lastMonth = -1;
  gridData.forEach((cell) => {
    const month = cell.date.getMonth();
    if (month !== lastMonth && cell.day === 0) {
      monthLabels.push({
        month: cell.date.toLocaleDateString("en-US", { month: "short" }),
        week: cell.week,
      });
      lastMonth = month;
    }
  });

  const handleCellClick = (date: Date) => {
    const dateStr = date.toISOString().split("T")[0];
    router.push(`/policy?date=${dateStr}`);
  };

  const handleCellHover = (cell: { date: Date; gapCount: number; week: number; day: number }, event: React.MouseEvent) => {
    setHoveredCell({
      date: cell.date.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" }),
      count: cell.gapCount,
      x: event.clientX,
      y: event.clientY,
    });
  };

  const svgWidth = 53 * cellTotal + 40; // 40px for day labels
  const svgHeight = 7 * cellTotal + 20; // 20px for month labels

  return (
    <div className="glass rounded-2xl p-4">
      <div className="text-sm font-semibold text-white mb-4">Gap Timeline (52 weeks)</div>
      <div className="overflow-x-auto">
        <svg width={svgWidth} height={svgHeight}>
          {/* Month labels */}
          {monthLabels.map((label, i) => (
            <text
              key={i}
              x={40 + label.week * cellTotal}
              y={12}
              fontSize={10}
              fill="#94a3b8"
            >
              {label.month}
            </text>
          ))}

          {/* Day labels */}
          {["M", "W", "F"].map((label, i) => (
            <text
              key={i}
              x={30}
              y={20 + [0, 2, 4][i] * cellTotal + cellSize / 2 + 4}
              fontSize={10}
              fill="#94a3b8"
              textAnchor="end"
            >
              {label}
            </text>
          ))}

          {/* Grid cells */}
          {gridData.map((cell, i) => (
            <rect
              key={i}
              x={40 + cell.week * cellTotal}
              y={20 + cell.day * cellTotal}
              width={cellSize}
              height={cellSize}
              rx={2}
              fill={getGapColor(cell.gapCount, isDark)}
              cursor="pointer"
              onClick={() => handleCellClick(cell.date)}
              onMouseEnter={(e) => handleCellHover(cell, e)}
              onMouseLeave={() => setHoveredCell(null)}
            />
          ))}
        </svg>
      </div>

      {/* Tooltip */}
      {hoveredCell && (
        <div
          className="fixed z-50 px-2 py-1 text-xs text-white bg-slate-900 border border-slate-700 rounded shadow-lg pointer-events-none"
          style={{
            left: hoveredCell.x + 10,
            top: hoveredCell.y + 10,
          }}
        >
          {hoveredCell.count} gaps on {hoveredCell.date}
        </div>
      )}
    </div>
  );
}
