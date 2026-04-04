import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WaiverManagement } from "./WaiverManagement";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { policyApi, governanceApi } from "@/lib/api";
import { Waiver } from "@/lib/types";

// Mock dependencies
vi.mock("@/store/session");
vi.mock("@/lib/api");

const mockAuthHeaders = vi.fn(() => ({ "X-Admin-Token": "test-token" }));

const mockActiveWaiver: Waiver = {
  id: 1,
  repo: "test-repo",
  pr_number: 123,
  rule_set: "default",
  rule_ids: ["rule-1", "rule-2"],
  justification: "This is a test justification for the waiver request",
  requested_by: "John Doe",
  requested_role: "engineer",
  decided_by: "Jane Smith",
  decided_role: "admin",
  status: "approved",
  expires_at: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString(), // 10 days from now
  created_at: new Date().toISOString(),
};

const mockExpiredWaiver: Waiver = {
  id: 2,
  repo: "test-repo",
  pr_number: 456,
  rule_set: "default",
  rule_ids: ["rule-3"],
  justification: "This waiver has expired",
  requested_by: "Bob Johnson",
  requested_role: "engineer",
  decided_by: "Alice Brown",
  decided_role: "admin",
  status: "expired",
  expires_at: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(), // 5 days ago
  created_at: new Date(Date.now() - 35 * 24 * 60 * 60 * 1000).toISOString(),
};

const mockPendingWaiver: Waiver = {
  id: 3,
  repo: "test-repo",
  pr_number: 789,
  rule_set: "default",
  rule_ids: ["rule-4", "rule-5", "rule-6"],
  justification: "Pending approval waiver",
  requested_by: "Charlie Wilson",
  requested_role: "engineer",
  status: "pending",
  expires_at: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString(), // 5 days from now (within 7 days warning)
  created_at: new Date().toISOString(),
};

describe("WaiverManagement", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });

    vi.mocked(useSession).mockReturnValue({
      authHeaders: mockAuthHeaders,
      user: null,
      activeRepo: "test-repo",
      adminToken: "test-token",
      setUser: vi.fn(),
      setActiveRepo: vi.fn(),
      setAdminToken: vi.fn(),
      logout: vi.fn(),
    });

    vi.clearAllMocks();
  });

  const renderComponent = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <WaiverManagement />
      </QueryClientProvider>
    );
  };

  describe("Basic rendering", () => {
    it("renders tabs for Active and Expired waivers", async () => {
      vi.mocked(policyApi.listWaivers).mockResolvedValue({ items: [] });

      renderComponent();

      await waitFor(() => {
        expect(screen.getByRole("tab", { name: /active/i })).toBeInTheDocument();
        expect(screen.getByRole("tab", { name: /expired/i })).toBeInTheDocument();
      });
    });

    it("shows empty state when no active waivers exist", async () => {
      vi.mocked(policyApi.listWaivers).mockResolvedValue({ items: [] });

      renderComponent();

      await waitFor(() => {
        expect(screen.getByText(/no active waivers/i)).toBeInTheDocument();
      });
    });

    it("shows empty state when no repository is selected", () => {
      vi.mocked(useSession).mockReturnValue({
        authHeaders: mockAuthHeaders,
        user: null,
        activeRepo: null,
        adminToken: "test-token",
        setUser: vi.fn(),
        setActiveRepo: vi.fn(),
        setAdminToken: vi.fn(),
        logout: vi.fn(),
      });

      renderComponent();

      expect(screen.getByText(/no repository selected/i)).toBeInTheDocument();
    });
  });

  describe("Active waivers tab", () => {
    it("displays active waivers in a table", async () => {
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockActiveWaiver, mockPendingWaiver],
      });

      renderComponent();

      await waitFor(() => {
        expect(screen.getByText("John Doe")).toBeInTheDocument();
        expect(screen.getByText("Jane Smith")).toBeInTheDocument();
        expect(screen.getByText("Charlie Wilson")).toBeInTheDocument();
      });
    });

    it("displays pending approval badge for waivers without decided_by", async () => {
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockPendingWaiver],
      });

      renderComponent();

      await waitFor(() => {
        expect(screen.getByText(/pending approval/i)).toBeInTheDocument();
      });
    });

    it("displays rules bypassed with truncation for long lists", async () => {
      const longRuleWaiver: Waiver = {
        ...mockActiveWaiver,
        rule_ids: [
          "very-long-rule-name-1",
          "very-long-rule-name-2",
          "very-long-rule-name-3",
          "very-long-rule-name-4",
        ],
      };

      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [longRuleWaiver],
      });

      renderComponent();

      await waitFor(() => {
        const rulesText = screen.getByText(/very-long-rule-name/);
        expect(rulesText.textContent).toContain("...");
      });
    });

    it("displays expiry date in red when within 7 days", async () => {
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockPendingWaiver],
      });

      renderComponent();

      await waitFor(() => {
        // Find the expiry cell with red text
        const expiryCell = screen.getByText("Charlie Wilson")
          .closest("tr")
          ?.querySelector("td:nth-child(5) span");
        
        expect(expiryCell).toHaveClass("text-red-500");
        expect(expiryCell).toHaveClass("font-semibold");
      });
    });

    it("displays revoke button for active waivers", async () => {
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockActiveWaiver],
      });

      renderComponent();

      await waitFor(() => {
        const revokeButton = screen.getByLabelText(/revoke waiver 1/i);
        expect(revokeButton).toBeInTheDocument();
      });
    });

    it("displays status badge with correct color", async () => {
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockActiveWaiver, mockPendingWaiver],
      });

      renderComponent();

      await waitFor(() => {
        const approvedBadge = screen.getByText("approved");
        expect(approvedBadge).toHaveClass("text-emerald-400");

        const pendingBadge = screen.getByText("pending");
        expect(pendingBadge).toHaveClass("text-amber-400");
      });
    });
  });

  describe("Expired waivers tab", () => {
    it("switches to expired tab when clicked", async () => {
      const user = userEvent.setup();
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockExpiredWaiver],
      });

      renderComponent();

      // Wait for loading to complete
      await waitFor(() => {
        expect(screen.getByRole("tab", { name: /active/i })).toBeInTheDocument();
      });

      const expiredTab = screen.getByRole("tab", { name: /expired/i });
      await user.click(expiredTab);

      await waitFor(() => {
        expect(screen.getByText("Bob Johnson")).toBeInTheDocument();
      });
    });

    it("does not display revoke button for expired waivers", async () => {
      const user = userEvent.setup();
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockExpiredWaiver],
      });

      renderComponent();

      // Wait for loading to complete
      await waitFor(() => {
        expect(screen.getByRole("tab", { name: /active/i })).toBeInTheDocument();
      });

      const expiredTab = screen.getByRole("tab", { name: /expired/i });
      await user.click(expiredTab);

      await waitFor(() => {
        expect(screen.queryByLabelText(/revoke waiver/i)).not.toBeInTheDocument();
      });
    });

    it("shows empty state when no expired waivers exist", async () => {
      const user = userEvent.setup();
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockActiveWaiver],
      });

      renderComponent();

      // Wait for loading to complete
      await waitFor(() => {
        expect(screen.getByRole("tab", { name: /active/i })).toBeInTheDocument();
      });

      const expiredTab = screen.getByRole("tab", { name: /expired/i });
      await user.click(expiredTab);

      await waitFor(() => {
        expect(screen.getByText(/no expired waivers/i)).toBeInTheDocument();
      });
    });
  });

  describe("Revoke waiver functionality", () => {
    it("calls DELETE API when revoke button is clicked", async () => {
      const user = userEvent.setup();
      const mockDeleteWaiver = vi.fn().mockResolvedValue({});
      vi.mocked(governanceApi.deleteWaiver).mockImplementation(mockDeleteWaiver);
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockActiveWaiver],
      });

      // Mock window.confirm
      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

      renderComponent();

      await waitFor(() => {
        expect(screen.getByText("John Doe")).toBeInTheDocument();
      });

      const revokeButton = screen.getByLabelText(/revoke waiver 1/i);
      await user.click(revokeButton);

      expect(confirmSpy).toHaveBeenCalled();
      expect(mockDeleteWaiver).toHaveBeenCalledWith(1, expect.any(Object));

      confirmSpy.mockRestore();
    });

    it("does not call DELETE API when user cancels confirmation", async () => {
      const user = userEvent.setup();
      const mockDeleteWaiver = vi.fn().mockResolvedValue({});
      vi.mocked(governanceApi.deleteWaiver).mockImplementation(mockDeleteWaiver);
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockActiveWaiver],
      });

      // Mock window.confirm to return false
      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);

      renderComponent();

      await waitFor(() => {
        expect(screen.getByText("John Doe")).toBeInTheDocument();
      });

      const revokeButton = screen.getByLabelText(/revoke waiver 1/i);
      await user.click(revokeButton);

      expect(confirmSpy).toHaveBeenCalled();
      expect(mockDeleteWaiver).not.toHaveBeenCalled();

      confirmSpy.mockRestore();
    });

    it("performs optimistic update when revoking waiver", async () => {
      const user = userEvent.setup();
      const mockDeleteWaiver = vi
        .fn()
        .mockImplementation(() => new Promise((resolve) => setTimeout(resolve, 100)));
      vi.mocked(governanceApi.deleteWaiver).mockImplementation(mockDeleteWaiver);
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockActiveWaiver, mockPendingWaiver],
      });

      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

      renderComponent();

      await waitFor(() => {
        expect(screen.getByText("John Doe")).toBeInTheDocument();
        expect(screen.getByText("Charlie Wilson")).toBeInTheDocument();
      });

      const revokeButton = screen.getByLabelText(/revoke waiver 1/i);
      await user.click(revokeButton);

      // Waiver should be removed immediately (optimistic update)
      await waitFor(() => {
        expect(screen.queryByText("John Doe")).not.toBeInTheDocument();
      });

      // Charlie Wilson should still be visible
      expect(screen.getByText("Charlie Wilson")).toBeInTheDocument();

      confirmSpy.mockRestore();
    });

    it("rolls back optimistic update on error", async () => {
      const user = userEvent.setup();
      const mockDeleteWaiver = vi.fn().mockRejectedValue(new Error("Delete failed"));
      vi.mocked(governanceApi.deleteWaiver).mockImplementation(mockDeleteWaiver);
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockActiveWaiver],
      });

      const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);

      renderComponent();

      await waitFor(() => {
        expect(screen.getByText("John Doe")).toBeInTheDocument();
      });

      const revokeButton = screen.getByLabelText(/revoke waiver 1/i);
      await user.click(revokeButton);

      // Wait for error and rollback
      await waitFor(() => {
        // Waiver should be restored after rollback
        expect(screen.getByText("John Doe")).toBeInTheDocument();
      });

      confirmSpy.mockRestore();
    });
  });

  describe("Loading state", () => {
    it("displays skeleton loading while fetching waivers", () => {
      vi.mocked(policyApi.listWaivers).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      renderComponent();

      const skeletons = screen.getAllByRole("generic").filter((el) =>
        el.className.includes("skeleton")
      );
      expect(skeletons.length).toBeGreaterThan(0);
    });
  });

  describe("Avatar display", () => {
    it("displays user initials in avatar", async () => {
      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [mockActiveWaiver],
      });

      renderComponent();

      await waitFor(() => {
        // John Doe -> JD
        const avatars = screen.getAllByText("JD");
        expect(avatars.length).toBeGreaterThan(0);
      });
    });

    it("displays single initial for single-word names", async () => {
      const singleNameWaiver: Waiver = {
        ...mockActiveWaiver,
        requested_by: "Admin",
        decided_by: "Supervisor",
      };

      vi.mocked(policyApi.listWaivers).mockResolvedValue({
        items: [singleNameWaiver],
      });

      renderComponent();

      await waitFor(() => {
        expect(screen.getByText("A")).toBeInTheDocument();
        expect(screen.getByText("S")).toBeInTheDocument();
      });
    });
  });
});
