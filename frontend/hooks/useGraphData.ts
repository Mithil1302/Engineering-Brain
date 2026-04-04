/**
 * Custom hook for fetching and managing Knowledge Graph data
 * Implements parallel node/edge fetching and neighbor expansion
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { graphApi } from "@/lib/api";
import type { GraphNode, GraphEdge } from "@/lib/types";

interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface NeighborExpansionResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/**
 * Fetches graph nodes and edges in parallel
 * Cache with staleTime 30000ms (30 seconds)
 * Initial graph render with up to 200 nodes must complete within 2 seconds
 */
export function useGraphData() {
  const { activeRepo, authHeaders } = useSession();

  const query = useQuery<GraphData>({
    queryKey: ["graph-data", activeRepo],
    queryFn: async () => {
      // Fetch nodes and edges in parallel using Promise.all
      const [nodes, edges] = await Promise.all([
        graphApi.nodes(activeRepo, authHeaders()),
        graphApi.edges(activeRepo, authHeaders()),
      ]);

      return {
        nodes: nodes as GraphNode[],
        edges: edges as GraphEdge[],
      };
    },
    enabled: !!activeRepo,
    staleTime: 30000, // 30 seconds
  });

  return query;
}

/**
 * Mutation for expanding node neighbors on double-click
 * Fetches neighbors at depth=1 and returns new nodes/edges to add to graph
 */
export function useNeighborExpansion() {
  const { authHeaders } = useSession();
  const queryClient = useQueryClient();

  const mutation = useMutation<NeighborExpansionResult, Error, string>({
    mutationFn: async (nodeId: string) => {
      // POST to GET /graph/neighbors/{node_id}?depth=1
      const result = await graphApi.neighbors(nodeId, 1, authHeaders());
      return result as NeighborExpansionResult;
    },
    onSuccess: (data, nodeId) => {
      // Optionally update the cache with new nodes/edges
      // This is handled in the component to control animation timing
      console.log(`Expanded neighbors for node ${nodeId}:`, data);
    },
  });

  return mutation;
}
