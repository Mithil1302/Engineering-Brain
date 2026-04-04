import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  SimulationNodeDatum,
  SimulationLinkDatum,
} from "d3-force";
import dagre from "@dagrejs/dagre";
import { GraphNode, GraphEdge } from "./types";

/**
 * Position interface for node coordinates
 */
export interface NodePosition {
  x: number;
  y: number;
}

/**
 * Node with position for React Flow
 */
export interface PositionedNode extends GraphNode {
  position: NodePosition;
}

/**
 * D3 simulation node type
 */
interface D3Node extends SimulationNodeDatum {
  id: string;
  [key: string]: unknown;
}

/**
 * D3 simulation link type
 */
interface D3Link extends SimulationLinkDatum<D3Node> {
  source: string | D3Node;
  target: string | D3Node;
}

/**
 * Force Layout using d3-force
 * 
 * Implements Force_Layout with:
 * - linkDistance=150
 * - chargeStrength=-400
 * - 300 synchronous ticks before first render
 * 
 * **Validates: Requirements 2.5, 2.21, 13.2, 13.3, Glossary: Force_Layout**
 */
export function computeForceLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  width = 1000,
  height = 800
): PositionedNode[] {
  if (nodes.length === 0) {
    return [];
  }

  // Create mutable copies for d3-force
  const d3Nodes: D3Node[] = nodes.map((n) => ({
    ...n,
    id: n.id,
  }));

  const d3Links: D3Link[] = edges.map((e) => ({
    source: e.source,
    target: e.target,
  }));

  // Create force simulation
  const simulation = forceSimulation(d3Nodes)
    .force(
      "link",
      forceLink<D3Node, D3Link>(d3Links)
        .id((d) => d.id)
        .distance(150)
    )
    .force("charge", forceManyBody().strength(-400))
    .force("center", forceCenter(width / 2, height / 2));

  // Run 300 synchronous ticks before first render
  simulation.tick(300);
  simulation.stop();

  // Map back to PositionedNode with computed positions
  return nodes.map((node, i) => ({
    ...node,
    position: {
      x: d3Nodes[i].x ?? 0,
      y: d3Nodes[i].y ?? 0,
    },
  }));
}

/**
 * Tree Layout using dagre
 * 
 * Implements Tree_Layout with:
 * - direction="LR" (left-to-right)
 * - roots identified as nodes with no incoming edges
 * - hierarchical arrangement
 * 
 * **Validates: Requirements 2.5, 2.21, 13.2, 13.3, Glossary: Tree_Layout**
 */
export function computeTreeLayout(
  nodes: GraphNode[],
  edges: GraphEdge[]
): PositionedNode[] {
  if (nodes.length === 0) {
    return [];
  }

  // Create a new directed graph
  const g = new dagre.graphlib.Graph();

  // Set graph options for left-to-right layout
  g.setGraph({
    rankdir: "LR",
    nodesep: 80,
    ranksep: 150,
  });

  // Default node dimensions
  g.setDefaultEdgeLabel(() => ({}));

  // Add nodes to the graph
  nodes.forEach((node) => {
    g.setNode(node.id, {
      label: node.label,
      width: 180,
      height: 72,
    });
  });

  // Add edges to the graph
  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target);
  });

  // Apply dagre layout
  dagre.layout(g);

  // Map nodes with computed positions
  return nodes.map((node) => {
    const dagreNode = g.node(node.id);
    return {
      ...node,
      position: {
        x: dagreNode?.x ?? 0,
        y: dagreNode?.y ?? 0,
      },
    };
  });
}

/**
 * Radial Layout
 * 
 * Implements Radial_Layout with:
 * - Equal angles around center point
 * - radius = (nodeCount * 30) clamped to 200-600px
 * 
 * **Validates: Requirements 2.5, 2.21, 13.2, 13.3, Glossary: Radial_Layout**
 */
export function computeRadialLayout(
  nodes: GraphNode[],
  centerX = 500,
  centerY = 400
): PositionedNode[] {
  if (nodes.length === 0) {
    return [];
  }

  // Compute radius: (nodeCount * 30) clamped to 200-600px
  const radius = Math.max(200, Math.min(600, nodes.length * 30));

  // Distribute nodes at equal angles around center
  return nodes.map((node, i) => {
    const angle = (2 * Math.PI * i) / nodes.length;
    return {
      ...node,
      position: {
        x: centerX + radius * Math.cos(angle),
        y: centerY + radius * Math.sin(angle),
      },
    };
  });
}

/**
 * Animate layout transition over 600ms using requestAnimationFrame
 * 
 * Interpolates node positions from current to target over 600ms.
 * Returns a cleanup function to cancel the animation.
 * 
 * **Validates: Requirements 2.21, 13.3**
 */
export function animateLayoutTransition(
  currentNodes: PositionedNode[],
  targetNodes: PositionedNode[],
  onUpdate: (nodes: PositionedNode[]) => void,
  duration = 600
): () => void {
  const startTime = performance.now();
  let animationFrameId: number;

  // Create a map of target positions by node id
  const targetPositions = new Map(
    targetNodes.map((n) => [n.id, n.position])
  );

  // Store initial positions
  const initialPositions = new Map(
    currentNodes.map((n) => [n.id, n.position])
  );

  function animate(currentTime: number) {
    const elapsed = currentTime - startTime;
    const progress = Math.min(elapsed / duration, 1);

    // Ease-in-out interpolation
    const eased =
      progress < 0.5
        ? 2 * progress * progress
        : 1 - Math.pow(-2 * progress + 2, 2) / 2;

    // Interpolate positions
    const interpolatedNodes = currentNodes.map((node) => {
      const initial = initialPositions.get(node.id);
      const target = targetPositions.get(node.id);

      if (!initial || !target) {
        return node;
      }

      return {
        ...node,
        position: {
          x: initial.x + (target.x - initial.x) * eased,
          y: initial.y + (target.y - initial.y) * eased,
        },
      };
    });

    onUpdate(interpolatedNodes);

    if (progress < 1) {
      animationFrameId = requestAnimationFrame(animate);
    }
  }

  animationFrameId = requestAnimationFrame(animate);

  // Return cleanup function
  return () => {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId);
    }
  };
}
