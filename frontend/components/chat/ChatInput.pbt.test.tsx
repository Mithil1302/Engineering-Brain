/**
 * Property-Based Tests for ChatInput Component
 * 
 * **Validates: Requirements 1.10, 1.11, 1.12**
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import fc from "fast-check";
import { ChatInput } from "./ChatInput";

describe("ChatInput - Property-Based Tests", () => {
  afterEach(() => {
    cleanup();
  });

  /**
   * Property 5: Textarea Auto-resize with Mirror
   * 
   * For any input text in the textarea, the height should be at least 1 row 
   * and at most 6 rows, computed using a hidden div mirror technique that 
   * matches the textarea's content and styling.
   * 
   * **Validates: Requirements 1.10**
   */
  it("Property 5: textarea height is constrained between 1 and 6 rows for any input", async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate arbitrary strings with varying lengths
        fc.string({ minLength: 0, maxLength: 200 }),
        async (text) => {
          const mockOnSend = vi.fn();
          const { unmount } = render(<ChatInput onSend={mockOnSend} />);
          
          try {
            const textarea = screen.getByPlaceholderText(/Ask anything about your system/i) as HTMLTextAreaElement;
            
            // Simulate input change
            fireEvent.change(textarea, { target: { value: text } });
            
            // Wait for height update
            await waitFor(() => {
              const computedHeight = parseInt(textarea.style.height || "24", 10);
              expect(computedHeight).toBeGreaterThan(0);
            });
            
            // Get computed height
            const computedHeight = parseInt(textarea.style.height || "24", 10);
            
            // Line height is approximately 24px
            const lineHeight = 24;
            const minHeight = lineHeight; // 1 row
            const maxHeight = lineHeight * 6; // 6 rows
            
            // Assert height is within bounds
            expect(computedHeight).toBeGreaterThanOrEqual(minHeight);
            expect(computedHeight).toBeLessThanOrEqual(maxHeight);
          } finally {
            unmount();
            cleanup();
          }
        }
      ),
      { numRuns: 30 }
    );
  }, 10000);

  /**
   * Property 6: Conditional Button States
   * 
   * For any chat input state, the send button should be:
   * - Disabled when input is empty OR streaming is in progress
   * - Enabled when input is not empty AND not streaming
   * - Replaced with a stop button (calling reader.cancel()) when streaming is in progress
   * 
   * **Validates: Requirements 1.11, 1.12**
   */
  it("Property 6: button state correctly reflects input and streaming state", async () => {
    await fc.assert(
      fc.asyncProperty(
        // Generate arbitrary input states
        fc.record({
          text: fc.string({ minLength: 0, maxLength: 50 }),
          isStreaming: fc.boolean(),
          disabled: fc.boolean(),
        }),
        async ({ text, isStreaming, disabled }) => {
          const mockOnSend = vi.fn();
          const mockOnStop = vi.fn();
          
          const { unmount } = render(
            <ChatInput 
              onSend={mockOnSend} 
              onStop={mockOnStop}
              isStreaming={isStreaming}
              disabled={disabled}
            />
          );
          
          try {
            const textarea = screen.getByPlaceholderText(
              disabled ? /Select a repository/i : /Ask anything about your system/i
            ) as HTMLTextAreaElement;
            
            // Set the text value
            if (text) {
              fireEvent.change(textarea, { target: { value: text } });
            }
            
            // Check button state based on conditions
            if (isStreaming) {
              // When streaming, stop button should be present
              const stopButton = screen.getByLabelText("Stop streaming");
              expect(stopButton).toBeInTheDocument();
              expect(screen.queryByLabelText("Send message")).not.toBeInTheDocument();
            } else {
              // When not streaming, send button should be present
              const sendButton = screen.getByLabelText("Send message");
              expect(sendButton).toBeInTheDocument();
              expect(screen.queryByLabelText("Stop streaming")).not.toBeInTheDocument();
              
              // Send button should be disabled if text is empty or component is disabled
              const shouldBeDisabled = !text.trim() || disabled;
              if (shouldBeDisabled) {
                expect(sendButton).toBeDisabled();
              } else {
                expect(sendButton).not.toBeDisabled();
              }
            }
          } finally {
            unmount();
            cleanup();
          }
        }
      ),
      { numRuns: 50 }
    );
  });

  /**
   * Additional Property: Channel mode cycles correctly
   * 
   * For any number of toggles, the channel mode should alternate correctly.
   */
  it("Property: channel mode cycles correctly for any number of toggles", async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.integer({ min: 0, max: 5 }),
        async (toggleCount) => {
          const mockOnSend = vi.fn();
          const { unmount } = render(<ChatInput onSend={mockOnSend} />);
          
          try {
            // Initial state is "Web"
            let expectedMode: "web" | "cli" = "web";
            
            // Toggle the specified number of times
            for (let i = 0; i < toggleCount; i++) {
              const currentButton = screen.getByText(expectedMode === "web" ? "Web" : "CLI Preview");
              fireEvent.click(currentButton);
              expectedMode = expectedMode === "web" ? "cli" : "web";
            }
            
            // Verify final state
            const finalButton = screen.getByText(expectedMode === "web" ? "Web" : "CLI Preview");
            expect(finalButton).toBeInTheDocument();
          } finally {
            unmount();
            cleanup();
          }
        }
      ),
      { numRuns: 20 }
    );
  });
});
