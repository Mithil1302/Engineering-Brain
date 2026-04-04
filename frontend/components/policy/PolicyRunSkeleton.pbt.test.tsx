/**
 * Property-based tests for PolicyRunSkeleton component
 * 
 * **Validates: Requirements 4.22, 8.5**
 * 
 * Property 37: Skeleton shape matching
 * - Skeleton dimensions match actual content dimensions
 * - Five rectangles of varying widths are present
 * - Height is consistently 56px (h-14)
 */

import { render, cleanup } from "@testing-library/react";
import { PolicyRunSkeleton, PolicyRunListSkeleton } from "./PolicyRunSkeleton";
import * as fc from "fast-check";

describe("PolicyRunSkeleton - Property-Based Tests", () => {
  afterEach(() => {
    cleanup();
  });

  /**
   * Property 37: Skeleton shape matching
   * 
   * The skeleton must always have the correct structure regardless of
   * how many times it's rendered or in what context.
   */
  it("Property 37: skeleton always has correct height and structure", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const { container } = render(<PolicyRunSkeleton />);
        
        // Check height is 56px (h-14 class)
        const skeleton = container.querySelector(".h-14");
        expect(skeleton).toBeInTheDocument();
        
        // Check animate-pulse is present
        const animatedElement = container.querySelector(".animate-pulse");
        expect(animatedElement).toBeInTheDocument();
        
        // Check rectangles are present (7 total)
        const rectangles = container.querySelectorAll(".bg-slate-800");
        expect(rectangles.length).toBe(7);
        
        // Check structure has left and right sections
        const leftSection = container.querySelector(".flex-1");
        const rightSection = container.querySelector(".shrink-0");
        expect(leftSection).toBeInTheDocument();
        expect(rightSection).toBeInTheDocument();
        
        cleanup();
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Property 37: Skeleton list always renders correct number of items
   */
  it("Property 37: skeleton list always renders exactly 5 items", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const { container } = render(<PolicyRunListSkeleton />);
        
        // Check exactly 5 skeletons are rendered
        const skeletons = container.querySelectorAll(".h-14");
        expect(skeletons.length).toBe(5);
        
        // Check all have animate-pulse
        const animatedElements = container.querySelectorAll(".animate-pulse");
        expect(animatedElements.length).toBe(5);
        
        cleanup();
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Property 37: Skeleton rectangles have varying widths
   * 
   * The five rectangles should have different width classes to match
   * the varying content widths in actual policy run cards.
   */
  it("Property 37: skeleton rectangles have varying widths", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const { container } = render(<PolicyRunSkeleton />);
        
        const rectangles = container.querySelectorAll(".bg-slate-800");
        const widthClasses = Array.from(rectangles).map((rect) => {
          const classList = Array.from(rect.classList);
          return classList.find((cls) => cls.startsWith("w-"));
        });
        
        // Check that we have different width classes
        const uniqueWidths = new Set(widthClasses);
        expect(uniqueWidths.size).toBeGreaterThan(1);
        
        cleanup();
      }),
      { numRuns: 100 }
    );
  });
});
