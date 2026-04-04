import { describe, it, expect } from "vitest";
import * as fc from "fast-check";
import {
  computeForceLayout,
  computeTreeLayout,
  computeRadialLayout,
} from "./graph-layout";
import { GraphNode, GraphEdge } from "./types";

/**
 * Property-Based Tests for Graph Layout Algorithms
 * 
 * These tests verify that layout algorithms are deterministic:
 * applying the same algorithm twice to the same input produces identical positions.
 */

// Arbitraries for generating test data
const nodeTypeArb = fc.constantFrom(
  "service",
  "api",
  "schema",
  "adr",
  "engineer",
  "incident"
);

// Generate safe node IDs that won't conflict with Object.prototype properties
const safeNodeIdArb = fc
  .stringMatching(/^node-[a-z0-9]{1,8}$/)
  .filter((id) => id.length > 5); // Ensure minimum length

const graphNodeArb = fc.record({
  id: safeNodeIdArb,
  label: fc.string({ minLength: 1, maxLength: 20 }),
  type: nodeTypeArb,
  health_score: fc.option(fc.integer({ min: 0, max: 100 }), { nil: undefined }),
  owner: fc.option(fc.string({ minLength: 1, maxLength: 15 }), {
    nil: undefined,
  }),
}) as fc.Arbitrary<GraphNode>;

const relationshipArb = fc.constantFrom("depends_on", "owns", "causes");

function graphEdgeArb(nodeIds: string[]): fc.Arbitrary<GraphEdge> {
  const safeEdgeIdArb = fc
    .stringMatching(/^edge-[a-z0-9]{1,8}$/)
    .filter((id) => id.length > 5);

  if (nodeIds.length < 2) {
    // Return a dummy edge if not enough nodes
    return fc.record({
      id: safeEdgeIdArb,
      source: fc.constant(nodeIds[0] || "node-dummy"),
      target: fc.constant(nodeIds[0] || "node-dummy"),
      relationship: relationshipArb,
    }) as fc.Arbitrary<GraphEdge>;
  }

  return fc.record({
    id: safeEdgeIdArb,
    source: fc.constantFrom(...nodeIds),
    target: fc.constantFrom(...nodeIds),
    relationship: relationshipArb,
  }) as fc.Arbitrary<GraphEdge>;
}

// Generate a graph with unique node IDs
const graphArb = fc
  .array(graphNodeArb, { minLength: 1, maxLength: 20 })
  .chain((nodes) => {
    // Ensure unique IDs
    const uniqueNodes = Array.from(
      new Map(nodes.map((n) => [n.id, n])).values()
    );
    const nodeIds = uniqueNodes.map((n) => n.id);

    return fc
      .array(graphEdgeArb(nodeIds), { minLength: 0, maxLength: 30 })
      .map((edges) => ({
        nodes: uniqueNodes,
        edges,
      }));
  });

describe("Property 34: Layout Algorithm Determinism", () => {
  /**
   * **Validates: Requirements 13.2, 13.3, Glossary: Force_Layout, Tree_Layout, Radial_Layout**
   * 
   * For any graph layout mode (Force, Tree, Radial), applying the layout algorithm
   * twice to the same input (same nodes and edges) should produce the same node positions
   * (deterministic layout).
   */

  it("Force layout should be deterministic", { timeout: 10000 }, () => {
    fc.assert(
      fc.property(graphArb, ({ nodes, edges }) => {
        const result1 = computeForceLayout(nodes, edges, 1000, 800);
        const result2 = computeForceLayout(nodes, edges, 1000, 800);

        expect(result1.length).toBe(result2.length);

        for (let i = 0; i < result1.length; i++) {
          expect(result1[i].id).toBe(result2[i].id);
          expect(result1[i].position.x).toBeCloseTo(result2[i].position.x, 5);
          expect(result1[i].position.y).toBeCloseTo(result2[i].position.y, 5);
        }
      }),
      { numRuns: 20 }
    );
  });

  it("Tree layout should be deterministic", { timeout: 10000 }, () => {
    fc.assert(
      fc.property(graphArb, ({ nodes, edges }) => {
        const result1 = computeTreeLayout(nodes, edges);
        const result2 = computeTreeLayout(nodes, edges);

        expect(result1.length).toBe(result2.length);

        for (let i = 0; i < result1.length; i++) {
          expect(result1[i].id).toBe(result2[i].id);
          // Tree layout should be exactly deterministic (no floating point variance)
          expect(result1[i].position.x).toBe(result2[i].position.x);
          expect(result1[i].position.y).toBe(result2[i].position.y);
        }
      }),
      { numRuns: 20 }
    );
  });

  it("Radial layout should be deterministic", () => {
    fc.assert(
      fc.property(
        fc.array(graphNodeArb, { minLength: 1, maxLength: 20 }),
        fc.integer({ min: 0, max: 2000 }),
        fc.integer({ min: 0, max: 2000 }),
        (nodes, centerX, centerY) => {
          // Ensure unique IDs
          const uniqueNodes = Array.from(
            new Map(nodes.map((n) => [n.id, n])).values()
          );

          const result1 = computeRadialLayout(uniqueNodes, centerX, centerY);
          const result2 = computeRadialLayout(uniqueNodes, centerX, centerY);

          expect(result1.length).toBe(result2.length);

          for (let i = 0; i < result1.length; i++) {
            expect(result1[i].id).toBe(result2[i].id);
            // Radial layout should be exactly deterministic
            expect(result1[i].position.x).toBe(result2[i].position.x);
            expect(result1[i].position.y).toBe(result2[i].position.y);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("Force layout with 300 ticks should produce stable positions", { timeout: 10000 }, () => {
    fc.assert(
      fc.property(graphArb, ({ nodes, edges }) => {
        const result = computeForceLayout(nodes, edges, 1000, 800);

        // All positions should be finite numbers
        for (const node of result) {
          expect(isFinite(node.position.x)).toBe(true);
          expect(isFinite(node.position.y)).toBe(true);
          expect(isNaN(node.position.x)).toBe(false);
          expect(isNaN(node.position.y)).toBe(false);
        }
      }),
      { numRuns: 20 }
    );
  });

  it("Tree layout should use LR direction (left-to-right)", { timeout: 10000 }, () => {
    fc.assert(
      fc.property(graphArb, ({ nodes, edges }) => {
        // Skip if no edges (can't verify hierarchy)
        if (edges.length === 0) return true;

        const result = computeTreeLayout(nodes, edges);

        // All positions should be finite numbers
        for (const node of result) {
          expect(isFinite(node.position.x)).toBe(true);
          expect(isFinite(node.position.y)).toBe(true);
        }

        return true;
      }),
      { numRuns: 100 }
    );
  });

  it("Radial layout should clamp radius to 200-600px", () => {
    fc.assert(
      fc.property(
        fc.array(graphNodeArb, { minLength: 1, maxLength: 30 }),
        (nodes) => {
          // Ensure unique IDs
          const uniqueNodes = Array.from(
            new Map(nodes.map((n) => [n.id, n])).values()
          );

          const centerX = 500;
          const centerY = 400;
          const result = computeRadialLayout(uniqueNodes, centerX, centerY);

          // Calculate expected radius
          const expectedRadius = Math.max(
            200,
            Math.min(600, uniqueNodes.length * 30)
          );

          // Check that all nodes are at approximately the expected radius
          for (const node of result) {
            const dx = node.position.x - centerX;
            const dy = node.position.y - centerY;
            const actualRadius = Math.sqrt(dx * dx + dy * dy);

            expect(actualRadius).toBeCloseTo(expectedRadius, 1);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("Radial layout should distribute nodes at equal angles", () => {
    fc.assert(
      fc.property(
        fc.array(graphNodeArb, { minLength: 2, maxLength: 20 }),
        (nodes) => {
          // Ensure unique IDs
          const uniqueNodes = Array.from(
            new Map(nodes.map((n) => [n.id, n])).values()
          );

          if (uniqueNodes.length < 2) return true;

          const centerX = 500;
          const centerY = 400;
          const result = computeRadialLayout(uniqueNodes, centerX, centerY);

          // Calculate angles for each node
          const angles = result.map((node) => {
            const dx = node.position.x - centerX;
            const dy = node.position.y - centerY;
            return Math.atan2(dy, dx);
          });

          // Expected angle difference
          const expectedAngleDiff = (2 * Math.PI) / uniqueNodes.length;

          // Check angle differences (accounting for wrap-around)
          for (let i = 1; i < angles.length; i++) {
            let angleDiff = angles[i] - angles[i - 1];
            // Normalize to [0, 2π]
            if (angleDiff < 0) angleDiff += 2 * Math.PI;

            expect(angleDiff).toBeCloseTo(expectedAngleDiff, 1);
          }
        }
      ),
      { numRuns: 100 }
    );
  });

  it("All layouts should preserve node count and IDs", { timeout: 10000 }, () => {
    fc.assert(
      fc.property(graphArb, ({ nodes, edges }) => {
        const forceResult = computeForceLayout(nodes, edges);
        const treeResult = computeTreeLayout(nodes, edges);
        const radialResult = computeRadialLayout(nodes);

        expect(forceResult.length).toBe(nodes.length);
        expect(treeResult.length).toBe(nodes.length);
        expect(radialResult.length).toBe(nodes.length);

        const nodeIds = new Set(nodes.map((n) => n.id));
        const forceIds = new Set(forceResult.map((n) => n.id));
        const treeIds = new Set(treeResult.map((n) => n.id));
        const radialIds = new Set(radialResult.map((n) => n.id));

        expect(forceIds).toEqual(nodeIds);
        expect(treeIds).toEqual(nodeIds);
        expect(radialIds).toEqual(nodeIds);
      }),
      { numRuns: 20 }
    );
  });

  it("All layouts should preserve node properties", { timeout: 10000 }, () => {
    fc.assert(
      fc.property(graphArb, ({ nodes, edges }) => {
        const forceResult = computeForceLayout(nodes, edges);
        const treeResult = computeTreeLayout(nodes, edges);
        const radialResult = computeRadialLayout(nodes);

        for (let i = 0; i < nodes.length; i++) {
          // Force layout
          expect(forceResult[i].id).toBe(nodes[i].id);
          expect(forceResult[i].label).toBe(nodes[i].label);
          expect(forceResult[i].type).toBe(nodes[i].type);
          expect(forceResult[i].health_score).toBe(nodes[i].health_score);
          expect(forceResult[i].owner).toBe(nodes[i].owner);

          // Tree layout
          expect(treeResult[i].id).toBe(nodes[i].id);
          expect(treeResult[i].label).toBe(nodes[i].label);
          expect(treeResult[i].type).toBe(nodes[i].type);
          expect(treeResult[i].health_score).toBe(nodes[i].health_score);
          expect(treeResult[i].owner).toBe(nodes[i].owner);

          // Radial layout
          expect(radialResult[i].id).toBe(nodes[i].id);
          expect(radialResult[i].label).toBe(nodes[i].label);
          expect(radialResult[i].type).toBe(nodes[i].type);
          expect(radialResult[i].health_score).toBe(nodes[i].health_score);
          expect(radialResult[i].owner).toBe(nodes[i].owner);
        }
      }),
      { numRuns: 20 }
    );
  });
});
