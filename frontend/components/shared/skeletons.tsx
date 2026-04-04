import { Skeleton } from "@/components/ui/skeleton";

export function MessageSkeleton() {
  return <Skeleton className="h-14 w-full" />;
}

export function GraphNodeSkeleton({ type = "service" }: { type?: "service" | "engineer" }) {
  if (type === "engineer") {
    return <Skeleton className="w-[52px] h-[52px] rounded-full" />;
  }
  return <Skeleton className="w-[180px] h-[72px] rounded-lg" />;
}

export function MetricCardSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-12 w-full" />
      <Skeleton className="h-4 w-3/4" />
      <Skeleton className="h-3 w-1/2" />
    </div>
  );
}

export function PolicyRunSkeleton() {
  return (
    <div className="h-14 flex items-center gap-3 px-4">
      <Skeleton className="h-4 w-20" />
      <Skeleton className="h-4 w-16" />
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-4 w-24" />
      <Skeleton className="h-4 w-16" />
    </div>
  );
}

export function BlueprintCardSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-3 w-3/4" />
    </div>
  );
}

export function StageSkeleton() {
  return <Skeleton className="w-[200px] h-[100px] rounded-lg" />;
}
