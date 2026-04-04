"use client";
import { useState, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { ReactFlowProvider } from "@xyflow/react";
import { useSession } from "@/store/session";
import { simulationApi } from "@/lib/api";
import { GraphCanvas } from "@/components/graph/GraphCanvas";
import { FilterPanel } from "@/components/graph/FilterPanel";
import { NodeDetailPanel } from "@/components/graph/NodeDetailPanel";
import { GraphNodeData, GraphNodeType } from "@/lib/types";
import { getNodeTypeColor } from "@/lib/utils";
import { GitBranch } from "lucide-react";

export type LayoutMode = "force" | "hierarchy" | "circular";

function buildFlow(data: Record<string, unknown>) {
  const nodes: Array<{ id: string; type: string; position: { x: number; y: number }; data: GraphNodeData }> = [];
  const edges: Array<{ id: string; source: string; target: string; type?: string; style?: Record<string, unknown>; markerEnd?: Record<string, unknown> }> = [];

  const rawNodes = (data?.nodes as Array<Record<string, unknown>>) || [];
  const rawEdges = (data?.edges as Array<Record<string, unknown>>) || [];

  rawNodes.forEach((n, i) => {
    const angle = (i / rawNodes.length) * 2 * Math.PI;
    const radius = Math.min(300, 100 + rawNodes.length * 20);
    nodes.push({
      id: String(n.id),
      type: "customNode",
      position: { x: 400 + radius * Math.cos(angle), y: 300 + radius * Math.sin(angle) },
      data: {
        id: String(n.id),
        label: (n.label as string) || (n.name as string) || String(n.id),
        type: ((n.type as string) || "service") as GraphNodeType,
        healthScore: (n.health_score as number) ?? (n.healthScore as number) ?? 75,
        owner: (n.owner as string) || (n.team as string) || "",
        description: (n.description as string) || "",
        endpoints: (n.endpoints as GraphNodeData["endpoints"]) || [],
        linked_adrs: (n.linked_adrs as string[]) || [],
        last_updated: (n.last_updated as string) || "",
        documented: Boolean(n.documented ?? true),
      },
    });
  });

  rawEdges.forEach((e, i) => {
    const rel = (e.relationship as string) || (e.type as string) || "depends_on";
    const isDashed = rel === "owns" || rel === "causes";
    edges.push({
      id: String(e.id || `e-${i}`),
      source: String(e.source),
      target: String(e.target),
      style: {
        strokeDasharray: isDashed ? "5,5" : undefined,
        stroke: getNodeTypeColor(rel === "depends_on" ? "service" : "api"),
        strokeWidth: 1.5,
        opacity: 0.6,
      },
    });
  });

  return { nodes, edges };
}

export default function GraphPage() {
  const { activeRepo, authHeaders } = useSession();
  const [selectedNode, setSelectedNode] = useState<GraphNodeData | null>(null);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("force");
  const [visibleTypes, setVisibleTypes] = useState<Set<GraphNodeType>>(
    new Set(["service", "api", "schema", "database", "queue", "engineer", "adr", "incident"])
  );
  const [healthFilter, setHealthFilter] = useState(0);
  const [searchQuery, setSearchQuery] = useState("");
  const [undocumentedOnly, setUndocumentedOnly] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ["simulation-graph", activeRepo],
    queryFn: () => simulationApi.graph(activeRepo!, authHeaders()),
    enabled: !!activeRepo,
    retry: 1,
    staleTime: 30000,
  });

  const { nodes: rawNodes, edges } = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    return buildFlow(data as Record<string, unknown>);
  }, [data]);

  const filteredNodes = useMemo(() => {
    return rawNodes
      .filter((n) => visibleTypes.has(n.data.type))
      .filter((n) => (n.data.healthScore ?? 100) >= healthFilter)
      .filter((n) => !undocumentedOnly || !n.data.documented)
      .filter((n) => !searchQuery || n.data.label.toLowerCase().includes(searchQuery.toLowerCase()));
  }, [rawNodes, visibleTypes, healthFilter, undocumentedOnly, searchQuery]);

  const filteredEdges = useMemo(() => {
    const nodeIds = new Set(filteredNodes.map((n) => n.id));
    return edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));
  }, [edges, filteredNodes]);

  const toggleType = useCallback((type: GraphNodeType) => {
    setVisibleTypes((prev) => {
      const next = new Set(prev);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });
  }, []);

  if (!activeRepo) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-center p-8">
        <GitBranch className="w-10 h-10 text-slate-600 mb-4" />
        <h2 className="text-lg font-semibold text-slate-400 mb-2">No repository selected</h2>
        <p className="text-sm text-slate-500">Select a repository in the sidebar to visualize its knowledge graph.</p>
      </div>
    );
  }

  return (
    <div className="h-screen w-screen relative overflow-hidden bg-[#0c1523]">
      <ReactFlowProvider>
        {/* Graph Canvas */}
        <GraphCanvas
          nodes={filteredNodes}
          edges={filteredEdges}
          isLoading={isLoading}
          error={error ? (error as Error).message : null}
          layout={layoutMode}
          onNodeClick={setSelectedNode}
          selectedNodeId={selectedNode?.id ?? null}
        />

        {/* Control panel - absolutely positioned top-right */}
        <div className="absolute top-4 right-4 z-10">
          <FilterPanel
            visibleTypes={visibleTypes}
            onToggleType={toggleType}
            healthFilter={healthFilter}
            onHealthFilter={setHealthFilter}
            searchQuery={searchQuery}
            onSearch={setSearchQuery}
            undocumentedOnly={undocumentedOnly}
            onUndocumentedOnly={setUndocumentedOnly}
          />
        </div>

        {/* Detail panel - absolutely positioned top-right with slide-in animation */}
        <div
          className={`absolute top-0 right-0 h-full z-20 w-[400px] xl:w-[400px] lg:w-[320px] transition-transform duration-300 ${
            selectedNode ? "translate-x-0" : "translate-x-full"
          }`}
        >
          {selectedNode && (
            <NodeDetailPanel
              node={selectedNode}
              repo={activeRepo}
              onClose={() => setSelectedNode(null)}
            />
          )}
        </div>
      </ReactFlowProvider>
    </div>
  );
}
