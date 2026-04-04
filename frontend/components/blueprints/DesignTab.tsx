"use client";

import { useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  BackgroundVariant,
  Node,
  Edge,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "@dagrejs/dagre";
import type { Blueprint } from "@/lib/types";
import { Database, Cloud } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

interface DesignTabProps {
  blueprint: any;
}

// Custom node components
function BlueprintServiceNode({ data }: { data: any }) {
  const [showPopover, setShowPopover] = useState(false);

  return (
    <Popover open={showPopover} onOpenChange={setShowPopover}>
      <PopoverTrigger asChild>
        <div className="w-[180px] h-[72px] rounded-lg bg-slate-800 border-2 border-slate-600 p-2 cursor-pointer hover:border-blue-500 transition-colors">
          <div className="text-sm font-semibold text-white truncate">
            {data.label}
          </div>
          <div className="text-xs text-slate-400 truncate mt-1">{data.role}</div>
          {data.runtime && (
            <div className="absolute bottom-1 left-1 px-2 py-0.5 rounded bg-slate-700 text-xs text-slate-300">
              {data.runtime}
            </div>
          )}
        </div>
      </PopoverTrigger>
      <PopoverContent className="w-80 bg-slate-800 border-slate-700">
        <div className="space-y-3">
          <div>
            <h4 className="text-sm font-semibold text-white mb-1">{data.label}</h4>
            <p className="text-xs text-slate-400">{data.role}</p>
          </div>
          {data.runtime && (
            <div>
              <p className="text-xs text-slate-500 mb-1">Tech Stack</p>
              <div className="flex items-center gap-2">
                <span className="text-xs text-white">{data.language}</span>
                <span className="text-xs text-slate-400">•</span>
                <span className="text-xs text-white">{data.runtime}</span>
              </div>
            </div>
          )}
          {data.interfaces && data.interfaces.length > 0 && (
            <div>
              <p className="text-xs text-slate-500 mb-1">API Surface</p>
              <p className="text-xs text-white">{data.interfaces.length} endpoints</p>
            </div>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function DatabaseNode({ data }: { data: any }) {
  return (
    <div className="w-[100px] h-16 relative">
      {/* Cylinder shape using border-radius */}
      <div className="absolute inset-0 bg-gray-700 rounded-t-[50%] rounded-b-[50%] border-2 border-gray-600 flex items-center justify-center">
        <Database className="w-5 h-5 text-gray-300" />
      </div>
      <div className="absolute bottom-1 left-1/2 -translate-x-1/2 text-xs text-gray-300 whitespace-nowrap">
        {data.label}
      </div>
    </div>
  );
}

function ExternalNode({ data }: { data: any }) {
  return (
    <div
      className="w-[120px] h-16 bg-slate-800/50 border border-slate-600 flex items-center justify-center gap-2 px-3"
      style={{
        clipPath: "polygon(10% 0%, 90% 0%, 100% 50%, 90% 100%, 10% 100%, 0% 50%)",
      }}
    >
      <Cloud className="w-4 h-4 text-slate-400" />
      <span className="text-xs text-slate-300 truncate">{data.label}</span>
    </div>
  );
}

const nodeTypes = {
  service: BlueprintServiceNode,
  database: DatabaseNode,
  external: ExternalNode,
};

// Custom edge component with labels
function CustomEdge({ data, ...props }: any) {
  return (
    <>
      <path
        {...props}
        className={data.className}
        strokeWidth={1.5}
        markerEnd={data.markerEnd}
      />
      {data.label && (
        <text>
          <textPath
            href={`#${props.id}`}
            startOffset="50%"
            textAnchor="middle"
            className="text-[10px] fill-slate-400"
          >
            {data.label}
          </textPath>
        </text>
      )}
    </>
  );
}

const edgeTypes = {
  custom: CustomEdge,
};

function computeDagreLayout(nodes: Node[], edges: Edge[]): Node[] {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: "LR", nodesep: 100, ranksep: 150 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: 180, height: 72 });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  return nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - 90,
        y: nodeWithPosition.y - 36,
      },
    };
  });
}

function DesignTabContent({ blueprint }: DesignTabProps) {
  const { nodes, edges } = useMemo(() => {
    const services = blueprint.services || [];
    
    const initialNodes: Node[] = services.map((service: any, i: number) => ({
      id: service.name,
      type: "service",
      position: { x: 0, y: 0 },
      data: {
        label: service.name,
        role: service.role,
        language: service.language,
        runtime: service.runtime,
        interfaces: service.interfaces,
      },
    }));

    const initialEdges: Edge[] = [];

    // Compute layout
    const layoutedNodes = computeDagreLayout(initialNodes, initialEdges);

    return { nodes: layoutedNodes, edges: initialEdges };
  }, [blueprint]);

  if (nodes.length === 0) {
    return (
      <div className="h-[400px] flex items-center justify-center text-slate-500 text-sm">
        No services in this blueprint
      </div>
    );
  }

  return (
    <div className="h-[600px] rounded-xl overflow-hidden border border-slate-700/50">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        style={{ background: "#0f172a" }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1e293b" />
        <Controls position="bottom-right" />
      </ReactFlow>
    </div>
  );
}

export function DesignTab({ blueprint }: DesignTabProps) {
  return (
    <ReactFlowProvider>
      <DesignTabContent blueprint={blueprint} />
    </ReactFlowProvider>
  );
}
