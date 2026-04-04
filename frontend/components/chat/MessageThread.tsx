"use client";
import { ChainStepInfo, ChatMessage, Citation } from "@/lib/types";
import { cn, healthColor } from "@/lib/utils";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChevronDown, ChevronUp, FileText, Code, BookOpen } from "lucide-react";

export function MessageThread({
  messages,
  onFollowUp,
}: {
  messages: ChatMessage[];
  onFollowUp: (q: string) => void;
}) {
  return (
    <div className="space-y-6 max-w-4xl mx-auto w-full">
      {messages.map((msg) =>
        msg.role === "user" ? (
          <UserMessage key={msg.id} message={msg} />
        ) : (
          <AssistantMessage key={msg.id} message={msg} onFollowUp={onFollowUp} />
        )
      )}
    </div>
  );
}

function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-lg px-4 py-3 bg-indigo-600/80 border border-indigo-500/40 rounded-2xl rounded-tr-sm text-sm text-white">
        {message.content}
      </div>
    </div>
  );
}

function AssistantMessage({
  message,
  onFollowUp,
}: {
  message: ChatMessage;
  onFollowUp: (q: string) => void;
}) {
  const [showCitations, setShowCitations] = useState(false);
  const [showReasoning, setShowReasoning] = useState(false);

  return (
    <div className="flex gap-3">
      {/* Avatar */}
      <div className="w-7 h-7 shrink-0 mt-0.5 rounded-lg bg-gradient-to-br from-indigo-500 to-sky-400 flex items-center justify-center shadow">
        <span className="text-[10px] font-bold text-white">AI</span>
      </div>

      <div className="flex-1 min-w-0 space-y-3">
        {/* Intent badge */}
        {message.intent && (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-500/15 border border-indigo-500/25 text-[10px] font-mono text-indigo-300">
              {message.intent}
            </span>
            {message.sub_intent && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-sky-500/15 border border-sky-500/25 text-[10px] font-mono text-sky-300">
                {message.sub_intent}
              </span>
            )}
          </div>
        )}

        {/* Answer */}
        <div className={cn(
          "glass rounded-2xl rounded-tl-sm p-4 text-sm text-slate-200",
          message.streaming && "cursor-blink"
        )}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              code({ className, children, ...props }) {
                const isBlock = className && className.startsWith("language-");
                return isBlock ? (
                  <code className="block bg-slate-900/70 rounded-lg p-3 text-xs font-mono my-2 overflow-x-auto text-slate-300 border border-slate-700/50" {...props}>
                    {children}
                  </code>
                ) : (
                  <code className="bg-slate-800 rounded px-1 py-0.5 text-sky-300 text-[11px] font-mono" {...props}>
                    {children}
                  </code>
                );
              },
              p({ children }) { return <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>; },
              ul({ children }) { return <ul className="list-disc list-inside space-y-1 mb-2 text-slate-300">{children}</ul>; },
              li({ children }) { return <li className="text-sm">{children}</li>; },
            }}
          >
            {message.content || (message.streaming ? " " : "No response.")}
          </ReactMarkdown>
        </div>

        {/* Bottom panels — only after streaming */}
        {!message.streaming && (
          <>
            {/* Confidence + Source breakdown */}
            {message.confidence !== undefined && (
              <div className="flex items-center gap-4 px-1">
                <div className="flex items-center gap-2 flex-1">
                  <span className="text-[10px] text-slate-500 shrink-0">Confidence</span>
                  <div className="flex-1 h-1 bg-slate-700 rounded-full">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${(message.confidence * 100).toFixed(0)}%`,
                        backgroundColor: healthColor(message.confidence * 100),
                      }}
                    />
                  </div>
                  <span className="text-[10px] text-slate-400">{(message.confidence * 100).toFixed(0)}%</span>
                </div>
                {message.source_breakdown && (
                  <div className="flex items-center gap-2 shrink-0">
                    {Object.entries(message.source_breakdown)
                      .filter(([, count]) => (count || 0) > 0)
                      .slice(0, 4)
                      .map(([sourceType, count]) => (
                        <span key={sourceType} className="flex items-center gap-1 text-[10px] text-slate-400">
                          {(sourceType.toLowerCase().includes("code") || sourceType.toLowerCase().includes("graph")) ? (
                            <Code className="w-3 h-3" />
                          ) : (
                            <BookOpen className="w-3 h-3" />
                          )}
                          {sourceType}:{count}
                        </span>
                      ))}
                  </div>
                )}
              </div>
            )}

            {/* Citations */}
            {((message.citations && message.citations.length > 0) || (message.source_citations && message.source_citations.length > 0)) && (
              <div>
                <button
                  onClick={() => setShowCitations(!showCitations)}
                  className="flex items-center gap-1.5 text-[11px] text-slate-400 hover:text-white transition-colors"
                >
                  <FileText className="w-3 h-3" />
                  {((message.source_citations?.length || 0) + (message.citations?.length || 0))} citation{((message.source_citations?.length || 0) + (message.citations?.length || 0)) > 1 ? "s" : ""}
                  {showCitations ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </button>
                {showCitations && (
                  <div className="mt-2 space-y-2">
                    {[...(message.source_citations || []), ...(message.citations || [])].map((c, i) => <CitationCard key={i} citation={c} />)}
                  </div>
                )}
              </div>
            )}

            {/* Reasoning chain */}
            {message.chain_steps && message.chain_steps.length > 0 && (
              <div>
                <button
                  onClick={() => setShowReasoning(!showReasoning)}
                  className="flex items-center gap-1.5 text-[11px] text-slate-500 hover:text-slate-300 transition-colors"
                >
                  Reasoning chain
                  {showReasoning ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                </button>
                {showReasoning && (
                  <ol className="mt-2 space-y-1 list-decimal list-inside">
                    {message.chain_steps.map((step, i) => (
                      <li key={i} className="text-[11px] text-slate-400">
                        {typeof step === "string"
                          ? step
                          : formatStep(step)}
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            )}

            {/* Follow-up suggestions */}
            {message.follow_up_suggestions && message.follow_up_suggestions.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {message.follow_up_suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => onFollowUp(s)}
                    className="text-[11px] px-3 py-1.5 rounded-full border border-slate-700/60 text-slate-400 hover:text-white hover:border-indigo-500/40 hover:bg-indigo-500/10 transition-all"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function formatStep(step: ChainStepInfo): string {
  const name = step.step_name || step.name || "step";
  const latency = typeof step.latency_ms === "number" ? ` · ${step.latency_ms.toFixed(0)}ms` : "";
  const tokens = typeof step.tokens === "number"
    ? ` · ${step.tokens} tok`
    : (typeof step.tokens_used === "number" ? ` · ${step.tokens_used} tok` : "");
  return `${name}${latency}${tokens}`;
}

function CitationCard({ citation }: { citation: Citation }) {
  const title = citation.source_ref || citation.reference || citation.source;
  return (
    <div className="px-3 py-2 rounded-lg bg-slate-800/50 border border-slate-700/50 text-xs">
      <div className="flex items-center justify-between mb-1">
        <span className="font-mono text-sky-300 truncate text-[11px]">{title}</span>
        {citation.line_number && (
          <span className="text-slate-500 text-[10px] shrink-0 ml-2">L{citation.line_number}</span>
        )}
      </div>
      {(citation.source_type || citation.relevance || citation.details) && (
        <p className="text-[10px] text-slate-500 mb-1">
          {[citation.source_type, citation.relevance, citation.details].filter(Boolean).join(" · ")}
        </p>
      )}
      {citation.chunk_text && (
        <p className="text-slate-400 text-[11px] line-clamp-2">{citation.chunk_text}</p>
      )}
    </div>
  );
}
