/**
 * Unit tests for PolicyDetailSkeleton component
 * 
 * Tests:
 * - Renders banner skeleton with correct height (h-16)
 * - Renders three accordion header skeletons (h-10)
 * - Includes animate-pulse class
 * - Has correct structure matching detail panel
 */

import { render } from "@testing-library/react";
import { PolicyDetailSkeleton } from "./PolicyDetailSkeleton";

describe("PolicyDetailSkeleton", () => {
  it("renders banner skeleton with correct height", () => {
    const { container } = render(<PolicyDetailSkeleton />);
    const banner = container.querySelector(".h-16");
    expect(banner).toBeInTheDocument();
  });

  it("includes animate-pulse class", () => {
    const { container } = render(<PolicyDetailSkeleton />);
    const skeleton = container.querySelector(".animate-pulse");
    expect(skeleton).toBeInTheDocument();
  });

  it("renders three accordion header skeletons", () => {
    const { container } = render(<PolicyDetailSkeleton />);
    const accordionHeaders = container.querySelectorAll(".h-10");
    expect(accordionHeaders.length).toBe(3);
  });

  it("has correct structure with sections", () => {
    const { container } = render(<PolicyDetailSkeleton />);
    
    // Check for banner
    const banner = container.querySelector(".h-16");
    expect(banner).toBeInTheDocument();
    
    // Check for PR header section
    const prHeader = container.querySelector(".p-4.border-b");
    expect(prHeader).toBeInTheDocument();
    
    // Check for rules section
    const rulesSection = container.querySelectorAll(".p-4.border-b");
    expect(rulesSection.length).toBeGreaterThan(0);
  });

  it("renders all skeleton elements with bg-slate-800", () => {
    const { container } = render(<PolicyDetailSkeleton />);
    const skeletonElements = container.querySelectorAll(".bg-slate-800");
    expect(skeletonElements.length).toBeGreaterThan(5);
  });
});
