"use client";

import { useEffect, useRef } from "react";
import { PolicyRun } from "@/lib/types";
import { formatRelativeTime, cn } from "@/lib/utils";
import { ExternalLink, LockOpen, LockKeyhole } from "lucide-react";

interface PolicyRunListProps {
  runs: PolicyRun[];
  selectedRunId: number | null;
  onSelectRun: (runId: number) => void;
  onLoadMore: () => void;
  hasNextPage: boolean;
  className?: string;
}

export function PolicyRunList({
  runs,
  selectedRunId,
  onSelectRun,
  onLoadMore,
  hasNextPage,
  className,
}: PolicyRunListProps) {
  const sentinelRef = useRef<HTMLDivElement>(null);

  // Infinite scroll with IntersectionObserver
  useEffect(() => {
    if (!sentinelRef.current || !hasNextPage) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          onLoadMore();
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(sentinelRef.current);

    return () => {
      observer.disconnect();
    };
  }, [hasNextPage, onLoadMore]);

  return (
    <div className={cn("w-[380px] h-full overflow-y-auto bg-slate-900", className)}>
      {runs.map((run, index) => (
        <PolicyRunCard
          key={run.id}
          run={run}
          isSelected={run.id === selectedRunId}
          onClick={() => onSelectRun(run.id)}
          isNew={index === 0 && run.id !== selectedRunId}
        />
      ))}
      
      {/* Sentinel div for infinite scroll */}
      {hasNextPage && (
        <div ref={sentinelRef} className="h-4 w-full" />
      )}
    </div>
  );
}

interface PolicyRunCardProps {
  run: PolicyRun;
  isSelected: boolean;
  onClick: () => void;
  isNew?: boolean;
}

function PolicyRunCard({ run, isSelected, onClick, isNew }: PolicyRunCardProps) {
  const cardRef = useRef<HTMLButtonElement>(null);

  // Animate new policy runs from SSE
  useEffect(() => {
    if (isNew && cardRef.current) {
      // Start with slide-down-from-above state
      cardRef.current.style.transform = "translateY(-16px)";
      cardRef.current.style.opacity = "0";
      
      // Trigger animation after a brief delay
      requestAnimationFrame(() => {
        if (cardRef.current) {
          cardRef.current.style.transition = "all 300ms ease-out";
          cardRef.current.style.transform = "translateY(0)";
          cardRef.current.style.opacity = "1";
        }
      });
    }
  }, [isNew]);

  // Extract PR info from run
  const prNumber = run.pr_number;
  const branchName = extractBranchName(run);
  // Trim repo name and provide fallback for whitespace-only names
  const repoName = run.repo.trim() || "(unknown repo)";

  // Truncate branch name to 20 characters
  const truncatedBranch = branchName && branchName.length > 20
    ? branchName.substring(0, 20) + "..."
    : branchName;

  // Determine merge gate status
  const mergeGateDecision = run.merge_gate?.decision;
  const isLocked = mergeGateDecision === "block";
  const isUnlocked = mergeGateDecision === "allow" || mergeGateDecision === "allow_with_waiver";

  return (
    <button
      ref={cardRef}
      type="button"
      onClick={onClick}
      className={cn(
        "w-full h-14 px-3 py-2 flex items-center gap-2 border-b border-slate-800 hover:bg-slate-800/30 transition-colors text-left",
        isSelected && "border-l-[3px] border-l-blue-500 bg-slate-800/50"
      )}
    >
      {/* Left section: Repo, PR, Branch */}
      <div className="flex-1 min-w-0 flex flex-col gap-0.5">
        {/* Repo name */}
        <div className="text-xs text-slate-500 truncate">
          {repoName}
        </div>
        
        {/* PR number with external link */}
        <div className="flex items-center gap-1.5">
          {prNumber && (
            <a
              href={`https://github.com/${repoName}/pull/${prNumber}`}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="flex items-center gap-1 text-sm text-blue-400 hover:text-blue-300 transition-colors"
            >
              #{prNumber}
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
          
          {/* Branch name pill */}
          {truncatedBranch && (
            <span className="font-mono text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 truncate max-w-[120px]">
              {truncatedBranch}
            </span>
          )}
        </div>
      </div>

      {/* Right section: Ruleset, Outcome, Merge Gate, Timestamp */}
      <div className="flex items-center gap-2 shrink-0">
        {/* Ruleset badge */}
        <span className="text-xs px-1.5 py-0.5 rounded bg-gray-700 text-gray-300">
          {run.rule_set}
        </span>

        {/* Outcome badge */}
        <OutcomeBadge outcome={run.summary_status} />

        {/* Merge gate lock icon */}
        {isLocked && (
          <LockKeyhole className="w-4 h-4 text-red-500" />
        )}
        {isUnlocked && (
          <LockOpen className="w-4 h-4 text-green-500" />
        )}

        {/* Timestamp */}
        <span className="text-[10px] text-slate-500 whitespace-nowrap">
          {formatRelativeTime(run.produced_at)}
        </span>
      </div>
    </button>
  );
}

interface OutcomeBadgeProps {
  outcome: string;
}

function OutcomeBadge({ outcome }: OutcomeBadgeProps) {
  const normalizedOutcome = outcome.toLowerCase();
  
  let bgColor = "bg-gray-500";
  let textColor = "text-white";
  
  if (normalizedOutcome === "pass") {
    bgColor = "bg-green-500";
  } else if (normalizedOutcome === "warn") {
    bgColor = "bg-amber-500";
  } else if (normalizedOutcome === "block" || normalizedOutcome === "fail") {
    bgColor = "bg-red-500";
  }

  return (
    <span
      className={cn(
        "text-[10px] font-bold uppercase px-1.5 py-0.5 rounded",
        bgColor,
        textColor
      )}
    >
      {normalizedOutcome}
    </span>
  );
}

/**
 * Extract branch name from policy run
 * This is a helper function that attempts to extract branch info from the run data
 */
function extractBranchName(run: PolicyRun): string | null {
  // Check if there's a branch field in the run object
  // The API might include this in various places
  const runAny = run as any;
  
  if (runAny.branch) return runAny.branch;
  if (runAny.branch_name) return runAny.branch_name;
  if (runAny.ref) {
    // GitHub refs are like "refs/heads/feature-branch"
    const match = runAny.ref.match(/refs\/heads\/(.+)/);
    if (match) return match[1];
    return runAny.ref;
  }
  
  // Fallback: try to extract from idempotency_key or other fields
  if (runAny.idempotency_key) {
    // idempotency_key might contain branch info
    const parts = runAny.idempotency_key.split(":");
    if (parts.length > 2) return parts[2];
  }
  
  return null;
}
