/**
 * Unit tests for PolicyErrorState component
 * 
 * Tests:
 * - Displays correct message for empty results
 * - Displays correct message for network errors
 * - Includes retry button
 * - Calls onRetry when retry button is clicked
 * - Includes error icon
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { PolicyErrorState, PolicyListErrorState } from "./PolicyErrorState";
import { vi } from "vitest";

describe("PolicyErrorState", () => {
  const mockOnRetry = vi.fn();
  const activeRepo = "test-repo";

  beforeEach(() => {
    mockOnRetry.mockClear();
  });

  it("displays correct message for empty results", () => {
    render(
      <PolicyErrorState
        type="empty"
        activeRepo={activeRepo}
        onRetry={mockOnRetry}
      />
    );

    expect(
      screen.getByText(
        `No policy runs found for ${activeRepo} in the selected date range`
      )
    ).toBeInTheDocument();
  });

  it("displays correct message for network errors", () => {
    render(
      <PolicyErrorState
        type="network"
        activeRepo={activeRepo}
        onRetry={mockOnRetry}
      />
    );

    expect(
      screen.getByText("Failed to load policy runs. Check your connection.")
    ).toBeInTheDocument();
  });

  it("includes retry button", () => {
    render(
      <PolicyErrorState
        type="empty"
        activeRepo={activeRepo}
        onRetry={mockOnRetry}
      />
    );

    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("calls onRetry when retry button is clicked", () => {
    render(
      <PolicyErrorState
        type="empty"
        activeRepo={activeRepo}
        onRetry={mockOnRetry}
      />
    );

    const retryButton = screen.getByRole("button", { name: /retry/i });
    fireEvent.click(retryButton);

    expect(mockOnRetry).toHaveBeenCalledTimes(1);
  });

  it("includes error icon", () => {
    const { container } = render(
      <PolicyErrorState
        type="empty"
        activeRepo={activeRepo}
        onRetry={mockOnRetry}
      />
    );

    // Check for AlertCircle icon (lucide-react renders as svg)
    const icon = container.querySelector("svg");
    expect(icon).toBeInTheDocument();
  });
});

describe("PolicyListErrorState", () => {
  const mockOnRetry = vi.fn();
  const activeRepo = "test-repo";

  beforeEach(() => {
    mockOnRetry.mockClear();
  });

  it("displays correct message for empty results", () => {
    render(
      <PolicyListErrorState
        type="empty"
        activeRepo={activeRepo}
        onRetry={mockOnRetry}
      />
    );

    expect(
      screen.getByText(
        `No policy runs found for ${activeRepo} in the selected date range`
      )
    ).toBeInTheDocument();
  });

  it("displays correct message for network errors", () => {
    render(
      <PolicyListErrorState
        type="network"
        activeRepo={activeRepo}
        onRetry={mockOnRetry}
      />
    );

    expect(
      screen.getByText("Failed to load policy runs. Check your connection.")
    ).toBeInTheDocument();
  });

  it("includes retry button", () => {
    render(
      <PolicyListErrorState
        type="empty"
        activeRepo={activeRepo}
        onRetry={mockOnRetry}
      />
    );

    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("calls onRetry when retry button is clicked", () => {
    render(
      <PolicyListErrorState
        type="empty"
        activeRepo={activeRepo}
        onRetry={mockOnRetry}
      />
    );

    const retryButton = screen.getByRole("button", { name: /retry/i });
    fireEvent.click(retryButton);

    expect(mockOnRetry).toHaveBeenCalledTimes(1);
  });
});
