"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { architectureApi } from "@/lib/api";
import { ArchitecturePlan, ArchitectureDecision, ScaffoldArtifact } from "@/lib/types";
import { formatRelativeTime, truncate } from "@/lib/utils";
import { ReactFlow, Background, BackgroundVariant } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Layers, Plus, FileCode, Download, ChevronDown, ChevronUp, X, Loader2 } from "lucide-react";

function ServiceFlowNode({ data }: { data: { label: string; role: string; color: string } }) {
  return (
    <div className="rounded-xl border-2 px-3 py-2 min-w-[130px] shadow-lg" style={{ borderColor: data.color + "66", background: "#1e293b" }}>
      <div className="text-[10px] font-bold uppercase tracking-wider mb-0.5" style={{ color: data.color }}>Service</div>
      <div className="text-xs font-semibold text-white">{data.label}</div>
      <div className="text-[10px] text-slate-400 truncate mt-0.5">{data.role}</div>
    </div>
  );
}

const COLORS = ["#6366f1", "#38bdf8", "#a78bfa", "#10b981", "#f59e0b", "#f472b6"];

function DesignTab({ plan }: { plan: ArchitecturePlan }) {
  const services = plan.services || [];
  const nodes = services.map((s, i) => ({
    id: s.name,
    type: "serviceNode",
    position: { x: (i % 3) * 200 + 50, y: Math.floor(i / 3) * 160 + 50 },
    data: { label: s.name, role: s.role, color: COLORS[i % COLORS.length] },
  }));

  if (nodes.length === 0) {
    return <p className="text-xs text-slate-500 p-4">No service blueprints in this plan.</p>;
  }

  return (
    <div className="h-80 rounded-xl overflow-hidden border border-slate-700/50">
      <ReactFlow
        nodes={nodes}
        edges={[]}
        nodeTypes={{ serviceNode: ServiceFlowNode }}
        fitView
        style={{ background: "#0f172a" }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#1e293b" />
      </ReactFlow>
    </div>
  );
}

function RationaleTab({ plan }: { plan: ArchitecturePlan }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const decisions = plan.decisions || [];
  if (decisions.length === 0) {
    return <p className="text-xs text-slate-500 p-4">No architecture decisions recorded.</p>;
  }
  return (
    <div className="space-y-2">
      {decisions.map((d: ArchitectureDecision, i) => (
        <div key={i} className="glass rounded-xl border border-slate-700/40 overflow-hidden">
          <button
            onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
            className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
          >
            <div className="min-w-0">
              <p className="text-sm font-medium text-white truncate">{d.title}</p>
              {d.confidence !== undefined && (
                <p className="text-[10px] text-slate-500 mt-0.5">Confidence: {(d.confidence * 100).toFixed(0)}%</p>
              )}
            </div>
            {expandedIdx === i ? <ChevronUp className="w-4 h-4 text-slate-400 shrink-0" /> : <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />}
          </button>
          {expandedIdx === i && (
            <div className="px-4 pb-4 space-y-3 border-t border-slate-700/40 pt-3">
              <div>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Rationale</p>
                <p className="text-xs text-slate-300 leading-relaxed">{d.rationale}</p>
              </div>
              {d.tradeoffs && d.tradeoffs.length > 0 && (
                <div>
                  <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Tradeoffs</p>
                  <ul className="space-y-0.5">
                    {d.tradeoffs.map((t, j) => <li key={j} className="text-xs text-slate-400">• {t}</li>)}
                  </ul>
                </div>
              )}
              {d.alternatives && d.alternatives.length > 0 && (
                <div>
                  <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Alternatives Considered</p>
                  <ul className="space-y-0.5">
                    {d.alternatives.map((a, j) => <li key={j} className="text-xs text-slate-400">• {a}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ArtifactsTab({ plan }: { plan: ArchitecturePlan }) {
  const [selectedFile, setSelectedFile] = useState<ScaffoldArtifact | null>(null);
  const artifacts = plan.artifacts || [];

  const downloadAll = () => {
    const content = artifacts.map((a) => `// ${a.file_path}\n${a.content}`).join("\n\n---\n\n");
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${plan.plan_id}-artifacts.txt`;
    a.click();
  };

  if (artifacts.length === 0) {
    return <p className="text-xs text-slate-500 p-4">No scaffolding artifacts found. Generate a scaffold from this plan.</p>;
  }

  return (
    <div className="flex gap-3 h-72">
      {/* File tree */}
      <div className="w-48 shrink-0 glass rounded-xl border border-slate-700/40 overflow-hidden">
        <div className="p-2 border-b border-slate-700/40 flex items-center justify-between">
          <span className="text-[10px] text-slate-500 uppercase tracking-wider">Files</span>
          <button onClick={downloadAll} aria-label="Download all artifacts" className="text-slate-400 hover:text-white">
            <Download className="w-3 h-3" />
          </button>
        </div>
        <div className="overflow-y-auto">
          {artifacts.map((a, i) => (
            <button
              key={i}
              onClick={() => setSelectedFile(a)}
              className={`w-full text-left px-3 py-1.5 flex items-center gap-2 transition-colors ${
                selectedFile?.file_path === a.file_path ? "bg-indigo-600/20 text-indigo-300" : "text-slate-400 hover:text-white hover:bg-slate-800/50"
              }`}
            >
              <FileCode className="w-3 h-3 shrink-0" />
              <span className="text-[11px] truncate">{a.file_path.split("/").pop()}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Viewer */}
      <div className="flex-1 glass rounded-xl border border-slate-700/40 overflow-hidden">
        {selectedFile ? (
          <>
            <div className="px-3 py-2 border-b border-slate-700/40 flex items-center justify-between">
              <span className="text-[11px] font-mono text-slate-400">{selectedFile.file_path}</span>
            </div>
            <pre className="overflow-auto h-full p-3 text-xs font-mono text-slate-300 bg-slate-900/40">
              {selectedFile.content}
            </pre>
          </>
        ) : (
          <div className="h-full flex items-center justify-center">
            <p className="text-xs text-slate-500">Select a file to preview</p>
          </div>
        )}
      </div>
    </div>
  );
}

function GenerateModal({ onClose, repo }: { onClose: () => void; repo: string }) {
  const { authHeaders } = useSession();
  const qc = useQueryClient();
  const [reqText, setReqText] = useState("");
  const [domain, setDomain] = useState("");

  const { mutate, isPending } = useMutation({
    mutationFn: () => architectureApi.generatePlan({
      repo,
      requirement: { requirement_text: reqText, domain: domain || undefined, target_cloud: "generic" },
    }, authHeaders()),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["arch-plans", repo] }); onClose(); },
  });

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="glass rounded-2xl border border-slate-700/50 p-6 w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold text-white">Generate Architecture Blueprint</h3>
          <button onClick={onClose} aria-label="Close modal" className="text-slate-400 hover:text-white"><X className="w-4 h-4" /></button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Requirement (describe what to build)</label>
            <textarea
              value={reqText}
              onChange={(e) => setReqText(e.target.value)}
              rows={4}
              className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-indigo-500/50 resize-none"
              placeholder="Design a microservices architecture for a real-time notification system with 99.9% uptime…"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400 mb-1 block">Domain (optional)</label>
            <input
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-xl px-3 py-2 text-sm text-white outline-none focus:border-indigo-500/50"
              placeholder="notifications, payments, auth…"
            />
          </div>
          <button
            onClick={() => mutate()}
            disabled={isPending || reqText.length < 10}
            className="w-full py-2.5 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 transition-colors flex items-center justify-center gap-2"
          >
            {isPending && <Loader2 className="w-4 h-4 animate-spin" />}
            {isPending ? "Generating with Gemini…" : "Generate Blueprint"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ArchitecturePage() {
  const { activeRepo, authHeaders } = useSession();
  const [selectedPlan, setSelectedPlan] = useState<ArchitecturePlan | null>(null);
  const [activeTab, setActiveTab] = useState<"design" | "rationale" | "artifacts">("design");
  const [showGenModal, setShowGenModal] = useState(false);

  const { data: plansData, isLoading } = useQuery({
    queryKey: ["arch-plans", activeRepo],
    queryFn: () => architectureApi.listPlans(activeRepo!, authHeaders()),
    enabled: !!activeRepo,
  });

  const plans = ((plansData as Record<string, unknown>)?.plans || []) as ArchitecturePlan[];

  if (!activeRepo) {
    return (
      <div className="h-full flex items-center justify-center text-center p-8">
        <div>
          <Layers className="w-10 h-10 text-slate-600 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-slate-400 mb-2">No repository selected</h2>
          <p className="text-sm text-slate-500">Select a repository to view its architecture blueprints.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex min-h-0 overflow-hidden">
      {/* Left: Blueprint list */}
      <div className="w-80 shrink-0 border-r border-slate-700/50 flex flex-col min-h-0">
        <div className="p-4 border-b border-slate-700/50 glass shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-indigo-400" />
              <span className="text-sm font-semibold text-white">Blueprints</span>
            </div>
            <button
              onClick={() => setShowGenModal(true)}
              className="flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" /> New
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {isLoading ? (
            Array.from({ length: 3 }).map((_, i) => <div key={i} className="skeleton h-20 rounded-xl" />)
          ) : plans.length === 0 ? (
            <div className="p-6 text-center">
              <Layers className="w-8 h-8 text-slate-700 mx-auto mb-2" />
              <p className="text-xs text-slate-500">No blueprints yet.</p>
              <button
                onClick={() => setShowGenModal(true)}
                className="mt-3 text-xs text-indigo-400 hover:text-indigo-300 underline"
              >
                Generate your first blueprint →
              </button>
            </div>
          ) : (
            plans.map((plan) => (
              <button
                key={plan.plan_id}
                onClick={() => { setSelectedPlan(plan); setActiveTab("design"); }}
                className={`w-full text-left p-3 rounded-xl border transition-all ${
                  selectedPlan?.plan_id === plan.plan_id
                    ? "bg-indigo-600/10 border-indigo-500/30"
                    : "border-slate-700/40 hover:bg-slate-800/40 hover:border-slate-600/40"
                } glass`}
              >
                <div className="text-xs font-medium text-white mb-1 line-clamp-2">
                  {plan.requirement?.requirement_text
                    ? truncate(plan.requirement.requirement_text, 80)
                    : plan.plan_id}
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex gap-2">
                    {plan.services && (
                      <span className="text-[10px] text-slate-400">{plan.services.length} services</span>
                    )}
                    {plan.intent_tags && plan.intent_tags.length > 0 && (
                      <span className="text-[10px] text-indigo-400">{plan.intent_tags[0]}</span>
                    )}
                  </div>
                  <span className="text-[10px] text-slate-500">{formatRelativeTime(plan.produced_at)}</span>
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Right: Detail */}
      {selectedPlan ? (
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          {/* Plan header */}
          <div className="px-6 py-4 border-b border-slate-700/50 glass shrink-0">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="text-base font-bold text-white line-clamp-2">
                  {truncate(selectedPlan.requirement?.requirement_text || selectedPlan.plan_id, 120)}
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  {selectedPlan.services?.length || 0} services · {selectedPlan.decisions?.length || 0} decisions · {selectedPlan.artifacts?.length || 0} artifacts
                  · {formatRelativeTime(selectedPlan.produced_at)}
                </p>
              </div>
              <button onClick={() => setSelectedPlan(null)} aria-label="Close plan" className="text-slate-400 hover:text-white shrink-0">
                <X className="w-4 h-4" />
              </button>
            </div>
            {/* Tabs */}
            <div className="flex gap-1 mt-3 p-1 bg-slate-800/50 rounded-xl w-fit">
              {(["design", "rationale", "artifacts"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`text-xs px-3 py-1.5 rounded-lg font-medium transition-all capitalize ${
                    activeTab === tab ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-white"
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-6">
            {activeTab === "design" && <DesignTab plan={selectedPlan} />}
            {activeTab === "rationale" && <RationaleTab plan={selectedPlan} />}
            {activeTab === "artifacts" && <ArtifactsTab plan={selectedPlan} />}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center text-center">
          <div>
            <Layers className="w-8 h-8 text-slate-700 mx-auto mb-3" />
            <p className="text-sm text-slate-500">Select a blueprint to view its Design, Rationale, and Artifacts</p>
            <button onClick={() => setShowGenModal(true)} className="mt-3 text-xs text-indigo-400 hover:text-indigo-300 underline">
              Or generate a new one →
            </button>
          </div>
        </div>
      )}

      {showGenModal && <GenerateModal onClose={() => setShowGenModal(false)} repo={activeRepo} />}
    </div>
  );
}
