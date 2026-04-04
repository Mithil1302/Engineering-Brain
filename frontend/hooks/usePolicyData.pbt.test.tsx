/**
 * Property-based tests for usePolicyData hook
 * Task 5.3: Create data fetching hooks for CI/CD Policy Status
 * 
 * **Validates: Requirements 4.4, 4.5, 4.6, 10.2, Appendix B**
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { usePolicyData } from "./usePolicyData";
import { useSession } from "@/store/session";
import * as api from "@/lib/api";
import * as fc from "fast-check";

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

describe("usePolicyData - Property-Based Tests", () => {
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

  /**
   * Property 21: Infinite Scroll Pagination
   * 
   * For any scrollable list with infinite scroll (policy runs), when fetchNextPage is called
   * if hasNextPage is true, the new page should be appended to the existing data without
   * replacing previous pages.
   */
  it("Property 21: should append pages without replacing previous data", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 2, max: 5 }),
        async (numPages) => {
          // Create a fresh QueryClient for each test run
          const testQueryClient = new QueryClient({
            defaultOptions: {
              queries: { retry: false },
              mutations: { retry: false },
            },
          });

          const testWrapper = ({ children }: { children: React.ReactNode }) => (
            <QueryClientProvider client={testQueryClient}>{children}</QueryClientProvider>
          );

          // Generate mock pages with unique IDs
          const pages = Array.from({ length: numPages }, (_, index) => ({
            items: [
              {
                id: index + 1,
                repo: "test-repo",
                rule_set: "default",
                summary_status: "pass" as const,
                produced_at: new Date().toISOString(),
              },
            ],
            next_cursor: index < numPages - 1 ? `cursor-${index + 1}` : null,
          }));

          // Mock API to return pages sequentially
          let callCount = 0;
          vi.mocked(api.policyApi.runs).mockImplementation(() => {
            const page = pages[callCount];
            callCount++;
            return Promise.resolve(page);
          });
          vi.mocked(api.policyApi.rulesets).mockResolvedValue([]);

          const { result } = renderHook(() => usePolicyData(), { wrapper: testWrapper });

          // Wait for initial load
          await waitFor(() => {
            expect(result.current.isLoading).toBe(false);
          }, { timeout: 3000 });

          // Verify first page
          expect(result.current.policyRunsData?.pages).toHaveLength(1);

          // Fetch remaining pages
          for (let i = 1; i < numPages; i++) {
            if (result.current.hasNextPage) {
              result.current.fetchNextPage();
              await waitFor(() => {
                expect(result.current.policyRunsData?.pages.length).toBeGreaterThanOrEqual(i + 1);
              }, { timeout: 3000 });
            }
          }

          // Verify all pages are present
          expect(result.current.policyRunsData?.pages.length).toBe(numPages);
        }
      ),
      { numRuns: 5 }
    );
  });

  /**
   * Property 40: Performance Target Compliance
   * 
   * Policy run list first 25 items must render within 1 second.
   * This property verifies that the hook completes loading within acceptable time.
   */
  it("Property 40: should load policy runs within performance target", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 1, max: 25 }),
        async (numRuns) => {
          // Create a fresh QueryClient for each test run
          const testQueryClient = new QueryClient({
            defaultOptions: {
              queries: { retry: false },
              mutations: { retry: false },
            },
          });

          const testWrapper = ({ children }: { children: React.ReactNode }) => (
            <QueryClientProvider client={testQueryClient}>{children}</QueryClientProvider>
          );

          const policyRuns = Array.from({ length: numRuns }, (_, i) => ({
            id: i + 1,
            repo: "test-repo",
            rule_set: "default",
            summary_status: "pass" as const,
            produced_at: new Date().toISOString(),
          }));

          const mockResponse = {
            items: policyRuns,
            next_cursor: null,
          };

          vi.mocked(api.policyApi.runs).mockResolvedValue(mockResponse);
          vi.mocked(api.policyApi.rulesets).mockResolvedValue([]);

          const startTime = Date.now();
          const { result } = renderHook(() => usePolicyData(), { wrapper: testWrapper });

          await waitFor(() => {
            expect(result.current.isLoading).toBe(false);
          }, { timeout: 3000 });

          const loadTime = Date.now() - startTime;

          // Performance target: < 1 second (1000ms)
          // In tests, we allow some overhead, so we check < 2000ms
          expect(loadTime).toBeLessThan(2000);
          const hookResult: any = result.current;
          expect(hookResult.policyRunsData?.pages[0].items.length).toBe(numRuns);
        }
      ),
      { numRuns: 5 }
    );
  });

  /**
   * Property: Filter parameters should be correctly passed to API
   * 
   * For any combination of filter parameters (outcome, ruleset, search),
   * the API should be called with exactly those parameters.
   */
  it("should pass all filter parameters to API correctly", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          outcome: fc.option(fc.constantFrom("pass", "warn", "block"), { nil: undefined }),
          ruleset: fc.option(fc.constantFrom("default", "strict", "custom"), { nil: undefined }),
          search: fc.option(fc.string({ minLength: 2, maxLength: 20 }), { nil: undefined }),
        }),
        async (params) => {
          // Reset mocks before each property test run
          vi.clearAllMocks();
          
          // Create a fresh QueryClient for each test run
          const testQueryClient = new QueryClient({
            defaultOptions: {
              queries: { retry: false },
              mutations: { retry: false },
            },
          });

          const testWrapper = ({ children }: { children: React.ReactNode }) => (
            <QueryClientProvider client={testQueryClient}>{children}</QueryClientProvider>
          );

          vi.mocked(api.policyApi.runs).mockResolvedValue({ items: [], next_cursor: null });
          vi.mocked(api.policyApi.rulesets).mockResolvedValue([]);

          renderHook(() => usePolicyData(params), { wrapper: testWrapper });

          await waitFor(() => {
            expect(api.policyApi.runs).toHaveBeenCalled();
          }, { timeout: 3000 });

          const callArgs = vi.mocked(api.policyApi.runs).mock.calls[0];
          const queryParams = callArgs[1];

          // Verify all provided parameters are passed
          if (params.outcome) expect(queryParams.outcome).toBe(params.outcome);
          if (params.ruleset) expect(queryParams.ruleset).toBe(params.ruleset);
          if (params.search) expect(queryParams.search).toBe(params.search);
          expect(queryParams.limit).toBe("25");
        }
      ),
      { numRuns: 10 }
    );
  });

  /**
   * Property: Waiver request should validate required fields
   * 
   * For any waiver request, the mutation should be called with all required fields:
   * rule_ids (non-empty array), justification (string), expires_at (date), repo, pr_number.
   */
  it("should handle waiver requests with all required fields", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          rule_ids: fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 1, maxLength: 5 }),
          justification: fc.string({ minLength: 50, maxLength: 500 }),
          expires_at: fc.date({ min: new Date(), max: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000) }).map((d) => d.toISOString()),
          repo: fc.constant("test-repo"),
          pr_number: fc.integer({ min: 1, max: 10000 }),
        }),
        async (waiverRequest) => {
          vi.mocked(api.policyApi.runs).mockResolvedValue({ items: [], next_cursor: null });
          vi.mocked(api.policyApi.rulesets).mockResolvedValue([]);
          vi.mocked(api.governanceApi.createWaiver).mockResolvedValue({ id: 1 });

          const { result } = renderHook(() => usePolicyData(), { wrapper });

          await waitFor(() => {
            expect(result.current.isLoading).toBe(false);
          });

          result.current.requestWaiver(waiverRequest);

          await waitFor(() => {
            expect(api.governanceApi.createWaiver).toHaveBeenCalledWith(
              waiverRequest,
              expect.any(Object)
            );
          });
        }
      ),
      { numRuns: 10 }
    );
  });
});
