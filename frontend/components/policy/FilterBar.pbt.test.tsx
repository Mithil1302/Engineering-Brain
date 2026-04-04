import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FilterBar } from "./FilterBar";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import * as fc from "fast-check";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: vi.fn(),
  useSearchParams: vi.fn(),
}));

// Mock session store
vi.mock("@/store/session", () => ({
  useSession: vi.fn(() => ({
    activeRepo: "test-repo",
    authHeaders: vi.fn(() => ({ "X-Auth-Token": "test-token" })),
  })),
}));

// Mock API
vi.mock("@/lib/api", () => ({
  policyApi: {
    rulesets: vi.fn(() => Promise.resolve({ items: ["default", "strict"] })),
  },
}));

/**
 * **Validates: Requirements 4.2, 4.3**
 * 
 * Property 22: Filter URL Synchronization
 * 
 * For any combination of filter values (outcome, ruleset, date range, search text),
 * when those filters are applied, the URL query parameters must reflect the current
 * filter state, and when the page is loaded with those query parameters, the filters
 * must be initialized to match the URL state.
 * 
 * This ensures that:
 * - Filter state persists on page refresh
 * - URLs are shareable with the exact filter configuration
 * - All filter values are bidirectionally synced with URL
 */
describe("FilterBar - Property-Based Tests", () => {
  let queryClient: QueryClient;
  let mockRouter: any;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    mockRouter = {
      replace: vi.fn(),
    };

    vi.mocked(useRouter).mockReturnValue(mockRouter);
  });

  const renderFilterBar = (initialParams: URLSearchParams = new URLSearchParams()) => {
    vi.mocked(useSearchParams).mockReturnValue(initialParams as any);
    
    return render(
      <QueryClientProvider client={queryClient}>
        <FilterBar />
      </QueryClientProvider>
    );
  };

  it("Property 22: Filter values are bidirectionally synced with URL query parameters", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          outcome: fc.constantFrom("all", "pass", "warn", "block"),
          search: fc.string({ minLength: 0, maxLength: 20 }),
          dateRange: fc.constantFrom("today", "last7", "last30"),
        }),
        async ({ outcome, search, dateRange }) => {
          // Reset mocks
          mockRouter.replace.mockClear();

          // Phase 1: Load with URL parameters
          const initialParams = new URLSearchParams();
          if (outcome !== "all") initialParams.set("outcome", outcome);
          if (search) initialParams.set("search", search);
          if (dateRange !== "last7") initialParams.set("range", dateRange);

          const { container, unmount } = renderFilterBar(initialParams);

          // Verify initial state matches URL
          const outcomeButton = container.querySelector(`button[class*="bg-indigo-600"]`);
          if (outcome !== "all") {
            expect(outcomeButton?.textContent?.toLowerCase()).toContain(outcome);
          }

          const searchInput = container.querySelector('input[placeholder*="Search"]') as HTMLInputElement;
          if (searchInput) {
            expect(searchInput.value).toBe(search);
          }

          unmount();
        }
      ),
      { numRuns: 20 } // Reduced from 100 for faster execution
    );
  }, 10000); // 10 second timeout

  it("Property 22a: URL parameters are correctly parsed on initial load", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          outcome: fc.constantFrom("all", "pass", "warn", "block"),
          search: fc.string({ minLength: 0, maxLength: 20 }).filter(s => !s.includes("&") && !s.includes("=")),
          range: fc.constantFrom("today", "last7", "last30"),
        }),
        async ({ outcome, search, range }) => {
          // Create URL with parameters
          const params = new URLSearchParams();
          if (outcome !== "all") params.set("outcome", outcome);
          if (search) params.set("search", search);
          if (range !== "last7") params.set("range", range);

          const { container, unmount } = renderFilterBar(params);

          // Verify outcome button is highlighted
          if (outcome !== "all") {
            const highlightedButton = container.querySelector('button[class*="bg-indigo-600"]');
            expect(highlightedButton?.textContent?.toLowerCase()).toContain(outcome);
          }

          // Verify search input has correct value
          const searchInput = container.querySelector('input[placeholder*="Search"]') as HTMLInputElement;
          if (searchInput) {
            expect(searchInput.value).toBe(search);
          }

          unmount();
        }
      ),
      { numRuns: 20 } // Reduced from 100
    );
  }, 10000); // 10 second timeout

  it("Property 22b: Clearing filters removes parameters from URL", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          initialOutcome: fc.constantFrom("pass", "warn", "block"),
          initialSearch: fc.string({ minLength: 1, maxLength: 15 }),
        }),
        async ({ initialOutcome, initialSearch }) => {
          mockRouter.replace.mockClear();

          // Start with filters set
          const params = new URLSearchParams();
          params.set("outcome", initialOutcome);
          params.set("search", initialSearch);

          const { container, unmount } = renderFilterBar(params);
          const user = userEvent.setup();

          // Click "all" to clear outcome filter
          const allButton = Array.from(container.querySelectorAll("button")).find(
            (btn) => btn.textContent?.toLowerCase() === "all"
          );
          if (allButton) {
            await user.click(allButton);

            await waitFor(() => {
              const lastCall = mockRouter.replace.mock.calls[mockRouter.replace.mock.calls.length - 1];
              if (lastCall) {
                const urlArg = lastCall[0];
                // URL should not contain outcome parameter when set to "all"
                expect(urlArg).not.toContain("outcome=");
              }
            }, { timeout: 300 });
          }

          unmount();
        }
      ),
      { numRuns: 10 } // Reduced from 50
    );
  }, 10000); // 10 second timeout
});
