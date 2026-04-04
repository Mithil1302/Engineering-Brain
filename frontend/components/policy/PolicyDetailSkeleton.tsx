/**
 * PolicyDetailSkeleton component
 * 
 * Displays skeleton loading state for the policy detail panel.
 * Includes:
 * - Full-width banner skeleton (h-16) matching merge gate banner height
 * - Three accordion header skeletons (h-10) for the rules section
 * 
 * Requirements: 4.22, 8.5
 * Properties: 37 (skeleton shape matching)
 */

export function PolicyDetailSkeleton() {
  return (
    <div className="flex-1 h-full overflow-y-auto bg-slate-950 animate-pulse">
      {/* Banner skeleton - matches merge gate banner height */}
      <div className="w-full h-16 bg-slate-800 rounded" />

      {/* PR Header skeleton */}
      <div className="p-4 border-b border-slate-800 space-y-3">
        <div className="h-6 w-32 bg-slate-800 rounded" />
        <div className="h-4 w-48 bg-slate-800 rounded" />
        <div className="flex items-center gap-2">
          <div className="h-5 w-20 bg-slate-800 rounded" />
          <div className="h-4 w-24 bg-slate-800 rounded" />
        </div>
      </div>

      {/* Rules section skeleton */}
      <div className="p-4 border-b border-slate-800">
        <div className="h-5 w-24 bg-slate-800 rounded mb-3" />
        
        {/* Three accordion header skeletons */}
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={index}
              className="h-10 bg-slate-800 rounded border border-slate-700"
            />
          ))}
        </div>
      </div>

      {/* Additional sections skeleton */}
      <div className="p-4 space-y-4">
        <div className="h-20 bg-slate-800 rounded" />
        <div className="h-16 bg-slate-800 rounded" />
      </div>
    </div>
  );
}
