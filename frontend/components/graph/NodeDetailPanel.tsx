"use client";
import { GraphNodeData } from "@/lib/types";
import { getNodeTypeColor, healthColor, formatRelativeTime } from "@/lib/utils";
import { X, AlertTriangle, FileText, GitBranch, Cpu, ExternalLink } from "lucide-react";

export function NodeDetailPanel({
  node,
  repo,
  onClose,
}: {
  node: GraphNodeData;
  repo: string;
  onClose: () => void;
}) {
  const nodeColor = getNodeTypeColor(node.type);
  const hColor = healthColor(node.healthScore ?? 75);
  const score = node.healthScore ?? 75;

  return (
    <div className="h-full w-full glass border-l border-slate-700/50 flex flex-col shadow-2xl overflow-hidden">
      {/* Header */}
      <div className="p-4 border-b border-slate-700/50 shrink-0" style={{ borderColor: nodeColor + "33" }}>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span
                className="text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded"
                style={{ color: nodeColor, backgroundColor: nodeColor + "20" }}
              >
                {node.type}
              </span>
              {!node.documented && (
                <span className="text-[10px] text-amber-400 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> Undocumented
                </span>
              )}
            </div>
            <h3 className="text-base font-bold text-white truncate">{node.label}</h3>
            {node.owner && <p className="text-xs text-slate-400 mt-0.5">Owned by @{node.owner}</p>}
          </div>
          <button onClick={onClose} aria-label="Close node detail panel" className="shrink-0 text-slate-400 hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Description */}
        {node.description && (
          <p className="text-xs text-slate-300 leading-relaxed">{node.description}</p>
        )}

        {/* Health Score */}
        <div className="glass rounded-xl p-3 border border-slate-700/40">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] text-slate-500 uppercase tracking-wider">Knowledge Health</span>
            <span className="text-xs font-bold" style={{ color: hColor }}>{score.toFixed(0)}/100</span>
          </div>
          <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
            <div className="h-full rounded-full transition-all" style={{ width: `${score}%`, backgroundColor: hColor }} />
          </div>
        </div>

        {/* Endpoints */}
        {node.endpoints && node.endpoints.length > 0 && (
          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <Cpu className="w-3 h-3" /> API Endpoints ({node.endpoints.length})
            </div>
            <div className="space-y-1.5">
              {node.endpoints.slice(0, 6).map((ep, i) => (
                <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-slate-800/50 border border-slate-700/40">
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded font-mono ${
                    ep.method === "GET" ? "bg-emerald-500/20 text-emerald-300" :
                    ep.method === "POST" ? "bg-sky-500/20 text-sky-300" :
                    ep.method === "PUT" ? "bg-amber-500/20 text-amber-300" :
                    "bg-red-500/20 text-red-300"
                  }`}>{ep.method}</span>
                  <span className="text-[11px] text-slate-300 font-mono truncate">{ep.path}</span>
                </div>
              ))}
              {node.endpoints.length > 6 && (
                <p className="text-[10px] text-slate-500 pl-2">+{node.endpoints.length - 6} more…</p>
              )}
            </div>
          </div>
        )}

        {/* Linked ADRs */}
        {node.linked_adrs && node.linked_adrs.length > 0 && (
          <div>
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
              <FileText className="w-3 h-3" /> Architecture Decisions
            </div>
            <div className="space-y-1">
              {node.linked_adrs.map((adr, i) => (
                <div key={i} className="text-xs text-indigo-300 hover:text-indigo-200 flex items-center gap-1.5 cursor-pointer group">
                  <GitBranch className="w-3 h-3 shrink-0" />
                  <span className="truncate">{adr}</span>
                  <ExternalLink className="w-3 h-3 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Last Updated */}
        {node.last_updated && (
          <div className="text-[10px] text-slate-500">
            Last updated {formatRelativeTime(node.last_updated)}
          </div>
        )}
      </div>

      {/* Footer actions */}
      <div className="p-3 border-t border-slate-700/50 shrink-0">
        <a
          href={`/chat?q=${encodeURIComponent(`Tell me about the ${node.label} service in ${repo}`)}`}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-xs font-medium text-white transition-all"
          style={{ backgroundColor: nodeColor + "30", border: `1px solid ${nodeColor}40` }}
        >
          Ask about {node.label}
        </a>
      </div>
    </div>
  );
}
