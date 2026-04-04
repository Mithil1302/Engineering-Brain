"use client";

import { useState } from "react";
import { useBlueprintDetail, useReanalyzeAlignment } from "@/hooks/useBlueprintData";
import { Layers, CheckCircle, AlertTriangle, Loader2 } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { DesignTab } from "./DesignTab";
import { RationaleTab } from "./RationaleTab";
import { ArtifactsTab } from "./ArtifactsTab";
import type { Blueprint } from "@/lib/types";

interface BlueprintDetailPanelProps {
  blueprintId: string | null;
  onClose: () => void;
}

export function BlueprintDetailPanel({
  blueprintId,
  onClose,
}: BlueprintDetailPanelProps) {
  const { data, isLoading } = useBlueprintDetail(blueprintId);
  const blueprint = data as Blueprint | undefined;
  const reanalyzeMutation = useReanalyzeAlignment();
  const [activeTab, setActiveTab] = useState("design");

  if (!blueprintId) {
    return (
      <div className="flex-1 flex items-center justify-center text-center">
        <div>
          <Layers className="w-8 h-8 text-slate-700 mx-auto mb-3" />
          <p className="text-sm text-slate-500">
            Select a blueprint to view its Design, Rationale, and Artifacts
          </p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
      </div>
    );
  }

  if (!blueprint) {
    return (
      <div className="flex-1 flex items-center justify-center text-center">
        <div>
          <Layers className="w-8 h-8 text-slate-700 mx-auto mb-3" />
          <p className="text-sm text-slate-500">Failed to load blueprint details</p>
        </div>
      </div>
    );
  }

  const handleReanalyze = () => {
    reanalyzeMutation.mutate(blueprintId);
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      {/* Alignment banner */}
      {blueprint.aligned ? (
        <div className="bg-green-500 px-6 py-3 flex items-center gap-3">
          <CheckCircle className="w-5 h-5 text-white" />
          <div className="flex-1">
            <p className="text-sm font-semibold text-white">
              Blueprint is aligned with the current codebase
            </p>
            <p className="text-xs text-white/80">
              Last checked {new Date(blueprint.produced_at).toLocaleString()}
            </p>
          </div>
        </div>
      ) : (
        <div className="bg-red-500 px-6 py-3">
          <div className="flex items-start gap-3 mb-2">
            <AlertTriangle className="w-5 h-5 text-white shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-white">
                Blueprint has drifted from the codebase
              </p>
              {blueprint.drift_summary && (
                <p className="text-xs text-white/90 mt-1">{blueprint.drift_summary}</p>
              )}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={handleReanalyze}
              disabled={reanalyzeMutation.isPending}
              className="bg-white/10 border-white/20 text-white hover:bg-white/20"
            >
              {reanalyzeMutation.isPending ? (
                <>
                  <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                  Analyzing...
                </>
              ) : (
                "Re-analyze alignment"
              )}
            </Button>
          </div>
          {blueprint.drift_summary && (
            <div className="flex flex-wrap gap-2 mt-2">
              {blueprint.drift_summary.split(",").map((drift: string, i: number) => (
                <span
                  key={i}
                  className="text-xs bg-white/10 text-white px-2 py-1 rounded"
                >
                  {drift.trim()}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col min-h-0">
          <div className="px-6 py-3 border-b border-slate-700/50">
            <TabsList className="bg-slate-800/50">
              <TabsTrigger value="design">Design</TabsTrigger>
              <TabsTrigger value="rationale">Rationale</TabsTrigger>
              <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
            </TabsList>
          </div>

          <div className="flex-1 overflow-y-auto">
            <TabsContent value="design" className="p-6 m-0">
              <DesignTab blueprint={blueprint} />
            </TabsContent>
            <TabsContent value="rationale" className="p-6 m-0">
              <RationaleTab blueprint={blueprint} />
            </TabsContent>
            <TabsContent value="artifacts" className="p-6 m-0">
              <ArtifactsTab blueprintId={blueprintId} />
            </TabsContent>
          </div>
        </Tabs>
      </div>
    </div>
  );
}
