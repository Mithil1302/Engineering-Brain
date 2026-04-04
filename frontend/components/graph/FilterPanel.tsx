"use client";
import { GraphNodeType } from "@/lib/types";
import { getNodeTypeColor } from "@/lib/utils";
import { Search, Eye, EyeOff, Filter } from "lucide-react";

const ALL_TYPES: GraphNodeType[] = ["service", "api", "schema", "database", "queue", "engineer", "adr", "incident"];

export function FilterPanel({
  visibleTypes,
  onToggleType,
  healthFilter,
  onHealthFilter,
  searchQuery,
  onSearch,
  undocumentedOnly,
  onUndocumentedOnly,
}: {
  visibleTypes: Set<GraphNodeType>;
  onToggleType: (t: GraphNodeType) => void;
  healthFilter: number;
  onHealthFilter: (v: number) => void;
  searchQuery: string;
  onSearch: (v: string) => void;
  undocumentedOnly: boolean;
  onUndocumentedOnly: (v: boolean) => void;
}) {
  return (
    <div className="w-64 glass rounded-2xl shadow-2xl border border-slate-700/50 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Filter className="w-3.5 h-3.5 text-indigo-400" />
        <span className="text-xs font-semibold text-white">Graph Filters</span>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-500" />
        <input
          value={searchQuery}
          onChange={(e) => onSearch(e.target.value)}
          placeholder="Search nodes…"
          className="w-full pl-7 pr-3 py-1.5 bg-slate-800/80 border border-slate-700/50 rounded-lg text-xs text-white placeholder-slate-500 outline-none focus:border-indigo-500/50"
        />
      </div>

      {/* Undocumented quick filter */}
      <button
        onClick={() => onUndocumentedOnly(!undocumentedOnly)}
        className={`w-full text-xs px-3 py-2 rounded-lg border transition-all flex items-center gap-2 ${
          undocumentedOnly
            ? "bg-red-500/20 border-red-500/40 text-red-300"
            : "bg-slate-800/50 border-slate-700/50 text-slate-400 hover:text-white"
        }`}
      >
        {undocumentedOnly ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
        Show undocumented only
      </button>

      {/* Node type toggles */}
      <div>
        <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2">Node Types</div>
        <div className="grid grid-cols-2 gap-1.5">
          {ALL_TYPES.map((type) => {
            const active = visibleTypes.has(type);
            const color = getNodeTypeColor(type);
            return (
              <button
                key={type}
                onClick={() => onToggleType(type)}
                className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg border text-[10px] font-medium transition-all capitalize ${
                  active ? "border-opacity-40" : "opacity-40 border-slate-700/50"
                }`}
                style={{
                  borderColor: active ? color + "66" : undefined,
                  backgroundColor: active ? color + "15" : undefined,
                  color: active ? color : "#64748b",
                }}
              >
                <div className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: color }} />
                {type}
              </button>
            );
          })}
        </div>
      </div>

      {/* Health score filter */}
      <div>
        <div className="flex justify-between mb-1.5">
          <span className="text-[10px] text-slate-500 uppercase tracking-wider">Min Health Score</span>
          <span className="text-[10px] font-mono text-slate-300">{healthFilter}</span>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          value={healthFilter}
          onChange={(e) => onHealthFilter(Number(e.target.value))}
          aria-label="Minimum health score filter"
          className="w-full h-1 bg-slate-700 rounded-full appearance-none cursor-pointer accent-indigo-500"
        />
        <div className="flex justify-between mt-1">
          <span className="text-[9px] text-slate-600">All</span>
          <span className="text-[9px] text-slate-600">Healthy only</span>
        </div>
      </div>
    </div>
  );
}
