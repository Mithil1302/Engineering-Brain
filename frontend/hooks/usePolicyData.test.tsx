/**
 * Unit tests for usePolicyData hook
 * Task 5.3: Create data fetching hooks for CI/CD Policy Status
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usePolicyData, usePolicyStream } from "./usePolicyData";
import { useSession } from "@/store/session";
import * as api from "@/lib/api";

// Mock the session store
vi.mock("@/store/session", () => ({
  useSession: vi.fn(),
}));

// Mock the API
vi.mock("@/lib/api", () => ({
  policyApi: {
    runs: vi.fn(),
    rulesets: vi.fn(),
  },
  governanceApi: {
    createWaiver: vi.fn(),
    deleteWaiver: vi.fn(),
  },
}));

describe("usePolicyData", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    // Mock session
    vi.mocked(useSession).mockReturnValue({
      activeRepo: "test-repo",
      authHeaders: () => ({ "X-Admin-Token": "test-token" }),
      user: null,
      adminToken: "test-token",
      setUser: vi.fn(),
      setActiveRepo: vi.fn(),
      setAdminToken: vi.fn(),
      logout: vi.fn(),
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  it("should fetch policy runs with infinite scroll", async () => {
    const mockRuns = {
      items: [
        {
          id: 1,
          repo: "test-repo",
          pr_number: 123,
          rule_set: "default",
          summary_status: "pass",
          produced_at: "2025-01-01T00:00:00Z",
        },
      ],
      next_cursor: "cursor-1",
    };

    vi.mocked(api.policyApi.runs).mockResolvedValue(mockRuns);
    vi.mocked(api.policyApi.rulesets).mockResolvedValue(["default", "strict"]);

    const { result } = renderHook(() => usePolicyData(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.policyRunsData?.pages).toHaveLength(1);
    expect(result.current.policyRunsData?.pages[0]).toEqual(mockRuns);
    expect(result.current.hasNextPage).toBe(true);
  });

  it("should fetch policy runs with filter parameters", async () => {
    const mockRuns = {
      items: [],
      next_cursor: null,
    };

    vi.mocked(api.policyApi.runs).mockResolvedValue(mockRuns);
    vi.mocked(api.policyApi.rulesets).mockResolvedValue([]);

    const params = {
      outcome: "block",
      ruleset: "strict",
      from: "2025-01-01",
      to: "2025-01-31",
      search: "PR-123",
    };

    renderHook(() => usePolicyData(params), { wrapper });

    await waitFor(() => {
      expect(api.policyApi.runs).toHaveBeenCalledWith(
        "test-repo",
        expect.objectContaining({
          limit: "25",
          outcome: "block",
          ruleset: "strict",
          from: "2025-01-01",
          to: "2025-01-31",
          search: "PR-123",
        }),
        expect.any(Object)
      );
    });
  });

  it("should fetch rulesets for filter dropdown", async () => {
    const mockRulesets = ["default", "strict", "custom"];

    vi.mocked(api.policyApi.runs).mockResolvedValue({ items: [], next_cursor: null });
    vi.mocked(api.policyApi.rulesets).mockResolvedValue(mockRulesets);

    const { result } = renderHook(() => usePolicyData(), { wrapper });

    await waitFor(() => {
      expect(result.current.rulesets).toEqual(mockRulesets);
    });
  });

  it("should handle waiver request mutation", async () => {
    vi.mocked(api.policyApi.runs).mockResolvedValue({ items: [], next_cursor: null });
    vi.mocked(api.policyApi.rulesets).mockResolvedValue([]);
    vi.mocked(api.governanceApi.createWaiver).mockResolvedValue({ id: 1 });

    const { result } = renderHook(() => usePolicyData(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    const waiverRequest = {
      rule_ids: ["rule-1", "rule-2"],
      justification: "This is a valid justification with more than 50 characters to meet the minimum requirement.",
      expires_at: "2025-02-01T00:00:00Z",
      repo: "test-repo",
      pr_number: 123,
    };

    result.current.requestWaiver(waiverRequest);

    await waitFor(() => {
      expect(api.governanceApi.createWaiver).toHaveBeenCalledWith(
        waiverRequest,
        expect.any(Object)
      );
    });
  });

  it("should handle waiver revoke mutation", async () => {
    vi.mocked(api.policyApi.runs).mockResolvedValue({ items: [], next_cursor: null });
    vi.mocked(api.policyApi.rulesets).mockResolvedValue([]);
    vi.mocked(api.governanceApi.deleteWaiver).mockResolvedValue(undefined);

    const { result } = renderHook(() => usePolicyData(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    result.current.revokeWaiver(1);

    await waitFor(() => {
      expect(api.governanceApi.deleteWaiver).toHaveBeenCalledWith(1, expect.any(Object));
    });
  });

  it("should handle pagination with cursor", async () => {
    const mockPage1 = {
      items: [{ id: 1, repo: "test-repo", rule_set: "default", summary_status: "pass", produced_at: "2025-01-01T00:00:00Z" }],
      next_cursor: "cursor-1",
    };
    const mockPage2 = {
      items: [{ id: 2, repo: "test-repo", rule_set: "default", summary_status: "warn", produced_at: "2025-01-02T00:00:00Z" }],
      next_cursor: null,
    };

    vi.mocked(api.policyApi.runs)
      .mockResolvedValueOnce(mockPage1)
      .mockResolvedValueOnce(mockPage2);
    vi.mocked(api.policyApi.rulesets).mockResolvedValue([]);

    const { result } = renderHook(() => usePolicyData(), { wrapper });

    await waitFor(() => {
      expect(result.current.policyRunsData?.pages).toHaveLength(1);
    });

    result.current.fetchNextPage();

    await waitFor(() => {
      expect(result.current.policyRunsData?.pages).toHaveLength(2);
      expect(result.current.hasNextPage).toBe(false);
    });
  });

  it("should not fetch when activeRepo is not set", () => {
    vi.mocked(useSession).mockReturnValue({
      activeRepo: "",
      authHeaders: () => ({}),
      user: null,
      adminToken: "",
      setUser: vi.fn(),
      setActiveRepo: vi.fn(),
      setAdminToken: vi.fn(),
      logout: vi.fn(),
    });

    renderHook(() => usePolicyData(), { wrapper });

    expect(api.policyApi.runs).not.toHaveBeenCalled();
    expect(api.policyApi.rulesets).not.toHaveBeenCalled();
  });
});

describe("usePolicyStream", () => {
  beforeEach(() => {
    // Mock EventSource as a simple class
    global.EventSource = class MockEventSource {
      addEventListener = vi.fn();
      close = vi.fn();
      onopen: any = null;
      onerror: any = null;
      
      constructor(public url: string) {}
    } as any;

    // Mock session
    vi.mocked(useSession).mockReturnValue({
      activeRepo: "test-repo",
      authHeaders: () => ({ "X-Admin-Token": "test-token" }),
      user: null,
      adminToken: "test-token",
      setUser: vi.fn(),
      setActiveRepo: vi.fn(),
      setAdminToken: vi.fn(),
      logout: vi.fn(),
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should initialize with disconnected status", () => {
    const queryClient = new QueryClient();
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => usePolicyStream(), { wrapper });

    // Initial status should be disconnected
    expect(result.current.connectionStatus).toBe("disconnected");
    expect(result.current.showPausedIndicator).toBe(false);
  });
});
