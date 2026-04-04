"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { policyApi } from "@/lib/api";
import { PolicyRun, Waiver, Finding } from "@/lib/types";
import { outcomeColor, severityColor, formatRelativeTime } from "@/lib/utils";
import { Shield, ChevronDown, ChevronUp, GitPullRequest, CheckCircle, XCircle, AlertTriangle, Clock, X } from "lucide-react";
import { FilterBar } from "@/components/policy/FilterBar";
import { WaiverManagement } from "@/components/policy/WaiverManagement";

function OutcomeBadge({ outcome }: { outcome: string }) {
  return (
    <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded-full border ${outcomeColor(outcome)}`}>
      {outcome}
    </span>
  );
}

function MergeGateBanner({ run }: { run: PolicyRun }) {
  const gate = run.merge_gate;
  if (!gate) return null;
  const isBlocked = gate.decision === "block";
  const isWaived = gate.decision === "allow_with_waiver";
  return (
    <div className={`flex items-start gap-3 px-4 py-3 rounded-xl border mb-4 ${
      isBlocked ? "bg-red-500/10 border-red-500/30" :
      isWaived ? "bg-amber-500/10 border-amber-500/30" :
      "bg-emerald-500/10 border-emerald-500/30"
    }`}>
      {isBlocked ? <XCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" /> :
       isWaived ? <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" /> :
       <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />}
      <div>
        <p className={`text-sm font-semibold ${isBlocked ? "text-red-300" : isWaived ? "text-amber-300" : "text-emerald-300"}`}>
          {isBlocked ? "PR Blocked — Cannot Merge" : isWaived ? "Allowed with Waiver" : "Clear to Merge"}
        </p>
        {isBlocked && gate.reasons && gate.reasons.length > 0 && (
          <ul className="mt-1 space-y-0.5">
            {gate.reasons.map((r, i) => <li key={i} className="text-xs text-slate-400">• {r}</li>)}
          </ul>
        )}
      </div>
    </div>
  );
}

function FindingCard({ finding }: { finding: Finding }) {
  const [expanded, setExpanded] = useState(false);
  const statusOk = finding.status === "pass" || finding.status === "ok";
  return (
    <div className={`rounded-xl border transition-all ${
      statusOk ? "border-slate-700/40 bg-slate-800/20" : "border-slate-700/60 bg-slate-800/40"
    }`}>
      <button
        type="button"
        onClick={() => !statusOk && setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-3 py-2.5 text-left"
      >
        {statusOk ? (
          <CheckCircle className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
        ) : (
          <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />
        )}
        <span className="flex-1 text-xs font-medium text-slate-200 truncate">{finding.title || finding.rule_id}</span>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border mr-2 ${severityColor(finding.severity)}`}>
          {finding.severity}
        </span>
        {!statusOk && (expanded ? <ChevronUp className="w-3 h-3 text-slate-400" /> : <ChevronDown className="w-3 h-3 text-slate-400" />)}
      </button>
      {expanded && !statusOk && (
        <div className="px-3 pb-3 space-y-2">
          <p className="text-xs text-slate-400">{finding.description}</p>
          {finding.suggested_action && (
            <div className="px-3 py-2 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
              <p className="text-[10px] text-indigo-300 font-medium mb-0.5">Suggested Action</p>
              <p className="text-xs text-slate-300">{finding.suggested_action}</p>
            </div>
          )}
          {finding.evidence && finding.evidence.length > 0 && (
            <div>
              <p className="text-[10px] text-slate-500 mb-1">Evidence</p>
              <ul className="space-y-0.5">
                {finding.evidence.map((e, i) => <li key={i} className="text-[11px] font-mono text-slate-400 truncate">• {e}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RunDetailPanel({ run, onClose }: { run: PolicyRun; onClose: () => void }) {
  const findings = run.findings || [];
  const passed = findings.filter((f) => f.status === "pass" || f.status === "ok");
  const failed = findings.filter((f) => f.status !== "pass" && f.status !== "ok");

  return (
    <div className="flex-1 flex flex-col min-w-0 h-full overflow-y-auto p-5 space-y-4">
      <div className="flex items-start justify-between gap-2 shrink-0">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <OutcomeBadge outcome={run.summary_status} />
            <span className="text-[11px] text-slate-500">{formatRelativeTime(run.produced_at)}</span>
          </div>
          <h2 className="text-base font-bold text-white">
            {run.pr_number ? `PR #${run.pr_number}` : run.repo} — {run.rule_set}
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">{run.repo}</p>
        </div>
        <button onClick={onClose} type="button" aria-label="Close run detail" className="text-slate-400 hover:text-white shrink-0 transition-colors">
          <X className="w-4 h-4" />
        </button>
      </div>

      <MergeGateBanner run={run} />

      {/* Findings */}
      {findings.length > 0 && (
        <div>
          <div className="text-xs font-semibold text-white mb-2">
            Rule Findings ({failed.length} failed, {passed.length} passed)
          </div>
          <div className="space-y-2">
            {failed.map((f, i) => <FindingCard key={i} finding={f} />)}
            {passed.map((f, i) => <FindingCard key={`p-${i}`} finding={f} />)}
          </div>
        </div>
      )}

      {/* Doc refresh plan */}
      {run.doc_refresh_plan && (
        <div className="glass rounded-xl p-3 border border-slate-700/40">
          <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1.5">Doc Refresh Plan</p>
          <pre className="text-[11px] text-slate-300 font-mono overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(run.doc_refresh_plan, null, 2)}
          </pre>
        </div>
      )}

      {/* Waiver */}
      {run.merge_gate?.waiver && (
        <div className="glass rounded-xl p-3 border border-amber-500/20 bg-amber-500/5">
          <p className="text-[10px] text-amber-400 uppercase tracking-wider mb-1.5">Waiver Applied</p>
          <pre className="text-[11px] text-slate-300 font-mono overflow-x-auto whitespace-pre-wrap">
            {JSON.stringify(run.merge_gate.waiver, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function WaiverModal({ onClose, repo }: { onClose: () => void; repo: string }) {
  const { authHeaders } = useSession();
  const qc = useQueryClient();
  const [form, setForm] = useState({ pr_number: "", rule_ids: "", justification: "" });

  const { mutate, isPending } = useMutation({
    mutationFn: (body: unknown) => policyApi.requestWaiver(body, authHeaders()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["waivers"] }); onClose(); },
  });

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="glass rounded-2xl border border-slate-700/50 p-6 w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold text-white">Request Policy Waiver</h3>
          <button onClick={onClose} type="button" aria-label="Close waiver modal" className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-slate-400 mb-1 block">PR Number</label>
            <input
              type="number"
              value={form.pr_number}
              onChange={(e) => setForm((p) => ({ ...p, pr_number: e.target.value }))}
              aria-label="PR Number"
              className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-indigo-500/50"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Rule IDs (comma-separated)</label>
            <input
              value={form.rule_ids}
              onChange={(e) => setForm((p) => ({ ...p, rule_ids: e.target.value }))}
              className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-indigo-500/50"
              placeholder="no-docs-no-merge, coverage-gate"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Justification</label>
            <textarea
              value={form.justification}
              onChange={(e) => setForm((p) => ({ ...p, justification: e.target.value }))}
              rows={3}
              className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-indigo-500/50 resize-none"
              placeholder="Why is this waiver needed?"
            />
          </div>
          <button
            type="button"
            onClick={() => mutate({ repo, pr_number: parseInt(form.pr_number), rule_ids: form.rule_ids.split(",").map((s) => s.trim()), justification: form.justification, requested_by: "current-user", requested_role: "engineer" })}
            disabled={isPending || !form.justification}
            className="w-full py-2.5 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 transition-colors"
          >
            {isPending ? "Submitting…" : "Submit Request"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PolicyPage() {
  const { activeRepo, authHeaders } = useSession();
  const [selectedRun, setSelectedRun] = useState<PolicyRun | null>(null);
  const [activeTab, setActiveTab] = useState<"runs" | "waivers">("runs");
  const [outcomeFilter, setOutcomeFilter] = useState("all");
  const [showWaiverModal, setShowWaiverModal] = useState(false);

  const { data: runsData, isLoading } = useQuery({
    queryKey: ["policy-check-runs", activeRepo, outcomeFilter],
    queryFn: () => policyApi.policyCheckRuns(
      activeRepo!,
      outcomeFilter !== "all" ? { outcome: outcomeFilter, limit: "50" } : { limit: "50" },
      authHeaders()
    ),
    enabled: !!activeRepo,
    refetchInterval: 10000,
  });

  const { data: waiversData } = useQuery({
    queryKey: ["waivers", activeRepo],
    queryFn: () => policyApi.listWaivers(activeRepo ? { repo: activeRepo } : {}, authHeaders()),
    enabled: !!activeRepo,
  });

  const runs = ((runsData as Record<string, unknown>)?.items || []) as PolicyRun[];
  const waivers = ((waiversData as Record<string, unknown>)?.items || []) as Waiver[];

  if (!activeRepo) {
    return (
      <div className="h-full flex items-center justify-center text-center p-8">
        <div>
          <Shield className="w-10 h-10 text-slate-600 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-slate-400 mb-2">No repository selected</h2>
          <p className="text-sm text-slate-500">Select a repository to view CI/CD policy runs.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full policy-grid min-h-0 overflow-hidden">
      {/* Left panel */}
      <div className="w-full policy-list-panel flex flex-col border-r border-slate-700/50 min-h-0">
        {/* Header */}
        <div className="p-4 border-b border-slate-700/50 glass shrink-0">
          <div className="flex items-center gap-2 mb-3">
            <Shield className="w-4 h-4 text-indigo-400" />
            <span className="text-sm font-semibold text-white">CI/CD Policy</span>
          </div>
          {/* Tabs */}
          <div className="flex gap-1 p-1 bg-slate-800/50 rounded-xl">
            {(["runs", "waivers"] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveTab(tab)}
                className={`flex-1 text-xs py-1.5 rounded-lg font-medium transition-all capitalize ${
                  activeTab === tab ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
          {activeTab === "waivers" && (
            <button
              type="button"
              onClick={() => setShowWaiverModal(true)}
              className="mt-2 w-full text-xs py-2 rounded-lg bg-indigo-600/20 border border-indigo-500/30 text-indigo-300 hover:bg-indigo-600/30 transition-colors"
            >
              + Request Waiver
            </button>
          )}
        </div>
        
        {/* FilterBar - only shown for runs tab */}
        {activeTab === "runs" && <FilterBar />}

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === "runs" && (
            isLoading ? (
              <div className="p-4 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton h-16 rounded-xl" />)}
              </div>
            ) : runs.length === 0 ? (
              <div className="p-8 text-center">
                <p className="text-sm text-slate-400">No policy runs found for this repository in the last 30 days.</p>
              </div>
            ) : (
              runs.map((run) => (
                <button
                  key={run.id}
                  type="button"
                  onClick={() => setSelectedRun(run)}
                  className={`w-full text-left px-4 py-3 border-b border-slate-700/30 hover:bg-slate-800/40 transition-colors ${
                    selectedRun?.id === run.id ? "bg-indigo-600/10 border-l-2 border-l-indigo-500" : ""
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <div className="flex items-center gap-2">
                      <GitPullRequest className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                      <span className="text-xs font-medium text-slate-200 truncate">
                        {run.pr_number ? `PR #${run.pr_number}` : run.idempotency_key?.slice(0, 20) || run.repo}
                      </span>
                    </div>
                    <OutcomeBadge outcome={run.summary_status} />
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-slate-500 truncate">{run.rule_set}</span>
                    <span className="text-[10px] text-slate-500 shrink-0">{formatRelativeTime(run.produced_at)}</span>
                  </div>
                </button>
              ))
            )
          )}
        </div>
      </div>

      {/* Right panel */}
      {activeTab === "runs" ? (
        selectedRun ? (
          <RunDetailPanel run={selectedRun} onClose={() => setSelectedRun(null)} />
        ) : (
          <div className="flex-1 flex items-center justify-center text-center">
            <div>
              <Clock className="w-8 h-8 text-slate-700 mx-auto mb-3" />
              <p className="text-sm text-slate-500">Select a policy run to view its details</p>
            </div>
          </div>
        )
      ) : (
        <WaiverManagement />
      )}

      {showWaiverModal && <WaiverModal onClose={() => setShowWaiverModal(false)} repo={activeRepo} />}
    </div>
  );
}
