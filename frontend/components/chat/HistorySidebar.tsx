"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { assistantApi } from "@/lib/api";
import { Session, ChatMessage } from "@/lib/types";
import { groupSessionsByTime, formatRelativeTime, cn } from "@/lib/utils";
import { Plus, Trash2, MessageSquare, X } from "lucide-react";
import { ErrorState, MessageSkeleton } from "@/components/shared";

interface HistorySidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onNewConversation: () => void;
  onLoadSession: (messages: ChatMessage[]) => void;
}

export function HistorySidebar({
  isOpen,
  onClose,
  onNewConversation,
  onLoadSession,
}: HistorySidebarProps) {
  const { activeRepo, authHeaders } = useSession();
  const queryClient = useQueryClient();
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Fetch sessions from API
  const { data: sessions = [], isLoading, isError, error, refetch } = useQuery<Session[]>({
    queryKey: ["sessions", activeRepo],
    queryFn: () => assistantApi.sessions(activeRepo, authHeaders()) as Promise<Session[]>,
    enabled: !!activeRepo && isOpen,
  });

  // Group sessions by time
  const grouped = groupSessionsByTime(sessions);

  // Delete session mutation
  const deleteMutation = useMutation({
    mutationFn: (sessionId: string) =>
      assistantApi.deleteSession(sessionId, authHeaders()),
    onMutate: (sessionId) => {
      setDeletingId(sessionId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions", activeRepo] });
    },
    onSettled: () => {
      // Wait for fade-out animation (200ms) before clearing
      setTimeout(() => setDeletingId(null), 200);
    },
  });

  // Load session messages
  const handleSessionClick = async (sessionId: string) => {
    try {
      const messages = await assistantApi.sessionMessages(sessionId, authHeaders());
      onLoadSession(messages as ChatMessage[]);
    } catch (error) {
      console.error("Failed to load session:", error);
    }
  };

  // Handle delete with animation
  const handleDelete = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    deleteMutation.mutate(sessionId);
  };

  return (
    <div
      className={cn(
        "w-80 h-full glass border-l border-slate-700/50 flex flex-col transition-transform duration-300",
        isOpen ? "translate-x-0" : "translate-x-full"
      )}
    >
      {/* Header */}
      <div className="shrink-0 px-4 py-3 border-b border-slate-700/50 flex items-center justify-between">
        <h2 className="text-sm md:text-base font-semibold text-white">History</h2>
        <button
          type="button"
          onClick={onClose}
          className="text-slate-400 hover:text-white transition-colors"
          aria-label="Close history sidebar"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* New Conversation Button */}
      <div className="shrink-0 px-4 py-3 border-b border-slate-700/50">
        <button
          type="button"
          onClick={onNewConversation}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-sm md:text-base font-medium transition-colors shadow-md shadow-indigo-500/20"
        >
          <Plus className="w-4 h-4" />
          New conversation
        </button>
      </div>

      {/* Sessions List */}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {isLoading ? (
          <div className="space-y-2 px-2">
            {[1, 2, 3, 4, 5].map((i) => (
              <MessageSkeleton key={i} />
            ))}
          </div>
        ) : isError ? (
          <div className="px-2 py-4">
            <ErrorState 
              error={new Error(`Could not load conversation history for ${activeRepo}`)}
              onRetry={refetch}
            />
          </div>
        ) : sessions.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <MessageSquare className="w-8 h-8 text-slate-600 mx-auto mb-2" />
            <p className="text-xs md:text-sm text-slate-500">No conversations yet</p>
          </div>
        ) : (
          <>
            {grouped.today.length > 0 && (
              <SessionGroup
                title="Today"
                sessions={grouped.today}
                onSessionClick={handleSessionClick}
                onDelete={handleDelete}
                deletingId={deletingId}
              />
            )}
            {grouped.yesterday.length > 0 && (
              <SessionGroup
                title="Yesterday"
                sessions={grouped.yesterday}
                onSessionClick={handleSessionClick}
                onDelete={handleDelete}
                deletingId={deletingId}
              />
            )}
            {grouped.last7Days.length > 0 && (
              <SessionGroup
                title="This Week"
                sessions={grouped.last7Days}
                onSessionClick={handleSessionClick}
                onDelete={handleDelete}
                deletingId={deletingId}
              />
            )}
            {(grouped.last30Days.length > 0 || grouped.older.length > 0) && (
              <SessionGroup
                title="Older"
                sessions={[...grouped.last30Days, ...grouped.older]}
                onSessionClick={handleSessionClick}
                onDelete={handleDelete}
                deletingId={deletingId}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

interface SessionGroupProps {
  title: string;
  sessions: Session[];
  onSessionClick: (sessionId: string) => void;
  onDelete: (e: React.MouseEvent, sessionId: string) => void;
  deletingId: string | null;
}

function SessionGroup({
  title,
  sessions,
  onSessionClick,
  onDelete,
  deletingId,
}: SessionGroupProps) {
  return (
    <div className="mb-4">
      <h3 className="px-2 mb-1 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
        {title}
      </h3>
      <div className="space-y-0.5">
        {sessions.map((session) => (
          <SessionItem
            key={session.id}
            session={session}
            onClick={() => onSessionClick(session.id)}
            onDelete={(e) => onDelete(e, session.id)}
            isDeleting={deletingId === session.id}
          />
        ))}
      </div>
    </div>
  );
}

interface SessionItemProps {
  session: Session;
  onClick: () => void;
  onDelete: (e: React.MouseEvent) => void;
  isDeleting: boolean;
}

function SessionItem({ session, onClick, onDelete, isDeleting }: SessionItemProps) {
  // Display label or fallback to "New conversation"
  const displayLabel = session.label || "New conversation";

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full group flex items-start gap-2 px-2 py-2 rounded-lg hover:bg-slate-800/60 transition-all text-left",
        isDeleting && "opacity-0 pointer-events-none"
      )}
      style={{
        transition: isDeleting
          ? "opacity 200ms ease-out"
          : "background-color 150ms ease-out",
      }}
    >
      <MessageSquare className="w-3.5 h-3.5 text-slate-500 shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <p className="text-xs md:text-sm text-slate-300 group-hover:text-white truncate transition-colors">
          {displayLabel}
        </p>
        <p className="text-[10px] md:text-xs text-slate-500 mt-0.5">
          {formatRelativeTime(session.created_at)}
        </p>
      </div>
      <button
        type="button"
        onClick={onDelete}
        className="opacity-0 group-hover:opacity-100 shrink-0 p-1 rounded hover:bg-red-500/20 text-slate-500 hover:text-red-400 transition-all"
        aria-label="Delete session"
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </button>
  );
}
