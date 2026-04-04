"use client";
import { useState, useRef } from "react";
import { Send } from "lucide-react";
import { cn } from "@/lib/utils";

type ChannelMode = "web" | "cli" | "api" | "chat";

export function ChatInput({
  onSend,
  disabled,
}: {
  onSend: (payload: { message: string; channel: ChannelMode }) => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");
  const [channel, setChannel] = useState<ChannelMode>("web");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend({ message: trimmed, channel });
    setValue("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    const ta = e.target;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <div className="text-[10px] text-slate-500 uppercase tracking-wider">Channel mode</div>
        <div className="inline-flex p-0.5 bg-slate-800/70 border border-slate-700/50 rounded-lg">
          {(["web", "cli", "api", "chat"] as ChannelMode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setChannel(m)}
              className={cn(
                "px-2 py-1 text-[10px] rounded-md capitalize transition-colors",
                channel === m
                  ? "bg-indigo-600 text-white"
                  : "text-slate-400 hover:text-white"
              )}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div className={cn(
        "flex items-end gap-3 px-4 py-3 rounded-2xl glass border border-slate-700/50 transition-colors",
        !disabled && "focus-within:border-indigo-500/40"
      )}>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? "Select a repository to start asking…" : "Ask anything about your system… (Enter to send, Shift+Enter for newline)"}
        disabled={disabled}
        rows={1}
        className="flex-1 resize-none bg-transparent text-sm text-white placeholder-slate-500 outline-none leading-relaxed min-h-[24px] max-h-40 disabled:opacity-40"
      />
      <button
        onClick={handleSend}
        disabled={!value.trim() || disabled}
        className={cn(
          "shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all",
          value.trim() && !disabled
            ? "bg-indigo-600 hover:bg-indigo-500 shadow-md shadow-indigo-500/30 text-white"
            : "bg-slate-800 text-slate-600 cursor-not-allowed"
        )}
      >
        <Send className="w-3.5 h-3.5" />
      </button>
      </div>
    </div>
  );
}
