/**
 * PolicyRunSkeleton component
 * 
 * Displays skeleton loading state for policy run list items.
 * Each skeleton is 56px tall (h-14) with rectangles of varying widths
 * to match the structure of actual policy run cards.
 * 
 * Requirements: 4.22, 8.5
 * Properties: 37 (skeleton shape matching)
 */

export function PolicyRunSkeleton() {
  return (
    <div className="w-full h-14 px-3 py-2 flex items-center gap-2 border-b border-slate-800 animate-pulse">
      {/* Left section: Repo and PR info */}
      <div className="flex-1 min-w-0 flex flex-col gap-1">
        {/* Repo name skeleton */}
        <div className="h-3 w-20 bg-slate-800 rounded" />
        
        {/* PR number and branch skeleton */}
        <div className="flex items-center gap-1.5">
          <div className="h-4 w-12 bg-slate-800 rounded" />
          <div className="h-5 w-24 bg-slate-800 rounded-full" />
        </div>
      </div>

      {/* Right section: Badges and metadata */}
      <div className="flex items-center gap-2 shrink-0">
        {/* Ruleset badge skeleton */}
        <div className="h-5 w-16 bg-slate-800 rounded" />
        
        {/* Outcome badge skeleton */}
        <div className="h-5 w-12 bg-slate-800 rounded" />
        
        {/* Lock icon skeleton */}
        <div className="h-4 w-4 bg-slate-800 rounded" />
        
        {/* Timestamp skeleton */}
        <div className="h-3 w-14 bg-slate-800 rounded" />
      </div>
    </div>
  );
}

/**
 * PolicyRunListSkeleton component
 * 
 * Displays five policy run skeletons for the list loading state.
 */
export function PolicyRunListSkeleton() {
  return (
    <div className="w-full">
      {Array.from({ length: 5 }).map((_, index) => (
        <PolicyRunSkeleton key={index} />
      ))}
    </div>
  );
}
