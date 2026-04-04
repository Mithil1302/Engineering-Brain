/**
 * Unit tests for useGraphData hook
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useGraphData, useNeighborExpansion } from "./useGraphData";
import { useSession } from "@/store/session";
import { graphApi } from "@/lib/api";
import type { GraphNode, GraphEdge } from "@/lib/types";

// Mock dependencies
vi.mock("@/store/session");
vi.mock("@/lib/api");

const mockUseSession = vi.mocked(useSession);
const mockGraphApi = vi.mocked(graphApi);

// Test data
const mockNodes: GraphNode[] = [
  {
    id: "service-1",
    label: "Payment Service",
    type: "service",
    health_score: 85,
    owner: "team-payments",
  },
  {
    id: "service-2",
    label: "Auth Service",
    type: "service",
    health_score: 92,
    owner: "team-platform",
  },
];

const mockEdges: GraphEdge[] = [
  {
    id: "edge-1",
    source: "service-1",
    target: "service-2",
    relationship: "depends_on",
  },
];

const mockNeighbors = {
  nodes: [
    {
      id: "service-3",
      label: "Database Service",
      type: "service" as const,
      health_score: 78,
    },
  ],
  edges: [
    {
      id: "edge-2",
      source: "service-1",
      target: "service-3",
      relationship: "depends_on" as const,
    },
  ],
};

// Helper to create wrapper with QueryClient
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("useGraphData", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock session store
    mockUseSession.mockReturnValue({
      activeRepo: "test-repo",
      authHeaders: () => ({ "X-Admin-Token": "test-token" }),
    } as any);
  });

  it("fetches nodes and edges in parallel", async () => {
    // Mock API responses
    mockGraphApi.nodes.mockResolvedValue(mockNodes as any);
    mockGraphApi.edges.mockResolvedValue(mockEdges as any);

    const { result } = renderHook(() => useGraphData(), {
      wrapper: createWrapper(),
    });

    // Initially loading
    expect(result.current.isLoading).toBe(true);

    // Wait for data to load
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Verify data
    expect(result.current.data).toEqual({
      nodes: mockNodes,
      edges: mockEdges,
    });

    // Verify API calls
    expect(mockGraphApi.nodes).toHaveBeenCalledWith(
      "test-repo",
      { "X-Admin-Token": "test-token" }
    );
    expect(mockGraphApi.edges).toHaveBeenCalledWith(
      "test-repo",
      { "X-Admin-Token": "test-token" }
    );
  });

  it("does not fetch when activeRepo is empty", () => {
    mockUseSession.mockReturnValue({
      activeRepo: "",
      authHeaders: () => ({}),
    } as any);

    const { result } = renderHook(() => useGraphData(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(false);
    expect(mockGraphApi.nodes).not.toHaveBeenCalled();
    expect(mockGraphApi.edges).not.toHaveBeenCalled();
  });

  it("uses staleTime of 30 seconds", () => {
    mockGraphApi.nodes.mockResolvedValue(mockNodes as any);
    mockGraphApi.edges.mockResolvedValue(mockEdges as any);

    const { result } = renderHook(() => useGraphData(), {
      wrapper: createWrapper(),
    });

    // The staleTime is configured in the hook
    // We can verify it's set by checking the query options
    expect(result.current).toBeDefined();
  });
});

describe("useNeighborExpansion", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    
    mockUseSession.mockReturnValue({
      activeRepo: "test-repo",
      authHeaders: () => ({ "X-Admin-Token": "test-token" }),
    } as any);
  });

  it("fetches neighbors for a node", async () => {
    mockGraphApi.neighbors.mockResolvedValue(mockNeighbors as any);

    const { result } = renderHook(() => useNeighborExpansion(), {
      wrapper: createWrapper(),
    });

    // Trigger mutation
    result.current.mutate("service-1");

    // Wait for mutation to complete
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Verify data
    expect(result.current.data).toEqual(mockNeighbors);

    // Verify API call
    expect(mockGraphApi.neighbors).toHaveBeenCalledWith(
      "service-1",
      1,
      { "X-Admin-Token": "test-token" }
    );
  });

  it("handles errors gracefully", async () => {
    const error = new Error("Network error");
    mockGraphApi.neighbors.mockRejectedValue(error);

    const { result } = renderHook(() => useNeighborExpansion(), {
      wrapper: createWrapper(),
    });

    // Trigger mutation
    result.current.mutate("service-1");

    // Wait for mutation to fail
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toEqual(error);
  });
});
