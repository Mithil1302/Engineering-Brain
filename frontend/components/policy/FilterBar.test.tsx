import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FilterBar } from "./FilterBar";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";

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
    rulesets: vi.fn(() => Promise.resolve({ items: ["default", "strict", "custom"] })),
  },
}));

describe("FilterBar", () => {
  let queryClient: QueryClient;
  let mockRouter: any;
  let mockSearchParams: any;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    mockRouter = {
      replace: vi.fn(),
    };

    mockSearchParams = new URLSearchParams();

    vi.mocked(useRouter).mockReturnValue(mockRouter);
    vi.mocked(useSearchParams).mockReturnValue(mockSearchParams as any);
  });

  const renderFilterBar = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <FilterBar />
      </QueryClientProvider>
    );
  };

  it("renders all outcome filter options", () => {
    renderFilterBar();
    
    expect(screen.getByRole("button", { name: /all/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /pass/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /warn/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /block/i })).toBeInTheDocument();
  });

  it("renders date range buttons", () => {
    renderFilterBar();
    
    expect(screen.getByRole("button", { name: /today/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /last 7 days/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /last 30 days/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /custom/i })).toBeInTheDocument();
  });

  it("renders search input", () => {
    renderFilterBar();
    
    const searchInput = screen.getByPlaceholderText(/search by pr number or branch/i);
    expect(searchInput).toBeInTheDocument();
  });

  it("highlights selected outcome filter", async () => {
    renderFilterBar();
    const user = userEvent.setup();
    
    const passButton = screen.getByRole("button", { name: /^pass$/i });
    await user.click(passButton);
    
    expect(passButton).toHaveClass("bg-indigo-600");
  });

  it("updates URL when outcome filter changes", async () => {
    renderFilterBar();
    const user = userEvent.setup();
    
    const warnButton = screen.getByRole("button", { name: /^warn$/i });
    await user.click(warnButton);
    
    await waitFor(() => {
      expect(mockRouter.replace).toHaveBeenCalledWith(
        expect.stringContaining("outcome=warn"),
        expect.any(Object)
      );
    });
  });

  it("debounces search input", async () => {
    renderFilterBar();
    const user = userEvent.setup();
    
    const searchInput = screen.getByPlaceholderText(/search by pr number or branch/i);
    
    // Clear any initial calls
    mockRouter.replace.mockClear();
    
    await user.type(searchInput, "PR-123");
    
    // Should update after debounce delay
    await waitFor(() => {
      expect(mockRouter.replace).toHaveBeenCalledWith(
        expect.stringContaining("search=PR-123"),
        expect.any(Object)
      );
    }, { timeout: 500 });
  });

  it("shows clear button when search has text", async () => {
    renderFilterBar();
    const user = userEvent.setup();
    
    const searchInput = screen.getByPlaceholderText(/search by pr number or branch/i);
    await user.type(searchInput, "test");
    
    const clearButton = screen.getByLabelText(/clear search/i);
    expect(clearButton).toBeInTheDocument();
  });

  it("clears search when clear button is clicked", async () => {
    renderFilterBar();
    const user = userEvent.setup();
    
    const searchInput = screen.getByPlaceholderText(/search by pr number or branch/i) as HTMLInputElement;
    await user.type(searchInput, "test");
    
    const clearButton = screen.getByLabelText(/clear search/i);
    await user.click(clearButton);
    
    expect(searchInput.value).toBe("");
  });

  it("opens custom date picker when Custom button is clicked", async () => {
    renderFilterBar();
    const user = userEvent.setup();
    
    const customButton = screen.getByRole("button", { name: /custom/i });
    await user.click(customButton);
    
    // Check for date picker labels using getAllByText
    await waitFor(() => {
      const fromLabels = screen.getAllByText(/^from$/i);
      const toLabels = screen.getAllByText(/^to$/i);
      expect(fromLabels.length).toBeGreaterThan(0);
      expect(toLabels.length).toBeGreaterThan(0);
    });
  });

  it("reads initial filter values from URL", () => {
    mockSearchParams = new URLSearchParams("outcome=block&search=test-pr");
    vi.mocked(useSearchParams).mockReturnValue(mockSearchParams as any);
    
    renderFilterBar();
    
    const blockButton = screen.getByRole("button", { name: /^block$/i });
    expect(blockButton).toHaveClass("bg-indigo-600");
    
    const searchInput = screen.getByPlaceholderText(/search by pr number or branch/i) as HTMLInputElement;
    expect(searchInput.value).toBe("test-pr");
  });

  it("displays colored dots for each outcome option", () => {
    renderFilterBar();
    
    const allButton = screen.getByRole("button", { name: /^all$/i });
    const passButton = screen.getByRole("button", { name: /^pass$/i });
    const warnButton = screen.getByRole("button", { name: /^warn$/i });
    const blockButton = screen.getByRole("button", { name: /^block$/i });
    
    // Check that each button contains a colored dot span
    expect(allButton.querySelector(".bg-slate-400")).toBeInTheDocument();
    expect(passButton.querySelector(".bg-emerald-400")).toBeInTheDocument();
    expect(warnButton.querySelector(".bg-amber-400")).toBeInTheDocument();
    expect(blockButton.querySelector(".bg-red-400")).toBeInTheDocument();
  });
});
