"use client";

import { PolicyRun, Finding } from "@/lib/types";
import { formatRelativeTime, cn } from "@/lib/utils";
import { XCircle, CheckCircle, AlertTriangle, ChevronRight } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import dynamic from "next/dynamic";

// Dynamically import react-diff-viewer-continued to avoid SSR issues
const ReactDiffViewer = dynamic(() => import("react-diff-viewer-continued"), {
  ssr: false,
});

interface PolicyDetailPanelProps {
  run: PolicyRun | null;
  onRequestWaiver?: (ruleIds: string[]) => void;
  className?: string;
}

export function PolicyDetailPanel({
  run,
  onRequestWaiver,
  className,
}: PolicyDetailPanelProps) {
  if (!run) {
    return (
      <div
        className={cn(
          "flex-1 flex items-center justify-center h-full",
          className
        )}
      >
        <p className="text-slate-500 text-sm">
          Select a policy run to view details
        </p>
      </div>
    );
  }

  return (
    <div className={cn("flex-1 h-full overflow-y-auto bg-slate-950", className)}>
      <MergeGateBanner run={run} onRequestWaiver={onRequestWaiver} />
      <PRHeader run={run} />
      <RulesSection run={run} onRequestWaiver={onRequestWaiver} />
      <PatchesSection run={run} />
      <DocRefreshPlanSection run={run} />
      <WaiverSection run={run} onRequestWaiver={onRequestWaiver} />
    </div>
  );
}

interface MergeGateBannerProps {
  run: PolicyRun;
  onRequestWaiver?: (ruleIds: string[]) => void;
}

function MergeGateBanner({ run, onRequestWaiver }: MergeGateBannerProps) {
  const decision = run.merge_gate?.decision;
  const blockingRuleIds = run.merge_gate?.blocking_rule_ids || [];
  const outcome = run.summary_status.toLowerCase();

  // Determine banner state
  let bgColor = "bg-green-500";
  let message = "This PR is clear to merge";
  let showBlockingItems = false;
  let showRequestWaiver = false;

  if (decision === "block" || outcome === "block") {
    bgColor = "bg-red-500";
    message = "This PR is blocked from merging";
    showBlockingItems = true;
    showRequestWaiver = true;
  } else if (outcome === "warn") {
    bgColor = "bg-amber-500";
    message = "This PR has warnings that should be resolved";
    showBlockingItems = true;
    showRequestWaiver = true;
  }

  // Get blocking findings
  const blockingFindings = run.findings?.filter((f) =>
    blockingRuleIds.includes(f.rule_id)
  ) || [];

  return (
    <div className={cn("w-full p-4", bgColor)}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <p className="text-white font-bold mb-2">{message}</p>
          
          {showBlockingItems && blockingFindings.length > 0 && (
            <ul className="list-disc list-inside space-y-1 text-white text-sm">
              {blockingFindings.map((finding) => (
                <li key={finding.rule_id}>
                  {finding.title}
                  {finding.suggested_action && (
                    <a
                      href="#"
                      className="ml-2 underline hover:no-underline"
                      onClick={(e) => {
                        e.preventDefault();
                        // Navigate to fix link if available
                      }}
                    >
                      Fix
                    </a>
                  )}
                </li>
              ))}
            </ul>
          )}

          {!showBlockingItems && (
            <p className="text-white text-sm">
              Last checked {formatRelativeTime(run.produced_at)}
            </p>
          )}
        </div>

        {showRequestWaiver && onRequestWaiver && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onRequestWaiver(blockingRuleIds)}
            className="bg-white/10 text-white border-white/20 hover:bg-white/20"
          >
            Request waiver
          </Button>
        )}
      </div>
    </div>
  );
}

interface PRHeaderProps {
  run: PolicyRun;
}

function PRHeader({ run }: PRHeaderProps) {
  // Extract PR info
  const prNumber = run.pr_number;
  const branchName = extractBranchName(run);
  const repoName = run.repo;

  return (
    <div className="p-4 border-b border-slate-800">
      <h2 className="text-lg font-semibold text-white mb-2">
        {prNumber ? `PR #${prNumber}` : "Policy Check"}
      </h2>
      
      <div className="flex items-center gap-2 text-sm text-slate-400 mb-2">
        {branchName && (
          <>
            <span className="font-mono">{branchName}</span>
            <ChevronRight className="w-4 h-4" />
          </>
        )}
        <span>{repoName}</span>
      </div>

      <div className="flex items-center gap-2">
        <Badge variant="outline" className="text-xs">
          {run.rule_set}
        </Badge>
        <span className="text-xs text-slate-500">
          {formatRelativeTime(run.produced_at)}
        </span>
      </div>
    </div>
  );
}

interface RulesSectionProps {
  run: PolicyRun;
  onRequestWaiver?: (ruleIds: string[]) => void;
}

function RulesSection({ run, onRequestWaiver }: RulesSectionProps) {
  const findings = run.findings || [];

  // Group findings by severity/status
  const failedFindings = findings.filter(
    (f) => (f.severity === "critical" || f.severity === "high") && f.status !== "pass"
  );
  const warnedFindings = findings.filter(
    (f) => (f.severity === "medium" || f.severity === "low") && f.status !== "pass"
  );
  const passedFindings = findings.filter((f) => f.status === "pass");

  return (
    <div className="p-4 border-b border-slate-800">
      <h3 className="text-base font-semibold text-white mb-3">Rules</h3>

      <Accordion type="multiple" defaultValue={["failed"]} className="space-y-2">
        {/* Failed rules */}
        {failedFindings.length > 0 && (
          <AccordionItem value="failed" className="border border-slate-800 rounded-lg">
            <AccordionTrigger className="px-4 hover:no-underline">
              <span className="text-red-400 font-medium">
                Failed ({failedFindings.length})
              </span>
            </AccordionTrigger>
            <AccordionContent className="px-4">
              <div className="space-y-3">
                {failedFindings.map((finding) => (
                  <RuleItem
                    key={finding.rule_id}
                    finding={finding}
                    onRequestWaiver={onRequestWaiver}
                  />
                ))}
              </div>
            </AccordionContent>
          </AccordionItem>
        )}

        {/* Warned rules */}
        {warnedFindings.length > 0 && (
          <AccordionItem value="warned" className="border border-slate-800 rounded-lg">
            <AccordionTrigger className="px-4 hover:no-underline">
              <span className="text-amber-400 font-medium">
                Warned ({warnedFindings.length})
              </span>
            </AccordionTrigger>
            <AccordionContent className="px-4">
              <div className="space-y-3">
                {warnedFindings.map((finding) => (
                  <RuleItem
                    key={finding.rule_id}
                    finding={finding}
                    onRequestWaiver={onRequestWaiver}
                  />
                ))}
              </div>
            </AccordionContent>
          </AccordionItem>
        )}

        {/* Passed rules */}
        {passedFindings.length > 0 && (
          <AccordionItem value="passed" className="border border-slate-800 rounded-lg">
            <AccordionTrigger className="px-4 hover:no-underline">
              <span className="text-green-400 font-medium">
                Passed ({passedFindings.length})
              </span>
            </AccordionTrigger>
            <AccordionContent className="px-4">
              <div className="space-y-2">
                {passedFindings.map((finding) => (
                  <div
                    key={finding.rule_id}
                    className="flex items-center gap-2 py-2"
                  >
                    <CheckCircle className="w-4 h-4 text-green-500 shrink-0" />
                    <span className="text-sm text-slate-300">{finding.title}</span>
                  </div>
                ))}
              </div>
            </AccordionContent>
          </AccordionItem>
        )}
      </Accordion>
    </div>
  );
}

interface RuleItemProps {
  finding: Finding;
  onRequestWaiver?: (ruleIds: string[]) => void;
}

function RuleItem({ finding, onRequestWaiver }: RuleItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Parse suggested action into steps
  const steps = finding.suggested_action
    ? finding.suggested_action.split("\n").filter((s) => s.trim())
    : [];

  return (
    <div className="border border-slate-700 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-slate-800/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <XCircle className="w-4 h-4 text-red-500 shrink-0" />
          <span className="text-sm text-white font-medium">{finding.title}</span>
        </div>
        <ChevronRight
          className={cn(
            "w-4 h-4 text-slate-400 transition-transform",
            isExpanded && "rotate-90"
          )}
        />
      </button>

      {isExpanded && (
        <div className="p-3 pt-0 space-y-3">
          {/* What's missing */}
          <div>
            <p className="text-xs font-semibold text-slate-400 mb-1">
              What's missing
            </p>
            <p className="text-sm text-slate-300">{finding.description}</p>
          </div>

          {/* How to fix */}
          {steps.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-slate-400 mb-1">
                How to fix
              </p>
              <ol className="list-decimal pl-5 space-y-1">
                {steps.map((step, index) => (
                  <li key={index} className="text-sm text-slate-300">
                    {step}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-2">
            {finding.entity_refs && finding.entity_refs.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  // Navigate to /graph with the entity
                  window.location.href = `/graph?node=${finding.entity_refs![0]}`;
                }}
              >
                View documentation gap
              </Button>
            )}

            {onRequestWaiver && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRequestWaiver([finding.rule_id])}
              >
                Create waiver for this rule
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface PatchesSectionProps {
  run: PolicyRun;
}

function PatchesSection({ run }: PatchesSectionProps) {
  const patches = run.suggested_patches || [];

  if (patches.length === 0) {
    return null;
  }

  return (
    <div className="p-4 border-b border-slate-800">
      <h3 className="text-base font-semibold text-white mb-3">
        Suggested Patches ({patches.length})
      </h3>

      <div className="space-y-4">
        {patches.map((patch: any, index: number) => (
          <PatchItem key={index} patch={patch} />
        ))}
      </div>
    </div>
  );
}

interface PatchItemProps {
  patch: any;
}

function PatchItem({ patch }: PatchItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="border border-slate-700 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-slate-800/30 transition-colors"
      >
        <span className="font-mono text-xs text-slate-300">
          {patch.file_path || "Patch"}
        </span>
        <ChevronRight
          className={cn(
            "w-4 h-4 text-slate-400 transition-transform",
            isExpanded && "rotate-90"
          )}
        />
      </button>

      {isExpanded && (
        <div className="border-t border-slate-700">
          <ReactDiffViewer
            oldValue={patch.old_content || ""}
            newValue={patch.new_content || ""}
            splitView={false}
            showDiffOnly={true}
            useDarkTheme={true}
          />
          
          <div className="p-3 border-t border-slate-700">
            <Button
              size="sm"
              onClick={async () => {
                // Apply patch
                try {
                  const response = await fetch(
                    `/api/policy/patches/${patch.id}/apply`,
                    {
                      method: "POST",
                    }
                  );
                  if (response.ok) {
                    alert("Patch applied successfully");
                  }
                } catch (error) {
                  console.error("Failed to apply patch:", error);
                }
              }}
            >
              Apply patch
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

interface DocRefreshPlanSectionProps {
  run: PolicyRun;
}

function DocRefreshPlanSection({ run }: DocRefreshPlanSectionProps) {
  const docRefreshPlan = run.doc_refresh_plan as any;

  if (!docRefreshPlan || !docRefreshPlan.jobs || docRefreshPlan.jobs.length === 0) {
    return null;
  }

  return (
    <div className="p-4 border-b border-slate-800">
      <h3 className="text-base font-semibold text-white mb-3">
        Documentation updates triggered
      </h3>

      <div className="space-y-2">
        {docRefreshPlan.jobs.map((job: any, index: number) => (
          <div
            key={index}
            className="flex items-center gap-3 p-2 rounded bg-slate-800/30"
          >
            <span className="text-sm text-slate-300">{job.service_name}</span>
            
            <Badge variant="outline" className="text-xs">
              {job.refresh_type || "refresh"}
            </Badge>

            <StatusBadge status={job.status || "queued"} />
          </div>
        ))}
      </div>
    </div>
  );
}

interface StatusBadgeProps {
  status: string;
}

function StatusBadge({ status }: StatusBadgeProps) {
  const normalizedStatus = status.toLowerCase();
  
  let bgColor = "bg-slate-500";
  let textColor = "text-white";
  
  if (normalizedStatus === "completed") {
    bgColor = "bg-green-500";
  } else if (normalizedStatus === "running") {
    bgColor = "bg-blue-500";
  } else if (normalizedStatus === "failed") {
    bgColor = "bg-red-500";
  } else if (normalizedStatus === "queued") {
    bgColor = "bg-amber-500";
  }

  return (
    <span
      className={cn(
        "text-xs px-2 py-0.5 rounded font-medium",
        bgColor,
        textColor
      )}
    >
      {normalizedStatus}
    </span>
  );
}

interface WaiverSectionProps {
  run: PolicyRun;
  onRequestWaiver?: (ruleIds: string[]) => void;
}

function WaiverSection({ run, onRequestWaiver }: WaiverSectionProps) {
  const waiver = run.merge_gate?.waiver as any;
  const outcome = run.summary_status.toLowerCase();
  const showRequestButton = !waiver && (outcome === "block" || outcome === "warn");

  const [isJustificationExpanded, setIsJustificationExpanded] = useState(false);

  if (!waiver && !showRequestButton) {
    return null;
  }

  return (
    <div className="p-4">
      <h3 className="text-base font-semibold text-white mb-3">Waiver</h3>

      {waiver ? (
        <div className="border border-slate-700 rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Badge className="bg-amber-500 text-white">Applied</Badge>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-slate-400 text-xs mb-1">Requested by</p>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded-full bg-blue-500 flex items-center justify-center text-white text-xs font-bold">
                  {getInitials(waiver.requested_by)}
                </div>
                <span className="text-slate-300">{waiver.requested_by}</span>
              </div>
            </div>

            <div>
              <p className="text-slate-400 text-xs mb-1">Approved by</p>
              <div className="flex items-center gap-2">
                {waiver.approved_by ? (
                  <>
                    <div className="w-6 h-6 rounded-full bg-green-500 flex items-center justify-center text-white text-xs font-bold">
                      {getInitials(waiver.approved_by)}
                    </div>
                    <span className="text-slate-300">{waiver.approved_by}</span>
                  </>
                ) : (
                  <Badge variant="outline">Pending approval</Badge>
                )}
              </div>
            </div>
          </div>

          <div>
            <p className="text-slate-400 text-xs mb-1">Rules bypassed</p>
            <p className="text-sm text-slate-300">
              {waiver.rule_ids?.join(", ") || "N/A"}
            </p>
          </div>

          {waiver.expires_at && (
            <div>
              <p className="text-slate-400 text-xs mb-1">Expires</p>
              <p
                className={cn(
                  "text-sm",
                  isExpiringWithin7Days(waiver.expires_at)
                    ? "text-red-500"
                    : "text-slate-300"
                )}
              >
                {formatRelativeTime(waiver.expires_at)}
              </p>
            </div>
          )}

          {waiver.justification && (
            <div>
              <button
                type="button"
                onClick={() => setIsJustificationExpanded(!isJustificationExpanded)}
                className="text-slate-400 text-xs mb-1 hover:text-slate-300 flex items-center gap-1"
              >
                Justification
                <ChevronRight
                  className={cn(
                    "w-3 h-3 transition-transform",
                    isJustificationExpanded && "rotate-90"
                  )}
                />
              </button>
              {isJustificationExpanded && (
                <p className="text-sm text-slate-300 mt-2">
                  {waiver.justification}
                </p>
              )}
            </div>
          )}
        </div>
      ) : (
        showRequestButton &&
        onRequestWaiver && (
          <Button
            onClick={() => {
              const blockingRuleIds = run.merge_gate?.blocking_rule_ids || [];
              onRequestWaiver(blockingRuleIds);
            }}
          >
            Request a waiver
          </Button>
        )
      )}
    </div>
  );
}

// Helper functions

function extractBranchName(run: PolicyRun): string | null {
  const runAny = run as any;
  
  if (runAny.branch) return runAny.branch;
  if (runAny.branch_name) return runAny.branch_name;
  if (runAny.ref) {
    const match = runAny.ref.match(/refs\/heads\/(.+)/);
    if (match) return match[1];
    return runAny.ref;
  }
  
  if (runAny.idempotency_key) {
    const parts = runAny.idempotency_key.split(":");
    if (parts.length > 2) return parts[2];
  }
  
  return null;
}

function getInitials(name: string): string {
  const parts = name.split(" ");
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.substring(0, 2).toUpperCase();
}

function isExpiringWithin7Days(expiresAt: string): boolean {
  const expiryDate = new Date(expiresAt);
  const now = new Date();
  const diffInDays = (expiryDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24);
  return diffInDays <= 7 && diffInDays > 0;
}
