/**
 * Property-based tests for PolicyDetailSkeleton component
 * 
 * **Validates: Requirements 4.22, 8.5**
 * 
 * Property 37: Skeleton shape matching
 * - Banner skeleton height matches merge gate banner (h-16)
 * - Three accordion header skeletons match rules section structure (h-10)
 * - Overall structure matches detail panel layout
 */

import { render, cleanup } from "@testing-library/react";
import { PolicyDetailSkeleton } from "./PolicyDetailSkeleton";
import * as fc from "fast-check";

describe("PolicyDetailSkeleton - Property-Based Tests", () => {
  afterEach(() => {
    cleanup();
  });

  /**
   * Property 37: Skeleton shape matching
   * 
   * The skeleton must always match the structure of the actual detail panel
   * with correct heights and section counts.
   */
  it("Property 37: skeleton always has correct banner height and structure", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const { container } = render(<PolicyDetailSkeleton />);
        
        // Check banner height is h-16
        const banner = container.querySelector(".h-16");
        expect(banner).toBeInTheDocument();
        
        // Check animate-pulse is present
        const animatedElement = container.querySelector(".animate-pulse");
        expect(animatedElement).toBeInTheDocument();
        
        // Check three accordion header skeletons (h-10)
        const accordionHeaders = container.querySelectorAll(".h-10");
        expect(accordionHeaders.length).toBe(3);
        
        // Check all accordion headers have border
        accordionHeaders.forEach((header) => {
          expect(header.classList.contains("border")).toBe(true);
          expect(header.classList.contains("border-slate-700")).toBe(true);
        });
        
        cleanup();
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Property 37: Skeleton has correct section structure
   * 
   * The skeleton should have sections matching the detail panel:
   * - Banner
   * - PR Header
   * - Rules section with accordion headers
   * - Additional sections
   */
  it("Property 37: skeleton always has correct section structure", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const { container } = render(<PolicyDetailSkeleton />);
        
        // Check for banner (h-16)
        const banner = container.querySelector(".h-16");
        expect(banner).toBeInTheDocument();
        
        // Check for sections with border-b
        const sections = container.querySelectorAll(".border-b");
        expect(sections.length).toBeGreaterThanOrEqual(2);
        
        // Check for skeleton elements
        const skeletonElements = container.querySelectorAll(".bg-slate-800");
        expect(skeletonElements.length).toBeGreaterThan(5);
        
        cleanup();
      }),
      { numRuns: 100 }
    );
  });

  /**
   * Property 37: Accordion headers have consistent styling
   * 
   * All three accordion header skeletons should have the same height
   * and styling to match the actual accordion structure.
   */
  it("Property 37: accordion headers have consistent height and styling", () => {
    fc.assert(
      fc.property(fc.constant(null), () => {
        const { container } = render(<PolicyDetailSkeleton />);
        
        const accordionHeaders = container.querySelectorAll(".h-10");
        
        // Check exactly 3 headers
        expect(accordionHeaders.length).toBe(3);
        
        // Check all have same classes
        accordionHeaders.forEach((header) => {
          expect(header.classList.contains("h-10")).toBe(true);
          expect(header.classList.contains("bg-slate-800")).toBe(true);
          expect(header.classList.contains("rounded")).toBe(true);
          expect(header.classList.contains("border")).toBe(true);
        });
        
        cleanup();
      }),
      { numRuns: 100 }
    );
  });
});
