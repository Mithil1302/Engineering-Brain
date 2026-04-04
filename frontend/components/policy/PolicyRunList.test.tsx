import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { PolicyRunList } from "./PolicyRunList";
import type { PolicyRun } from "@/lib/types";

// Mock the utils module
vi.mock("@/lib/utils", () => ({
  formatRelativeTime: (date: string) => "2 hours ago",
  cn: (...classes: any[]) => classes.filter(Boolean).join(" "),
}));

describe("PolicyRunList", () => {
  const mockRuns: PolicyRun[] = [
    {
      id: 1,
      repo: "org/repo-one",
      pr_number: 123,
      rule_set: "default",
      summary_status: "pass",
      merge_gate: { decision: "allow" },
      produced_at: "2024-01-15T10:00:00Z",
    },
    {
      id: 2,
      repo: "org/repo-two",
      pr_number: 456,
      rule_set: "strict",
      summary_status: "warn",
      merge_gate: { decision: "allow_with_waiver" },
      produced_at: "2024-01-15T09:00:00Z",
    },
    {
      id: 3,
      repo: "org/repo-three",
      pr_number: 789,
      rule_set: "security",
      summary_status: "block",
      merge_gate: { decision: "block" },
      produced_at: "2024-01-15T08:00:00Z",
    },
  ];

  const defaultProps = {
    runs: mockRuns,
    selectedRunId: null,
    onSelectRun: vi.fn(),
    onLoadMore: vi.fn(),
    hasNextPage: false,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders all policy run cards", () => {
    render(<PolicyRunList {...defaultProps} />);

    expect(screen.getByText("org/repo-one")).toBeInTheDocument();
    expect(screen.getByText("org/repo-two")).toBeInTheDocument();
    expect(screen.getByText("org/repo-three")).toBeInTheDocument();
  });

  it("displays PR numbers with external link icons", () => {
    render(<PolicyRunList {...defaultProps} />);

    const prLink = screen.getByRole("link", { name: /#123/i });
    expect(prLink).toHaveAttribute("href", "https://github.com/org/repo-one/pull/123");
    expect(prLink).toHaveAttribute("target", "_blank");
  });

  it("displays ruleset badges", () => {
    render(<PolicyRunList {...defaultProps} />);

    expect(screen.getByText("default")).toBeInTheDocument();
    expect(screen.getByText("strict")).toBeInTheDocument();
    expect(screen.getByText("security")).toBeInTheDocument();
  });

  it("displays outcome badges with correct styling", () => {
    render(<PolicyRunList {...defaultProps} />);

    const passBadge = screen.getByText("pass");
    expect(passBadge).toHaveClass("bg-green-500");

    const warnBadge = screen.getByText("warn");
    expect(warnBadge).toHaveClass("bg-amber-500");

    const blockBadge = screen.getByText("block");
    expect(blockBadge).toHaveClass("bg-red-500");
  });

  it("displays merge gate lock icons correctly", () => {
    const { container } = render(<PolicyRunList {...defaultProps} />);

    // Check for LockOpen icons (green) for allow/allow_with_waiver
    const unlockIcons = container.querySelectorAll(".text-green-500");
    expect(unlockIcons.length).toBeGreaterThan(0);

    // Check for LockKeyhole icon (red) for block
    const lockIcons = container.querySelectorAll(".text-red-500");
    expect(lockIcons.length).toBeGreaterThan(0);
  });

  it("displays relative timestamps", () => {
    render(<PolicyRunList {...defaultProps} />);

    const timestamps = screen.getAllByText("2 hours ago");
    expect(timestamps).toHaveLength(3);
  });

  it("calls onSelectRun when a run card is clicked", () => {
    const onSelectRun = vi.fn();
    render(<PolicyRunList {...defaultProps} onSelectRun={onSelectRun} />);

    const firstCard = screen.getByText("org/repo-one").closest("button");
    fireEvent.click(firstCard!);

    expect(onSelectRun).toHaveBeenCalledWith(1);
  });

  it("applies selected styling to the selected run", () => {
    render(<PolicyRunList {...defaultProps} selectedRunId={2} />);

    const selectedCard = screen.getByText("org/repo-two").closest("button");
    expect(selectedCard).toHaveClass("border-l-[3px]", "border-l-blue-500", "bg-slate-800/50");
  });

  it("renders sentinel div for infinite scroll when hasNextPage is true", () => {
    // Mock IntersectionObserver before rendering
    global.IntersectionObserver = class IntersectionObserver {
      observe = vi.fn();
      disconnect = vi.fn();
      unobserve = vi.fn();
      takeRecords = vi.fn();
      root = null;
      rootMargin = "";
      thresholds = [];
      constructor() {}
    } as any;

    const { container } = render(<PolicyRunList {...defaultProps} hasNextPage={true} />);

    const sentinel = container.querySelector(".h-4.w-full");
    expect(sentinel).toBeInTheDocument();
  });

  it("does not render sentinel div when hasNextPage is false", () => {
    const { container } = render(<PolicyRunList {...defaultProps} hasNextPage={false} />);

    const sentinel = container.querySelector(".h-4.w-full");
    expect(sentinel).not.toBeInTheDocument();
  });

  it("triggers onLoadMore when sentinel enters viewport", async () => {
    const onLoadMore = vi.fn();
    
    // Mock IntersectionObserver
    global.IntersectionObserver = class IntersectionObserver {
      observe = vi.fn();
      disconnect = vi.fn();
      unobserve = vi.fn();
      takeRecords = vi.fn();
      root = null;
      rootMargin = "";
      thresholds = [];
      
      constructor(callback: IntersectionObserverCallback) {
        // Simulate intersection immediately
        setTimeout(() => {
          callback([{ isIntersecting: true } as IntersectionObserverEntry], this as any);
        }, 0);
      }
    } as any;

    render(<PolicyRunList {...defaultProps} hasNextPage={true} onLoadMore={onLoadMore} />);

    await waitFor(() => {
      expect(onLoadMore).toHaveBeenCalled();
    });
  });

  it("truncates branch names longer than 20 characters", () => {
    const runsWithLongBranch: PolicyRun[] = [
      {
        id: 1,
        repo: "org/repo",
        pr_number: 123,
        rule_set: "default",
        summary_status: "pass",
        produced_at: "2024-01-15T10:00:00Z",
        branch: "feature/very-long-branch-name-that-exceeds-twenty-characters",
      } as any,
    ];

    render(<PolicyRunList {...defaultProps} runs={runsWithLongBranch} />);

    const branchPill = screen.getByText(/feature\/very-long-br.../);
    expect(branchPill).toBeInTheDocument();
  });

  it("stops propagation when clicking PR link", () => {
    const onSelectRun = vi.fn();
    render(<PolicyRunList {...defaultProps} onSelectRun={onSelectRun} />);

    const prLink = screen.getByRole("link", { name: /#123/i });
    fireEvent.click(prLink);

    // onSelectRun should not be called because stopPropagation prevents bubbling
    expect(onSelectRun).not.toHaveBeenCalled();
  });

  it("applies correct width class (w-[380px])", () => {
    const { container } = render(<PolicyRunList {...defaultProps} />);

    const listContainer = container.firstChild;
    expect(listContainer).toHaveClass("w-[380px]");
  });

  it("applies correct height class (h-14) to run cards", () => {
    render(<PolicyRunList {...defaultProps} />);

    const firstCard = screen.getByText("org/repo-one").closest("button");
    expect(firstCard).toHaveClass("h-14");
  });

  it("renders empty list without errors", () => {
    render(<PolicyRunList {...defaultProps} runs={[]} />);

    expect(screen.queryByText("org/repo-one")).not.toBeInTheDocument();
  });

  it("handles runs without PR numbers gracefully", () => {
    const runsWithoutPR: PolicyRun[] = [
      {
        id: 1,
        repo: "org/repo",
        rule_set: "default",
        summary_status: "pass",
        produced_at: "2024-01-15T10:00:00Z",
      },
    ];

    render(<PolicyRunList {...defaultProps} runs={runsWithoutPR} />);

    expect(screen.getByText("org/repo")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("handles runs without merge gate gracefully", () => {
    const runsWithoutMergeGate: PolicyRun[] = [
      {
        id: 1,
        repo: "org/repo",
        pr_number: 123,
        rule_set: "default",
        summary_status: "pass",
        produced_at: "2024-01-15T10:00:00Z",
      },
    ];

    const { container } = render(<PolicyRunList {...defaultProps} runs={runsWithoutMergeGate} />);

    // Should not render any lock icons
    const lockIcons = container.querySelectorAll(".text-red-500, .text-green-500");
    expect(lockIcons.length).toBe(0);
  });
});
