"use client";
import { 
  ReactFlow, 
  Background, 
  Controls, 
  MiniMap, 
  Node, 
  Edge, 
  useNodesState, 
  useEdgesState, 
  BackgroundVariant,
  useReactFlow,
  NodeMouseHandler,
  OnNodesChange,
  OnEdgesChange
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo, useEffect, useState, useCallback, useRef } from "react";
import { GraphNodeData } from "@/lib/types";
import { getNodeTypeColor } from "@/lib/utils";
import { LayoutMode } from "@/app/(app)/graph/page";
import { 
  ServiceNode, 
  APINode, 
  SchemaNode, 
  ADRNode, 
  EngineerNode, 
  IncidentNode 
} from "./nodes";
import { 
  DependencyEdge, 
  OwnershipEdge, 
  CausalityEdge 
} from "./edges";

// Register custom node types
const NODE_TYPES = {
  service: ServiceNode,
  api: APINode,
  schema: SchemaNode,
  adr: ADRNode,
  engineer: EngineerNode,
  incident: IncidentNode,
} as any;

// Register custom edge types
const EDGE_TYPES = {
  dependency: DependencyEdge,
  ownership: OwnershipEdge,
  causality: CausalityEdge,
};

function applyLayout(
  nodes: Array<{ id: string; type: string; position: { x: number; y: number }; data: GraphNodeData }>,
  layout: LayoutMode
): Array<Node<GraphNodeData>> {
  if (layout === "circular") {
    const r = Math.max(200, nodes.length * 30);
    return nodes.map((n, i) => ({
      ...n,
      position: {
        x: 500 + r * Math.cos((2 * Math.PI * i) / nodes.length),
        y: 400 + r * Math.sin((2 * Math.PI * i) / nodes.length),
      },
    })) as Node<GraphNodeData>[];
  }
  if (layout === "hierarchy") {
    return nodes.map((n, i) => ({
      ...n,
      position: { x: (i % 5) * 220 + 50, y: Math.floor(i / 5) * 160 + 80 },
    })) as Node<GraphNodeData>[];
  }
  // force — keep existing positions
  return nodes as Node<GraphNodeData>[];
}

// Helper to get connected node IDs
function getConnectedNodeIds(nodeId: string, edges: Edge[]): Set<string> {
  const connected = new Set<string>();
  connected.add(nodeId);
  
  edges.forEach((edge) => {
    if (edge.source === nodeId) {
      connected.add(edge.target);
    }
    if (edge.target === nodeId) {
      connected.add(edge.source);
    }
  });
  
  return connected;
}

export function GraphCanvas({
  nodes: inputNodes,
  edges: inputEdges,
  isLoading,
  error,
  layout,
  onNodeClick,
  selectedNodeId,
}: {
  nodes: Array<{ id: string; type: string; position: { x: number; y: number }; data: GraphNodeData }>;
  edges: Array<{ id: string; source: string; target: string; type?: string; style?: Record<string, unknown>; markerEnd?: Record<string, unknown> }>;
  isLoading: boolean;
  error: string | null;
  layout: LayoutMode;
  onNodeClick: (node: GraphNodeData) => void;
  selectedNodeId: string | null;
}) {
  const positioned = useMemo(() => applyLayout(inputNodes, layout), [inputNodes, layout]);
  const [nodes, setNodes, onNodesChange] = useNodesState(positioned);
  const [edges, setEdges, onEdgesChange] = useEdgesState(inputEdges as Edge[]);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const lastClickTimeRef = useRef<number>(0);
  const lastClickNodeRef = useRef<string | null>(null);

  useEffect(() => { 
    setNodes(positioned); 
  }, [positioned, setNodes]);

  useEffect(() => {
    setEdges(inputEdges as Edge[]);
  }, [inputEdges, setEdges]);

  // Apply hover effects
  const nodesWithHover = useMemo(() => {
    if (!hoveredNodeId) return nodes;
    
    const connectedIds = getConnectedNodeIds(hoveredNodeId, edges);
    
    return nodes.map((node) => ({
      ...node,
      style: {
        ...node.style,
        opacity: connectedIds.has(node.id) ? 1 : 0.15,
      },
    }));
  }, [nodes, edges, hoveredNodeId]);

  const edgesWithHover = useMemo(() => {
    if (!hoveredNodeId) return edges;
    
    const connectedIds = getConnectedNodeIds(hoveredNodeId, edges);
    
    return edges.map((edge) => ({
      ...edge,
      style: {
        ...edge.style,
        opacity: connectedIds.has(edge.source) && connectedIds.has(edge.target) ? 1 : 0.1,
      },
    }));
  }, [edges, hoveredNodeId]);

  // Handle node click (single and double-click)
  const handleNodeClick: NodeMouseHandler = useCallback((event, node) => {
    const now = Date.now();
    const timeSinceLastClick = now - lastClickTimeRef.current;
    const isDoubleClick = timeSinceLastClick < 300 && lastClickNodeRef.current === node.id;
    
    lastClickTimeRef.current = now;
    lastClickNodeRef.current = node.id;
    
    if (isDoubleClick) {
      // Double-click: fitView and fetch neighbors
      // TODO: Implement neighbor fetching in parent component
      // For now, just trigger fitView
      const reactFlowInstance = (window as any).__reactFlowInstance;
      if (reactFlowInstance) {
        reactFlowInstance.fitView({
          padding: 0.3,
          duration: 600,
          nodes: [{ id: node.id }],
        });
      }
    } else {
      // Single click: open detail panel
      setTimeout(() => {
        if (Date.now() - lastClickTimeRef.current >= 300) {
          onNodeClick(node.data as GraphNodeData);
        }
      }, 300);
    }
  }, [onNodeClick]);

  // Handle node hover
  const handleNodeMouseEnter: NodeMouseHandler = useCallback((event, node) => {
    setHoveredNodeId(node.id);
  }, []);

  const handleNodeMouseLeave: NodeMouseHandler = useCallback(() => {
    setHoveredNodeId(null);
  }, []);

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="w-10 h-10 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-slate-400">Loading knowledge graph…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center max-w-sm">
          <p className="text-sm font-semibold text-red-400 mb-1">Failed to load graph</p>
          <p className="text-xs text-slate-500">{error}</p>
          <p className="text-xs text-slate-600 mt-2">The knowledge graph for this repo may not have been indexed yet.</p>
        </div>
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-slate-400">No graph data found for this repository.</p>
          <p className="text-xs text-slate-500 mt-1">Trigger an indexing run to populate the knowledge graph.</p>
        </div>
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodesWithHover.map((n) => ({ ...n, selected: n.id === selectedNodeId }))}
      edges={edgesWithHover}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={NODE_TYPES}
      edgeTypes={EDGE_TYPES}
      onNodeClick={handleNodeClick}
      onNodeMouseEnter={handleNodeMouseEnter}
      onNodeMouseLeave={handleNodeMouseLeave}
      fitView
      minZoom={0.2}
      maxZoom={2}
      style={{ background: "#0c1523" }}
    >
      <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#1e293b" />
      <Controls className="!bg-slate-800 !border-slate-700 !rounded-xl" />
      <MiniMap
        style={{ background: "#1e293b", borderRadius: 8 }}
        nodeColor={(n) => getNodeTypeColor((n.data as GraphNodeData)?.type ?? "service")}
      />
    </ReactFlow>
  );
}
