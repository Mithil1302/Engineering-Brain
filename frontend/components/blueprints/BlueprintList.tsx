"use client";

import { useBlueprintList } from "@/hooks/useBlueprintData";
import { formatRelativeTime } from "@/lib/utils";
import { Grid2X2, Layers } from "lucide-react";
import type { Blueprint } from "@/lib/types";

interface BlueprintListProps {
  filters: {
    pattern: string | null;
    from: string | null;
    to: string | null;
    aligned: boolean | null;
  };
  selectedBlueprintId: string | null;
  onSelectBlueprint: (id: string) => void;
}

const PATTERN_COLORS: Record<string, string> = {
  Microservices: "bg-blue-500",
  Monolith: "bg-gray-500",
  CQRS: "bg-purple-500",
  BFF: "bg-green-500",
  Saga: "bg-amber-500",
  "Event-driven": "bg-orange-500",
};

function BlueprintCardSkeleton() {
  return (
    <div className="p-3 rounded-xl border border-slate-700/40 space-y-2">
      <div className="h-4 bg-slate-800 rounded animate-pulse" />
      <div className="h-3 bg-slate-800 rounded animate-pulse w-3/4" />
    </div>
  );
}

export function BlueprintList({
  filters,
  selectedBlueprintId,
  onSelectBlueprint,
}: BlueprintListProps) {
  const { data, isLoading, error } = useBlueprintList(filters);
  const blueprints = (data as Blueprint[]) || [];

  if (isLoading) {
    return (
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <BlueprintCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center p-6 text-center">
        <div>
          <Layers className="w-8 h-8 text-slate-700 mx-auto mb-2" />
          <p className="text-xs text-slate-500">Failed to load blueprints</p>
        </div>
      </div>
    );
  }

  if (blueprints.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-6 text-center">
        <div>
          <Layers className="w-8 h-8 text-slate-700 mx-auto mb-2" />
          <p className="text-xs text-slate-500">No blueprints found</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-2 space-y-2">
      {blueprints.map((blueprint) => {
        const isSelected = selectedBlueprintId === blueprint.plan_id;
        const patternColor = blueprint.pattern
          ? PATTERN_COLORS[blueprint.pattern] || "bg-gray-500"
          : "bg-gray-500";

        return (
          <button
            key={blueprint.plan_id}
            onClick={() => onSelectBlueprint(blueprint.plan_id)}
            className={`w-full text-left p-3 rounded-xl border transition-all ${
              isSelected
                ? "border-l-[3px] border-blue-500 bg-blue-600/10"
                : "border-slate-700/40 hover:bg-slate-800/40 hover:border-slate-600/40"
            }`}
          >
            {/* Requirement text */}
            <div className="text-xs font-medium text-white mb-2 line-clamp-2">
              {blueprint.requirement?.requirement_text || "Untitled blueprint"}
            </div>

            {/* Pattern badge and service count */}
            <div className="flex items-center gap-2 mb-2">
              {blueprint.pattern && (
                <span
                  className={`${patternColor} text-white text-[10px] px-2 py-0.5 rounded font-medium`}
                >
                  {blueprint.pattern}
                </span>
              )}
              {blueprint.services && (
                <span className="text-[10px] text-slate-400 flex items-center gap-1">
                  <Grid2X2 className="w-3 h-3" />
                  {blueprint.services.length} services
                </span>
              )}
            </div>

            {/* Date and alignment */}
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-slate-500">
                {formatRelativeTime(blueprint.produced_at)}
              </span>
              <div className="flex items-center gap-1">
                <div
                  className={`w-2 h-2 rounded-full ${
                    blueprint.aligned ? "bg-green-500" : "bg-red-500"
                  }`}
                />
                <span
                  className={`text-[10px] ${
                    blueprint.aligned ? "text-green-500" : "text-red-500"
                  }`}
                >
                  {blueprint.aligned ? "Aligned" : "Drifted"}
                </span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
