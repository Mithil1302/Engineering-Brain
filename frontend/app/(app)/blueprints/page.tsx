"use client";

import { useState } from "react";
import { useSession } from "@/store/session";
import { Layers } from "lucide-react";
import { FilterBar } from "@/components/blueprints/FilterBar";
import { BlueprintList } from "@/components/blueprints/BlueprintList";
import { BlueprintDetailPanel } from "@/components/blueprints/BlueprintDetailPanel";

export default function BlueprintsPage() {
  const { activeRepo } = useSession();
  const [selectedBlueprintId, setSelectedBlueprintId] = useState<string | null>(null);
  const [filters, setFilters] = useState({
    pattern: null as string | null,
    from: null as string | null,
    to: null as string | null,
    aligned: null as boolean | null,
  });

  if (!activeRepo) {
    return (
      <div className="h-full flex items-center justify-center text-center p-8">
        <div>
          <Layers className="w-10 h-10 text-slate-600 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-slate-400 mb-2">No repository selected</h2>
          <p className="text-sm text-slate-500">Select a repository to view its architecture blueprints.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col min-h-0 overflow-hidden min-w-[1280px]">
      {/* Header above both panels */}
      <div className="p-4 border-b border-slate-700/50 shrink-0">
        <h1 className="text-lg font-bold text-white">Architecture Blueprints</h1>
      </div>

      {/* Main content */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* Left: Blueprint list panel */}
        <div className="w-[340px] lg:w-[280px] shrink-0 border-r border-slate-700/50 flex flex-col min-h-0">
          <FilterBar filters={filters} onFiltersChange={setFilters} />
          <BlueprintList
            filters={filters}
            selectedBlueprintId={selectedBlueprintId}
            onSelectBlueprint={setSelectedBlueprintId}
          />
        </div>

        {/* Right: Detail panel */}
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          <BlueprintDetailPanel
            blueprintId={selectedBlueprintId}
            onClose={() => setSelectedBlueprintId(null)}
          />
        </div>
      </div>
    </div>
  );
}
