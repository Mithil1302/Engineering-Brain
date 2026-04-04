"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { useSession } from "@/store/session";
import { assistantApi } from "@/lib/api";
import { ChatMessage, Citation } from "@/lib/types";
import { MessageThread } from "@/components/chat/MessageThread";
import { ChatInput } from "@/components/chat/ChatInput";
import {
  MessageSquare, Layers, Shield, GraduationCap,
  GitBranch, Zap, Clock, ChevronRight
} from "lucide-react";
import { cn } from "@/lib/utils";

const STARTER_QUESTIONS: Array<{ intent: string; icon: React.ElementType; color: string; questions: string[] }> = [
  {
    intent: "Architecture",
    icon: Layers,
    color: "indigo",
    questions: [
      "What services does the auth flow depend on?",
      "How is the payment service connected to the database?",
      "Which services are at highest risk of cascading failure?",
    ],
  },
  {
    intent: "Policy",
    icon: Shield,
    color: "amber",
    questions: [
      "Why was PR #42 blocked by the policy gate?",
      "What rules are currently enforced for this repo?",
      "Which PRs have active waivers right now?",
    ],
  },
  {
    intent: "Onboarding",
    icon: GraduationCap,
    color: "emerald",
    questions: [
      "What should a new backend engineer learn first?",
      "Who owns the ingestion service?",
      "Where can I find the architecture decision records?",
    ],
  },
  {
    intent: "Impact",
    icon: GitBranch,
    color: "rose",
    questions: [
      "What happens if the graph-service goes down?",
      "Which endpoints would be affected by removing /api/v1/tickets?",
      "What is the blast radius of a database failover?",
    ],
  },
];

function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function ChatPage() {
  const { activeRepo, authHeaders } = useSession();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<Array<{ id: string; label: string; timestamp: string; messages: ChatMessage[] }>>([]);
  const conversationId = useRef<string>(generateId());
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages]);

  const sendMessage = useCallback(async (text: string, channel: "web" | "cli" = "web") => {
    if (!text.trim() || isStreaming) return;

    const userMsg: ChatMessage = {
      id: generateId(),
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };

    const assistantMsgId = generateId();
    const assistantMsg: ChatMessage = {
      id: assistantMsgId,
      role: "assistant",
      content: "",
      streaming: true,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    try {
      const response = await assistantApi.conversation(
        {
          question: text,
          repo: activeRepo || "",
          conversation_id: conversationId.current,
          history: messages.slice(-6).map((m) => ({ role: m.role, content: m.content })),
          channel, // Pass channel to API
        },
        authHeaders()
      ) as Record<string, unknown>;

      // Parse response
      const answer = (response?.answer as string) || (response?.response as string) || JSON.stringify(response);
      const citations = (response?.citations as Citation[]) || [];
      const intent = (response?.intent as string) || "";
      const confidence = (response?.confidence as number) ?? 0.8;
      const followUps = (response?.follow_up_suggestions as string[]) || [];
      const chainSteps = (response?.chain_steps as string[]) || [];

      // Simulate streaming by revealing text incrementally
      let i = 0;
      const words = answer.split(" ");
      const interval = setInterval(() => {
        i = Math.min(i + 3, words.length);
        const partialContent = words.slice(0, i).join(" ");
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantMsgId
              ? { ...m, content: partialContent, streaming: i < words.length }
              : m
          )
        );
        if (i >= words.length) {
          clearInterval(interval);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: answer,
                    streaming: false,
                    citations,
                    intent,
                    confidence,
                    follow_up_suggestions: followUps,
                    chain_steps: chainSteps,
                  }
                : m
            )
          );
          setIsStreaming(false);
        }
      }, 40);
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Failed to get a response. Check that the backend is running.";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantMsgId
            ? { ...m, content: errMsg, streaming: false }
            : m
        )
      );
      setIsStreaming(false);
    }
  }, [activeRepo, authHeaders, isStreaming, messages]);

  const stopStreaming = useCallback(() => {
    setIsStreaming(false);
  }, []);

  const saveToHistory = useCallback(() => {
    if (messages.length === 0) return;
    const label = messages.find((m) => m.role === "user")?.content.slice(0, 50) || "New conversation";
    setHistory((prev) => [
      { id: conversationId.current, label, timestamp: new Date().toISOString(), messages: [...messages] },
      ...prev.filter((h) => h.id !== conversationId.current),
    ]);
  }, [messages]);

  const loadHistory = (h: { id: string; messages: ChatMessage[] }) => {
    saveToHistory();
    conversationId.current = generateId();
    setMessages(h.messages);
    setShowHistory(false);
  };

  const newConversation = () => {
    saveToHistory();
    conversationId.current = generateId();
    setMessages([]);
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0 relative">
      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-h-0">
        {/* Header */}
        <div className="shrink-0 px-6 py-4 border-b border-slate-700/50 flex items-center justify-between glass">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center">
              <MessageSquare className="w-4 h-4 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-white">Intent-First Q&A</h1>
              <p className="text-[11px] text-slate-500">
                {activeRepo ? `Scoped to ${activeRepo}` : "Select a repo to begin"}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={newConversation}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors px-3 py-1.5 rounded-lg hover:bg-slate-800"
            >
              <Zap className="w-3.5 h-3.5" /> New chat
            </button>
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors px-3 py-1.5 rounded-lg hover:bg-slate-800"
            >
              <Clock className="w-3.5 h-3.5" /> History
            </button>
          </div>
        </div>

        {/* Thread */}
        <div ref={threadRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {isEmpty ? (
            <EmptyState onSend={sendMessage} />
          ) : (
            <MessageThread messages={messages} onFollowUp={sendMessage} />
          )}
        </div>

        {/* Input */}
        <div className="shrink-0 p-4 border-t border-slate-700/50 glass">
          <ChatInput 
            onSend={sendMessage} 
            onStop={stopStreaming}
            disabled={!activeRepo} 
            isStreaming={isStreaming}
          />
          {!activeRepo && (
            <p className="text-center text-xs text-slate-500 mt-2">
              Set a repository in the sidebar to start asking questions.
            </p>
          )}
        </div>
      </div>

      {/* History Panel */}
      <div
        className={cn(
          "absolute right-0 top-0 h-full w-72 glass border-l border-slate-700/50 flex flex-col transition-transform duration-300 z-10",
          showHistory ? "translate-x-0" : "translate-x-full"
        )}
      >
        <div className="p-4 border-b border-slate-700/50 flex items-center justify-between shrink-0">
          <span className="text-sm font-semibold text-white">Conversation History</span>
          <button onClick={() => setShowHistory(false)} aria-label="Close history panel" className="text-slate-400 hover:text-white">
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {history.length === 0 ? (
            <p className="text-xs text-slate-500 text-center mt-8">No past conversations yet.</p>
          ) : (
            history.map((h) => (
              <button
                key={h.id}
                onClick={() => loadHistory(h)}
                className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-slate-800/60 transition-colors group"
              >
                <div className="text-xs font-medium text-slate-300 truncate group-hover:text-white">{h.label}</div>
                <div className="text-[10px] text-slate-500 mt-0.5">{new Date(h.timestamp).toLocaleDateString()}</div>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function EmptyState({ onSend }: { onSend: (q: string) => void }) {
  return (
    <div className="h-full flex flex-col items-center justify-center p-6">
      <div className="w-12 h-12 rounded-2xl bg-slate-800 border border-slate-700 flex items-center justify-center mb-4">
        <MessageSquare className="w-6 h-6 text-white" />
      </div>
      <h2 className="text-xl font-bold text-white mb-1">Ask Your Engineering Brain</h2>
      <p className="text-sm text-slate-400 mb-8 text-center max-w-sm">
        Get intelligent answers about your system architecture, policies, and codebase — powered by Gemini 2.0.
      </p>
      <div className="grid grid-cols-2 gap-3 w-full max-w-2xl">
        {STARTER_QUESTIONS.map(({ intent, icon: Icon, color, questions }) => (
          <div key={intent} className="glass rounded-xl p-4 border border-slate-700/50">
            <div className="flex items-center gap-2 mb-3">
              <div className={cn(
                "w-6 h-6 rounded-md flex items-center justify-center",
                color === "indigo" && "bg-indigo-500/20",
                color === "amber" && "bg-amber-500/20",
                color === "emerald" && "bg-emerald-500/20",
                color === "rose" && "bg-rose-500/20",
              )}>
                <Icon className={cn("w-3.5 h-3.5",
                  color === "indigo" && "text-indigo-400",
                  color === "amber" && "text-amber-400",
                  color === "emerald" && "text-emerald-400",
                  color === "rose" && "text-rose-400",
                )} />
              </div>
              <span className="text-xs font-semibold text-slate-300">{intent}</span>
            </div>
            <div className="space-y-1.5">
              {questions.map((q) => (
                <button
                  key={q}
                  onClick={() => onSend(q)}
                  className="w-full text-left text-xs text-slate-400 hover:text-white hover:bg-slate-800/50 px-2 py-1.5 rounded-lg transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
