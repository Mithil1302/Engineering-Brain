import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { PolicyDetailPanel } from "./PolicyDetailPanel";
import { PolicyRun } from "@/lib/types";

describe("PolicyDetailPanel", () => {
  it("displays empty state when no run is selected", () => {
    render(<PolicyDetailPanel run={null} />);
    
    expect(
      screen.getByText("Select a policy run to view details")
    ).toBeInTheDocument();
  });

  it("displays merge gate banner with blocked state", () => {
    const mockRun: PolicyRun = {
      id: 1,
      repo: "test-repo",
      pr_number: 123,
      rule_set: "default",
      summary_status: "block",
      merge_gate: {
        decision: "block",
        blocking_rule_ids: ["rule-1"],
      },
      findings: [
        {
          rule_id: "rule-1",
          severity: "critical",
          status: "fail",
          title: "Missing documentation",
          description: "API endpoints are not documented",
        },
      ],
      produced_at: new Date().toISOString(),
    };

    render(<PolicyDetailPanel run={mockRun} />);
    
    expect(
      screen.getByText("This PR is blocked from merging")
    ).toBeInTheDocument();
  });

  it("displays merge gate banner with warned state", () => {
    const mockRun: PolicyRun = {
      id: 1,
      repo: "test-repo",
      pr_number: 123,
      rule_set: "default",
      summary_status: "warn",
      merge_gate: {
        decision: "allow",
      },
      findings: [],
      produced_at: new Date().toISOString(),
    };

    render(<PolicyDetailPanel run={mockRun} />);
    
    expect(
      screen.getByText("This PR has warnings that should be resolved")
    ).toBeInTheDocument();
  });

  it("displays merge gate banner with open state", () => {
    const mockRun: PolicyRun = {
      id: 1,
      repo: "test-repo",
      pr_number: 123,
      rule_set: "default",
      summary_status: "pass",
      merge_gate: {
        decision: "allow",
      },
      findings: [],
      produced_at: new Date().toISOString(),
    };

    render(<PolicyDetailPanel run={mockRun} />);
    
    expect(screen.getByText("This PR is clear to merge")).toBeInTheDocument();
  });

  it("displays PR header with PR number and branch", () => {
    const mockRun: PolicyRun = {
      id: 1,
      repo: "test-repo",
      pr_number: 123,
      rule_set: "default",
      summary_status: "pass",
      produced_at: new Date().toISOString(),
    };

    render(<PolicyDetailPanel run={mockRun} />);
    
    expect(screen.getByText("PR #123")).toBeInTheDocument();
    expect(screen.getByText("test-repo")).toBeInTheDocument();
  });

  it("displays rules section with failed, warned, and passed groups", () => {
    const mockRun: PolicyRun = {
      id: 1,
      repo: "test-repo",
      pr_number: 123,
      rule_set: "default",
      summary_status: "warn",
      findings: [
        {
          rule_id: "rule-1",
          severity: "critical",
          status: "fail",
          title: "Critical issue",
          description: "This is critical",
        },
        {
          rule_id: "rule-2",
          severity: "medium",
          status: "warn",
          title: "Warning issue",
          description: "This is a warning",
        },
        {
          rule_id: "rule-3",
          severity: "low",
          status: "pass",
          title: "Passed check",
          description: "This passed",
        },
      ],
      produced_at: new Date().toISOString(),
    };

    render(<PolicyDetailPanel run={mockRun} />);
    
    expect(screen.getByText(/Failed \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Warned \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/Passed \(1\)/)).toBeInTheDocument();
  });

  it("calls onRequestWaiver when request waiver button is clicked", () => {
    const mockOnRequestWaiver = vi.fn();
    const mockRun: PolicyRun = {
      id: 1,
      repo: "test-repo",
      pr_number: 123,
      rule_set: "default",
      summary_status: "block",
      merge_gate: {
        decision: "block",
        blocking_rule_ids: ["rule-1"],
      },
      findings: [],
      produced_at: new Date().toISOString(),
    };

    render(
      <PolicyDetailPanel run={mockRun} onRequestWaiver={mockOnRequestWaiver} />
    );
    
    const requestWaiverButton = screen.getByText("Request waiver");
    requestWaiverButton.click();
    
    expect(mockOnRequestWaiver).toHaveBeenCalledWith(["rule-1"]);
  });

  it("does not display patches section when no patches exist", () => {
    const mockRun: PolicyRun = {
      id: 1,
      repo: "test-repo",
      pr_number: 123,
      rule_set: "default",
      summary_status: "pass",
      suggested_patches: [],
      produced_at: new Date().toISOString(),
    };

    render(<PolicyDetailPanel run={mockRun} />);
    
    expect(screen.queryByText(/Suggested Patches/)).not.toBeInTheDocument();
  });

  it("displays waiver section when waiver exists", () => {
    const mockRun: PolicyRun = {
      id: 1,
      repo: "test-repo",
      pr_number: 123,
      rule_set: "default",
      summary_status: "block",
      merge_gate: {
        decision: "allow_with_waiver",
        waiver: {
          requested_by: "John Doe",
          approved_by: "Jane Smith",
          rule_ids: ["rule-1", "rule-2"],
          justification: "Emergency fix needed",
          expires_at: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000).toISOString(),
        },
      },
      produced_at: new Date().toISOString(),
    };

    render(<PolicyDetailPanel run={mockRun} />);
    
    expect(screen.getByText("Applied")).toBeInTheDocument();
    expect(screen.getByText("John Doe")).toBeInTheDocument();
    expect(screen.getByText("Jane Smith")).toBeInTheDocument();
  });
});
