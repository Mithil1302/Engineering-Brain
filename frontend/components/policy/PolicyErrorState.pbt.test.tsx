/**
 * Property-based tests for PolicyErrorState component
 * 
 * **Validates: Requirements 4.23, 8.6**
 * 
 * Property 38: Error state with retry
 * - Error messages are always displayed correctly based on error type
 * - Retry button is always present and functional
 * - Error icon is always displayed
 * - Component handles different repo names correctly
 */

import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { PolicyErrorState, PolicyListErrorState } from "./PolicyErrorState";
import * as fc from "fast-check";
import { vi } from "vitest";

describe("PolicyErrorState - Property-Based Tests", () => {
  afterEach(() => {
    cleanup();
  });

  /**
   * Property 38: Error state with retry
   * 
   * For any error type and repo name, the error state must:
   * 1. Display the correct message
   * 2. Include a retry button
   * 3. Call onRetry when button is clicked
   */
  it("Property 38: error state always displays correct message and retry button", { timeout: 10000 }, () => {
    fc.assert(
      fc.property(
        fc.constantFrom("empty", "network"),
        fc.string({ minLength: 2, maxLength: 50 }).filter(s => s.trim().length > 0),
        (errorType, repoName) => {
          const mockOnRetry = vi.fn();
          
          const { container } = render(
            <PolicyErrorState
              type={errorType as "empty" | "network"}
              activeRepo={repoName}
              onRetry={mockOnRetry}
            />
          );
          
          // Check correct message is displayed
          if (errorType === "empty") {
            expect(
              container.textContent
            ).toContain(`No policy runs found for ${repoName} in the selected date range`);
          } else {
            expect(
              container.textContent
            ).toContain("Failed to load policy runs. Check your connection.");
          }
          
          // Check retry button exists
          const retryButton = screen.getByRole("button", { name: /retry/i });
          expect(retryButton).toBeInTheDocument();
          
          // Check retry button calls onRetry
          fireEvent.click(retryButton);
          expect(mockOnRetry).toHaveBeenCalledTimes(1);
          
          cleanup();
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Property 38: Error icon is always present
   * 
   * Regardless of error type or repo name, the error icon should
   * always be displayed.
   */
  it("Property 38: error icon is always present", () => {
    fc.assert(
      fc.property(
        fc.constantFrom("empty", "network"),
        fc.string({ minLength: 2, maxLength: 50 }).filter(s => s.trim().length > 0),
        (errorType, repoName) => {
          const mockOnRetry = vi.fn();
          
          const { container } = render(
            <PolicyErrorState
              type={errorType as "empty" | "network"}
              activeRepo={repoName}
              onRetry={mockOnRetry}
            />
          );
          
          // Check for icon (svg element)
          const icon = container.querySelector("svg");
          expect(icon).toBeInTheDocument();
          
          cleanup();
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Property 38: Retry button can be clicked multiple times
   * 
   * The retry button should remain functional and call onRetry
   * each time it's clicked.
   */
  it("Property 38: retry button can be clicked multiple times", { timeout: 10000 }, () => {
    fc.assert(
      fc.property(
        fc.constantFrom("empty", "network"),
        fc.string({ minLength: 2, maxLength: 50 }).filter(s => s.trim().length > 0),
        fc.integer({ min: 1, max: 10 }),
        (errorType, repoName, clickCount) => {
          const mockOnRetry = vi.fn();
          
          render(
            <PolicyErrorState
              type={errorType as "empty" | "network"}
              activeRepo={repoName}
              onRetry={mockOnRetry}
            />
          );
          
          const retryButton = screen.getByRole("button", { name: /retry/i });
          
          // Click button multiple times
          for (let i = 0; i < clickCount; i++) {
            fireEvent.click(retryButton);
          }
          
          expect(mockOnRetry).toHaveBeenCalledTimes(clickCount);
          
          cleanup();
        }
      ),
      { numRuns: 100 }
    );
  });
});

describe("PolicyListErrorState - Property-Based Tests", () => {
  afterEach(() => {
    cleanup();
  });

  /**
   * Property 38: List error state always displays correct message and retry button
   */
  it("Property 38: list error state always displays correct message and retry button", () => {
    fc.assert(
      fc.property(
        fc.constantFrom("empty", "network"),
        fc.string({ minLength: 2, maxLength: 50 }).filter(s => s.trim().length > 0),
        (errorType, repoName) => {
          const mockOnRetry = vi.fn();
          
          const { container } = render(
            <PolicyListErrorState
              type={errorType as "empty" | "network"}
              activeRepo={repoName}
              onRetry={mockOnRetry}
            />
          );
          
          // Check correct message is displayed
          if (errorType === "empty") {
            expect(
              container.textContent
            ).toContain(`No policy runs found for ${repoName} in the selected date range`);
          } else {
            expect(
              container.textContent
            ).toContain("Failed to load policy runs. Check your connection.");
          }
          
          // Check retry button exists and works
          const retryButton = screen.getByRole("button", { name: /retry/i });
          expect(retryButton).toBeInTheDocument();
          
          fireEvent.click(retryButton);
          expect(mockOnRetry).toHaveBeenCalledTimes(1);
          
          cleanup();
        }
      ),
      { numRuns: 100 }
    );
  });

  /**
   * Property 38: Both error state components have consistent behavior
   * 
   * PolicyErrorState and PolicyListErrorState should behave the same way
   * for the same inputs.
   */
  it("Property 38: both error state components have consistent behavior", { timeout: 10000 }, () => {
    fc.assert(
      fc.property(
        fc.constantFrom("empty", "network"),
        fc.string({ minLength: 2, maxLength: 50 }).filter(s => s.trim().length > 0),
        (errorType, repoName) => {
          const mockOnRetry1 = vi.fn();
          const mockOnRetry2 = vi.fn();
          
          const { container: container1 } = render(
            <PolicyErrorState
              type={errorType as "empty" | "network"}
              activeRepo={repoName}
              onRetry={mockOnRetry1}
            />
          );
          
          const { container: container2 } = render(
            <PolicyListErrorState
              type={errorType as "empty" | "network"}
              activeRepo={repoName}
              onRetry={mockOnRetry2}
            />
          );
          
          // Both should have error icon
          expect(container1.querySelector("svg")).toBeInTheDocument();
          expect(container2.querySelector("svg")).toBeInTheDocument();
          
          // Both should have retry button
          const buttons = screen.getAllByRole("button", { name: /retry/i });
          expect(buttons.length).toBe(2);
          
          cleanup();
        }
      ),
      { numRuns: 50 }
    );
  });
});
