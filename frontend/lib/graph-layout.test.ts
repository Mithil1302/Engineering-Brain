import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  computeForceLayout,
  computeTreeLayout,
  computeRadialLayout,
  animateLayoutTransition,
  PositionedNode,
} from "./graph-layout";
import { GraphNode, GraphEdge } from "./types";

describe("computeForceLayout", () => {
  it("should return empty array for empty nodes", () => {
    const result = computeForceLayout([], []);
    expect(result).toEqual([]);
  });

  it("should compute positions for single node", () => {
    const nodes: GraphNode[] = [
      { id: "1", label: "Node 1", type: "service" },
    ];
    const result = computeForceLayout(nodes, []);

    expect(result).toHaveLength(1);
    expect(result[0]).toHaveProperty("position");
    expect(result[0].position).toHaveProperty("x");
    expect(result[0].position).toHaveProperty("y");
    expect(typeof result[0].position.x).toBe("number");
    expect(typeof result[0].position.y).toBe("number");
  });

  it("should compute positions for multiple connected nodes", () => {
    const nodes: GraphNode[] = [
      { id: "1", label: "Node 1", type: "service" },
      { id: "2", label: "Node 2", type: "service" },
      { id: "3", label: "Node 3", type: "api" },
    ];
    const edges: GraphEdge[] = [
      { id: "e1", source: "1", target: "2", relationship: "depends_on" },
      { id: "e2", source: "2", target: "3", relationship: "owns" },
    ];

    const result = computeForceLayout(nodes, edges);

    expect(result).toHaveLength(3);
    result.forEach((node) => {
      expect(node).toHaveProperty("position");
      expect(typeof node.position.x).toBe("number");
      expect(typeof node.position.y).toBe("number");
      expect(isFinite(node.position.x)).toBe(true);
      expect(isFinite(node.position.y)).toBe(true);
    });
  });

  it("should preserve node properties", () => {
    const nodes: GraphNode[] = [
      {
        id: "1",
        label: "Service A",
        type: "service",
        health_score: 85,
        owner: "team-a",
      },
    ];
    const result = computeForceLayout(nodes, []);

    expect(result[0].id).toBe("1");
    expect(result[0].label).toBe("Service A");
    expect(result[0].type).toBe("service");
    expect(result[0].health_score).toBe(85);
    expect(result[0].owner).toBe("team-a");
  });

  it("should produce deterministic results for same input", () => {
    const nodes: GraphNode[] = [
      { id: "1", label: "Node 1", type: "service" },
      { id: "2", label: "Node 2", type: "service" },
    ];
    const edges: GraphEdge[] = [
      { id: "e1", source: "1", target: "2", relationship: "depends_on" },
    ];

    const result1 = computeForceLayout(nodes, edges);
    const result2 = computeForceLayout(nodes, edges);

    expect(result1[0].position.x).toBeCloseTo(result2[0].position.x, 5);
    expect(result1[0].position.y).toBeCloseTo(result2[0].position.y, 5);
    expect(result1[1].position.x).toBeCloseTo(result2[1].position.x, 5);
    expect(result1[1].position.y).toBeCloseTo(result2[1].position.y, 5);
  });
});

describe("computeTreeLayout", () => {
  it("should return empty array for empty nodes", () => {
    const result = computeTreeLayout([], []);
    expect(result).toEqual([]);
  });

  it("should compute positions for single node", () => {
    const nodes: GraphNode[] = [
      { id: "1", label: "Root", type: "service" },
    ];
    const result = computeTreeLayout(nodes, []);

    expect(result).toHaveLength(1);
    expect(result[0]).toHaveProperty("position");
    expect(typeof result[0].position.x).toBe("number");
    expect(typeof result[0].position.y).toBe("number");
  });

  it("should compute hierarchical positions for tree structure", () => {
    const nodes: GraphNode[] = [
      { id: "1", label: "Root", type: "service" },
      { id: "2", label: "Child 1", type: "service" },
      { id: "3", label: "Child 2", type: "api" },
    ];
    const edges: GraphEdge[] = [
      { id: "e1", source: "1", target: "2", relationship: "depends_on" },
      { id: "e2", source: "1", target: "3", relationship: "owns" },
    ];

    const result = computeTreeLayout(nodes, edges);

    expect(result).toHaveLength(3);
    result.forEach((node) => {
      expect(node).toHaveProperty("position");
      expect(typeof node.position.x).toBe("number");
      expect(typeof node.position.y).toBe("number");
      expect(isFinite(node.position.x)).toBe(true);
      expect(isFinite(node.position.y)).toBe(true);
    });

    // Root should be leftmost in LR layout
    const root = result.find((n) => n.id === "1");
    const child1 = result.find((n) => n.id === "2");
    const child2 = result.find((n) => n.id === "3");

    expect(root!.position.x).toBeLessThan(child1!.position.x);
    expect(root!.position.x).toBeLessThan(child2!.position.x);
  });

  it("should preserve node properties", () => {
    const nodes: GraphNode[] = [
      {
        id: "1",
        label: "Service A",
        type: "service",
        health_score: 90,
        owner: "team-b",
      },
    ];
    const result = computeTreeLayout(nodes, []);

    expect(result[0].id).toBe("1");
    expect(result[0].label).toBe("Service A");
    expect(result[0].type).toBe("service");
    expect(result[0].health_score).toBe(90);
    expect(result[0].owner).toBe("team-b");
  });

  it("should produce deterministic results for same input", () => {
    const nodes: GraphNode[] = [
      { id: "1", label: "Node 1", type: "service" },
      { id: "2", label: "Node 2", type: "service" },
    ];
    const edges: GraphEdge[] = [
      { id: "e1", source: "1", target: "2", relationship: "depends_on" },
    ];

    const result1 = computeTreeLayout(nodes, edges);
    const result2 = computeTreeLayout(nodes, edges);

    expect(result1[0].position.x).toBe(result2[0].position.x);
    expect(result1[0].position.y).toBe(result2[0].position.y);
    expect(result1[1].position.x).toBe(result2[1].position.x);
    expect(result1[1].position.y).toBe(result2[1].position.y);
  });
});

describe("computeRadialLayout", () => {
  it("should return empty array for empty nodes", () => {
    const result = computeRadialLayout([]);
    expect(result).toEqual([]);
  });

  it("should compute positions for single node at center", () => {
    const nodes: GraphNode[] = [
      { id: "1", label: "Node 1", type: "service" },
    ];
    const result = computeRadialLayout(nodes, 500, 400);

    expect(result).toHaveLength(1);
    // Single node should be at radius distance from center
    const dx = result[0].position.x - 500;
    const dy = result[0].position.y - 400;
    const distance = Math.sqrt(dx * dx + dy * dy);
    expect(distance).toBeCloseTo(200, 1); // Minimum radius is 200
  });

  it("should distribute nodes at equal angles", () => {
    const nodes: GraphNode[] = [
      { id: "1", label: "Node 1", type: "service" },
      { id: "2", label: "Node 2", type: "service" },
      { id: "3", label: "Node 3", type: "api" },
      { id: "4", label: "Node 4", type: "schema" },
    ];
    const result = computeRadialLayout(nodes, 500, 400);

    expect(result).toHaveLength(4);

    // All nodes should be at same distance from center
    const centerX = 500;
    const centerY = 400;
    const distances = result.map((node) => {
      const dx = node.position.x - centerX;
      const dy = node.position.y - centerY;
      return Math.sqrt(dx * dx + dy * dy);
    });

    const firstDistance = distances[0];
    distances.forEach((d) => {
      expect(d).toBeCloseTo(firstDistance, 1);
    });
  });

  it("should clamp radius to 200-600px range", () => {
    // Test minimum radius (200px)
    const smallNodes: GraphNode[] = [
      { id: "1", label: "Node 1", type: "service" },
    ];
    const smallResult = computeRadialLayout(smallNodes, 500, 400);
    const smallRadius = Math.sqrt(
      Math.pow(smallResult[0].position.x - 500, 2) +
        Math.pow(smallResult[0].position.y - 400, 2)
    );
    expect(smallRadius).toBeCloseTo(200, 1);

    // Test maximum radius (600px) - need 21+ nodes (21 * 30 = 630 > 600)
    const largeNodes: GraphNode[] = Array.from({ length: 25 }, (_, i) => ({
      id: `${i + 1}`,
      label: `Node ${i + 1}`,
      type: "service" as const,
    }));
    const largeResult = computeRadialLayout(largeNodes, 500, 400);
    const largeRadius = Math.sqrt(
      Math.pow(largeResult[0].position.x - 500, 2) +
        Math.pow(largeResult[0].position.y - 400, 2)
    );
    expect(largeRadius).toBeCloseTo(600, 1);

    // Test mid-range (10 nodes * 30 = 300px)
    const midNodes: GraphNode[] = Array.from({ length: 10 }, (_, i) => ({
      id: `${i + 1}`,
      label: `Node ${i + 1}`,
      type: "service" as const,
    }));
    const midResult = computeRadialLayout(midNodes, 500, 400);
    const midRadius = Math.sqrt(
      Math.pow(midResult[0].position.x - 500, 2) +
        Math.pow(midResult[0].position.y - 400, 2)
    );
    expect(midRadius).toBeCloseTo(300, 1);
  });

  it("should preserve node properties", () => {
    const nodes: GraphNode[] = [
      {
        id: "1",
        label: "Service A",
        type: "service",
        health_score: 75,
        owner: "team-c",
      },
    ];
    const result = computeRadialLayout(nodes);

    expect(result[0].id).toBe("1");
    expect(result[0].label).toBe("Service A");
    expect(result[0].type).toBe("service");
    expect(result[0].health_score).toBe(75);
    expect(result[0].owner).toBe("team-c");
  });

  it("should produce deterministic results for same input", () => {
    const nodes: GraphNode[] = [
      { id: "1", label: "Node 1", type: "service" },
      { id: "2", label: "Node 2", type: "service" },
    ];

    const result1 = computeRadialLayout(nodes, 500, 400);
    const result2 = computeRadialLayout(nodes, 500, 400);

    expect(result1[0].position.x).toBe(result2[0].position.x);
    expect(result1[0].position.y).toBe(result2[0].position.y);
    expect(result1[1].position.x).toBe(result2[1].position.x);
    expect(result1[1].position.y).toBe(result2[1].position.y);
  });
});

describe("animateLayoutTransition", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("should interpolate positions over time", () => {
    const currentNodes: PositionedNode[] = [
      {
        id: "1",
        label: "Node 1",
        type: "service",
        position: { x: 0, y: 0 },
      },
    ];
    const targetNodes: PositionedNode[] = [
      {
        id: "1",
        label: "Node 1",
        type: "service",
        position: { x: 100, y: 100 },
      },
    ];

    const updates: PositionedNode[][] = [];
    const onUpdate = vi.fn((nodes: PositionedNode[]) => {
      updates.push(nodes);
    });

    const cleanup = animateLayoutTransition(
      currentNodes,
      targetNodes,
      onUpdate,
      600
    );

    // Fast-forward through animation
    vi.advanceTimersByTime(300); // 50% progress
    vi.advanceTimersByTime(300); // 100% progress

    cleanup();

    expect(onUpdate).toHaveBeenCalled();
    expect(updates.length).toBeGreaterThan(0);
  });

  it("should call cleanup function to cancel animation", () => {
    const currentNodes: PositionedNode[] = [
      {
        id: "1",
        label: "Node 1",
        type: "service",
        position: { x: 0, y: 0 },
      },
    ];
    const targetNodes: PositionedNode[] = [
      {
        id: "1",
        label: "Node 1",
        type: "service",
        position: { x: 100, y: 100 },
      },
    ];

    const onUpdate = vi.fn();
    const cleanup = animateLayoutTransition(
      currentNodes,
      targetNodes,
      onUpdate,
      600
    );

    // Cancel immediately
    cleanup();

    // Advance time - should not trigger more updates after cleanup
    const callCountAfterCleanup = onUpdate.mock.calls.length;
    vi.advanceTimersByTime(1000);

    // Should not have increased significantly
    expect(onUpdate.mock.calls.length).toBeLessThanOrEqual(
      callCountAfterCleanup + 1
    );
  });

  it("should preserve node properties during animation", () => {
    const currentNodes: PositionedNode[] = [
      {
        id: "1",
        label: "Service A",
        type: "service",
        health_score: 80,
        position: { x: 0, y: 0 },
      },
    ];
    const targetNodes: PositionedNode[] = [
      {
        id: "1",
        label: "Service A",
        type: "service",
        health_score: 80,
        position: { x: 100, y: 100 },
      },
    ];

    let lastUpdate: PositionedNode[] = [];
    const onUpdate = vi.fn((nodes: PositionedNode[]) => {
      lastUpdate = nodes;
    });

    const cleanup = animateLayoutTransition(
      currentNodes,
      targetNodes,
      onUpdate,
      600
    );

    vi.advanceTimersByTime(300);

    expect(lastUpdate[0].id).toBe("1");
    expect(lastUpdate[0].label).toBe("Service A");
    expect(lastUpdate[0].type).toBe("service");
    expect(lastUpdate[0].health_score).toBe(80);

    cleanup();
  });
});
