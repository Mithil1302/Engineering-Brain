/**
 * Unit tests for PolicyRunSkeleton component
 * 
 * Tests:
 * - Renders skeleton with correct structure
 * - Displays five rectangles of varying widths
 * - Has correct height (56px / h-14)
 * - Includes animate-pulse class
 */

import { render, screen } from "@testing-library/react";
import { PolicyRunSkeleton, PolicyRunListSkeleton } from "./PolicyRunSkeleton";

describe("PolicyRunSkeleton", () => {
  it("renders skeleton with correct height", () => {
    const { container } = render(<PolicyRunSkeleton />);
    const skeleton = container.querySelector(".h-14");
    expect(skeleton).toBeInTheDocument();
  });

  it("includes animate-pulse class", () => {
    const { container } = render(<PolicyRunSkeleton />);
    const skeleton = container.querySelector(".animate-pulse");
    expect(skeleton).toBeInTheDocument();
  });

  it("renders skeleton rectangles", () => {
    const { container } = render(<PolicyRunSkeleton />);
    const rectangles = container.querySelectorAll(".bg-slate-800");
    // 7 rectangles: 1 repo name + 2 PR/branch + 4 badges/metadata
    expect(rectangles.length).toBe(7);
  });

  it("has correct structure with left and right sections", () => {
    const { container } = render(<PolicyRunSkeleton />);
    const leftSection = container.querySelector(".flex-1");
    const rightSection = container.querySelector(".shrink-0");
    expect(leftSection).toBeInTheDocument();
    expect(rightSection).toBeInTheDocument();
  });
});

describe("PolicyRunListSkeleton", () => {
  it("renders five policy run skeletons", () => {
    const { container } = render(<PolicyRunListSkeleton />);
    const skeletons = container.querySelectorAll(".h-14");
    expect(skeletons.length).toBe(5);
  });

  it("all skeletons have animate-pulse class", () => {
    const { container } = render(<PolicyRunListSkeleton />);
    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBe(5);
  });
});
