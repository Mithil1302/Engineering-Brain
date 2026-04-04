"use client";
import { useState } from "react";
import { useSession } from "@/store/session";
import { MessageSquare, Plus, History, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { EmptyState } from "@/components/chat/EmptyState";

export default function QAPage() {
  const { activeRepo } = useSession();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [messages, setMessages] = useState<any[]>([]);

  const handleSend = (question: string) => {
    // TODO: Implement in task 2.2
    console.log("Sending:", question);
  };

  const handleNewChat = () => {
    setMessages([]);
  };

  const handleToggleHistory = () => {
    setHistoryOpen(!historyOpen);
  };

  return (
    <div className="h-screen flex flex-col relative min-w-[1280px]">
      {/* Header */}
      <header className="shrink-0 h-16 border-b border-slate-700/50 px-6 flex items-center justify-between bg-[#09090b]">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-slate-800 border border-slate-700 flex items-center justify-center">
            <MessageSquare className="w-4 h-4 text-white" />
          </div>
          <div>
            <h1 className="text-sm md:text-base font-semibold text-white">Q&A Chat Interface</h1>
            {activeRepo && (
              <p className="text-xs md:text-sm text-slate-500">Scoped to {activeRepo}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleNewChat}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            New chat
          </button>
          <button
            type="button"
            onClick={handleToggleHistory}
            className="flex items-center gap-2 px-3 py-1.5 text-sm text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
          >
            <History className="w-4 h-4" />
            History
          </button>
        </div>
      </header>

      {/* Main content area with three-panel layout */}
      <div className="flex-1 flex min-h-0 relative">
        {/* History sidebar - 320px, closed by default, 300ms transition */}
        {/* Below 1400px: absolute overlay (z-50), Above 1400px: relative push */}
        <aside
          className={cn(
            "w-80 border-r border-slate-700/50 bg-[#09090b] flex flex-col transition-transform duration-300",
            // Below 1400px: absolute positioning (overlay with z-50)
            "absolute left-0 top-0 h-full z-50",
            // Above 1400px: relative positioning (push content)
            "[@media(min-width:1400px)]:relative [@media(min-width:1400px)]:z-auto",
            // Visibility control
            historyOpen
              ? "translate-x-0"
              : "-translate-x-full [@media(min-width:1400px)]:hidden"
          )}
        >
          <div className="p-4 border-b border-slate-700/50 flex items-center justify-between">
            <h2 className="text-sm md:text-base font-semibold text-white">History</h2>
            <button
              type="button"
              onClick={() => setHistoryOpen(false)}
              className="[@media(max-width:1399px)]:block [@media(min-width:1400px)]:hidden text-slate-400 hover:text-white"
              aria-label="Close history sidebar"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            <p className="text-sm md:text-base text-slate-500 text-center mt-8">
              No conversation history yet
            </p>
          </div>
        </aside>

        {/* Message thread - flexible width */}
        <main className="flex-1 flex flex-col min-w-0">
          {messages.length === 0 ? (
            <EmptyState onSend={handleSend} />
          ) : (
            <div className="flex-1 overflow-y-auto p-6">
              {/* MessageThread component will go here in task 2.3 */}
              <p className="text-slate-400">Messages will appear here</p>
            </div>
          )}

          {/* Chat input - bottom fixed */}
          <div className="shrink-0 border-t border-slate-700/50 p-4 bg-[#09090b]">
            {/* ChatInput component will go here in task 2.4 */}
            <div className="max-w-4xl mx-auto">
              <textarea
                placeholder="Type your question..."
                className="w-full px-4 py-3 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 resize-none focus:outline-none focus:border-slate-600"
                rows={1}
              />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
