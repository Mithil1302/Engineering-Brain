export function BlueprintCardSkeleton() {
  return (
    <div className="p-3 rounded-xl border border-slate-700/40 space-y-2">
      <div className="h-4 bg-slate-800 rounded animate-pulse" />
      <div className="h-3 bg-slate-800 rounded animate-pulse w-3/4" />
    </div>
  );
}

export function BlueprintBannerSkeleton() {
  return <div className="h-16 bg-slate-800 rounded animate-pulse" />;
}

export function DesignTabSkeleton() {
  return (
    <div className="h-[600px] bg-slate-800 rounded-xl animate-pulse flex items-center justify-center">
      <div className="text-slate-600 text-sm">Loading diagram...</div>
    </div>
  );
}

export function RationaleTabSkeleton() {
  return (
    <div className="flex gap-6">
      <div className="w-[65%] space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-32 bg-slate-800 rounded-xl animate-pulse" />
        ))}
      </div>
      <div className="w-[35%] space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 bg-slate-800 rounded-lg animate-pulse" />
        ))}
      </div>
    </div>
  );
}

export function ArtifactsTabSkeleton() {
  return (
    <div className="flex gap-3 h-[600px]">
      <div className="w-[200px] bg-slate-800 rounded-xl animate-pulse" />
      <div className="flex-1 bg-slate-800 rounded-xl animate-pulse" />
    </div>
  );
}
