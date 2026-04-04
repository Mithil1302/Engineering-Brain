import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { WaiverModal } from "./WaiverModal";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { governanceApi } from "@/lib/api";

// Mock dependencies
vi.mock("@/store/session");
vi.mock("@/lib/api");

const mockAuthHeaders = vi.fn(() => ({ "X-Admin-Token": "test-token" }));

describe("WaiverModal", () => {
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

  const renderModal = (props: Partial<React.ComponentProps<typeof WaiverModal>> = {}) => {
    const defaultProps = {
      open: true,
      onOpenChange: vi.fn(),
      ruleIds: ["rule-1"],
      repo: "test-repo",
      prNumber: 123,
    };

    return render(
      <QueryClientProvider client={queryClient}>
        <WaiverModal {...defaultProps} {...props} />
      </QueryClientProvider>
    );
  };

  describe("Basic rendering", () => {
    it("renders modal with title and description", () => {
      renderModal();

      expect(screen.getByText("Request Waiver")).toBeInTheDocument();
      expect(
        screen.getByText(/Request a temporary waiver to bypass policy rules/i)
      ).toBeInTheDocument();
    });

    it("renders rule being waived field", () => {
      renderModal({ ruleIds: ["rule-1"] });

      expect(screen.getByText(/Rule being waived/i)).toBeInTheDocument();
      expect(screen.getByText("rule-1")).toBeInTheDocument();
    });

    it("displays multiple rules count when multiple rules selected", () => {
      renderModal({ ruleIds: ["rule-1", "rule-2", "rule-3"] });

      expect(screen.getByText("3 rules selected")).toBeInTheDocument();
    });

    it("renders justification textarea", () => {
      renderModal();

      const textarea = screen.getByPlaceholderText(/Explain why this waiver is needed/i);
      expect(textarea).toBeInTheDocument();
    });

    it("renders expiry date picker with default 7 days from today", () => {
      renderModal();

      // The date button shows the formatted date, not "select date"
      const dateButton = screen.getByRole("button", { name: /april/i });
      expect(dateButton).toBeInTheDocument();
    });

    it("renders submit and cancel buttons", () => {
      renderModal();

      expect(screen.getByRole("button", { name: /cancel/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /submit request/i })).toBeInTheDocument();
    });
  });

  describe("Character counter", () => {
    it("displays character count in red when below 50 characters", async () => {
      const user = userEvent.setup();
      renderModal();

      const textarea = screen.getByPlaceholderText(/Explain why this waiver is needed/i);
      await user.type(textarea, "Short text");

      const counter = screen.getByText(/10\/50 minimum/i);
      expect(counter).toHaveClass("text-red-500");
    });

    it("displays character count in gray when at or above 50 characters", { timeout: 10000 }, async () => {
      const user = userEvent.setup();
      renderModal();

      const textarea = screen.getByPlaceholderText(/Explain why this waiver is needed/i);
      const longText = "a".repeat(50);
      await user.type(textarea, longText);

      const counter = screen.getByText(/50\/50 minimum/i);
      expect(counter).toHaveClass("text-slate-400");
    });
  });

  describe("Client-side validation", () => {
    it("shows validation error when justification is less than 50 characters", async () => {
      const user = userEvent.setup();
      renderModal();

      const textarea = screen.getByPlaceholderText(/Explain why this waiver is needed/i);
      await user.type(textarea, "Too short");

      const submitButton = screen.getByRole("button", { name: /submit request/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(
          screen.getByText(/Justification must be at least 50 characters/i)
        ).toBeInTheDocument();
      });
    });

    it("shows validation error when rule_ids is empty", async () => {
      const user = userEvent.setup();
      renderModal({ ruleIds: [] });

      const submitButton = screen.getByRole("button", { name: /submit request/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(
          screen.getByText(/At least one rule must be selected/i)
        ).toBeInTheDocument();
      });
    });

    it("does not submit when validation fails", async () => {
      const user = userEvent.setup();
      const mockCreateWaiver = vi.fn();
      vi.mocked(governanceApi.createWaiver).mockImplementation(mockCreateWaiver);

      renderModal();

      const submitButton = screen.getByRole("button", { name: /submit request/i });
      await user.click(submitButton);

      expect(mockCreateWaiver).not.toHaveBeenCalled();
    });
  });

  describe("Form submission", () => {
    it("submits waiver request with valid data", { timeout: 10000 }, async () => {
      const user = userEvent.setup();
      const mockOnOpenChange = vi.fn();
      const mockCreateWaiver = vi.fn().mockResolvedValue({ id: 1 });
      vi.mocked(governanceApi.createWaiver).mockImplementation(mockCreateWaiver);

      renderModal({ onOpenChange: mockOnOpenChange });

      const textarea = screen.getByPlaceholderText(/Explain why this waiver is needed/i);
      const longText = "This is a valid justification that is longer than fifty characters to pass validation.";
      await user.type(textarea, longText);

      const submitButton = screen.getByRole("button", { name: /submit request/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockCreateWaiver).toHaveBeenCalledWith(
          expect.objectContaining({
            rule_ids: ["rule-1"],
            justification: longText,
            repo: "test-repo",
            pr_number: 123,
          }),
          expect.any(Object)
        );
      });
    });

    it("shows loading state during submission", { timeout: 10000 }, async () => {
      const user = userEvent.setup();
      const mockCreateWaiver = vi.fn().mockImplementation(
        () => new Promise((resolve) => setTimeout(resolve, 1000))
      );
      vi.mocked(governanceApi.createWaiver).mockImplementation(mockCreateWaiver);

      renderModal();

      const textarea = screen.getByPlaceholderText(/Explain why this waiver is needed/i);
      const longText = "This is a valid justification that is longer than fifty characters to pass validation.";
      await user.type(textarea, longText);

      const submitButton = screen.getByRole("button", { name: /submit request/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(submitButton).toBeDisabled();
        expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
      });
    });

    it("closes modal on successful submission", { timeout: 10000 }, async () => {
      const user = userEvent.setup();
      const mockOnOpenChange = vi.fn();
      const mockCreateWaiver = vi.fn().mockResolvedValue({ id: 1 });
      vi.mocked(governanceApi.createWaiver).mockImplementation(mockCreateWaiver);

      renderModal({ onOpenChange: mockOnOpenChange });

      const textarea = screen.getByPlaceholderText(/Explain why this waiver is needed/i);
      const longText = "This is a valid justification that is longer than fifty characters to pass validation.";
      await user.type(textarea, longText);

      const submitButton = screen.getByRole("button", { name: /submit request/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(mockOnOpenChange).toHaveBeenCalledWith(false);
      });
    });

    it("displays API error message on submission failure", { timeout: 10000 }, async () => {
      const user = userEvent.setup();
      const mockCreateWaiver = vi.fn().mockRejectedValue(
        new Error("Failed to create waiver")
      );
      vi.mocked(governanceApi.createWaiver).mockImplementation(mockCreateWaiver);

      renderModal();

      const textarea = screen.getByPlaceholderText(/Explain why this waiver is needed/i);
      const longText = "This is a valid justification that is longer than fifty characters to pass validation.";
      await user.type(textarea, longText);

      const submitButton = screen.getByRole("button", { name: /submit request/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Failed to create waiver/i)).toBeInTheDocument();
      });
    });

    it("invalidates policy run query on success", { timeout: 10000 }, async () => {
      const user = userEvent.setup();
      const mockCreateWaiver = vi.fn().mockResolvedValue({ id: 1 });
      vi.mocked(governanceApi.createWaiver).mockImplementation(mockCreateWaiver);

      const invalidateQueriesSpy = vi.spyOn(queryClient, "invalidateQueries");

      renderModal();

      const textarea = screen.getByPlaceholderText(/Explain why this waiver is needed/i);
      const longText = "This is a valid justification that is longer than fifty characters to pass validation.";
      await user.type(textarea, longText);

      const submitButton = screen.getByRole("button", { name: /submit request/i });
      await user.click(submitButton);

      await waitFor(() => {
        expect(invalidateQueriesSpy).toHaveBeenCalledWith({
          queryKey: ["policy-runs"],
        });
      });
    });
  });

  describe("Date picker", () => {
    it("opens calendar when date button is clicked", async () => {
      const user = userEvent.setup();
      renderModal();

      // The date button shows the formatted date
      const dateButton = screen.getByRole("button", { name: /april/i });
      await user.click(dateButton);

      // Calendar should be visible (checking for month navigation)
      await waitFor(() => {
        expect(screen.getByRole("grid")).toBeInTheDocument();
      });
    });

    it("displays maximum 30 days helper text", () => {
      renderModal();

      expect(screen.getByText(/Maximum 30 days from today/i)).toBeInTheDocument();
    });
  });

  describe("Form reset", () => {
    it("resets form when modal is reopened", async () => {
      const user = userEvent.setup();
      const { rerender } = renderModal({ open: true });

      const textarea = screen.getByPlaceholderText(/Explain why this waiver is needed/i);
      await user.type(textarea, "Some text");

      // Close modal
      rerender(
        <QueryClientProvider client={queryClient}>
          <WaiverModal
            open={false}
            onOpenChange={vi.fn()}
            ruleIds={["rule-1"]}
            repo="test-repo"
            prNumber={123}
          />
        </QueryClientProvider>
      );

      // Reopen modal
      rerender(
        <QueryClientProvider client={queryClient}>
          <WaiverModal
            open={true}
            onOpenChange={vi.fn()}
            ruleIds={["rule-1"]}
            repo="test-repo"
            prNumber={123}
          />
        </QueryClientProvider>
      );

      const textareaAfterReopen = screen.getByPlaceholderText(
        /Explain why this waiver is needed/i
      ) as HTMLTextAreaElement;
      expect(textareaAfterReopen.value).toBe("");
    });
  });

  describe("Cancel button", () => {
    it("closes modal when cancel button is clicked", async () => {
      const user = userEvent.setup();
      const mockOnOpenChange = vi.fn();
      renderModal({ onOpenChange: mockOnOpenChange });

      const cancelButton = screen.getByRole("button", { name: /cancel/i });
      await user.click(cancelButton);

      expect(mockOnOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
