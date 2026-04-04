"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Command } from "cmdk";
import { MessageSquare, GitBranch, BarChart3, Shield, Layers, GraduationCap, Search } from "lucide-react";
import { useSession } from "@/store/session";

const PAGES = [
  { href: "/chat", label: "Q&A Assistant", icon: MessageSquare },
  { href: "/graph", label: "Knowledge Graph", icon: GitBranch },
  { href: "/health", label: "System Health", icon: BarChart3 },
  { href: "/policy", label: "CI/CD Policy", icon: Shield },
  { href: "/architecture", label: "Architecture", icon: Layers },
  { href: "/onboarding", label: "Onboarding", icon: GraduationCap },
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const router = useRouter();
  const { setActiveRepo } = useSession();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function navigate(href: string) {
    router.push(href);
    setOpen(false);
    setQuery("");
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[15vh]">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setOpen(false)} />
      <div className="relative w-full max-w-xl glass rounded-2xl border border-slate-700 shadow-2xl overflow-hidden">
        <Command className="bg-transparent" shouldFilter>
          <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-700/50">
            <Search className="w-4 h-4 text-slate-400 shrink-0" />
            <Command.Input
              value={query}
              onValueChange={setQuery}
              placeholder="Navigate, switch repo, or ask a question..."
              className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 focus:outline-none"
              autoFocus
            />
            <kbd className="text-[10px] text-slate-500 bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700">ESC</kbd>
          </div>
          <Command.List className="max-h-80 overflow-y-auto p-2">
            <Command.Empty className="py-8 text-center text-sm text-slate-500">No results found.</Command.Empty>

            <Command.Group heading={<span className="text-[10px] text-slate-500 uppercase tracking-wider px-2">Navigate</span>}>
              {PAGES.map(({ href, label, icon: Icon }) => (
                <Command.Item
                  key={href}
                  value={label}
                  onSelect={() => navigate(href)}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-300 hover:text-white cursor-pointer data-[selected=true]:bg-slate-800 data-[selected=true]:text-white transition-colors"
                >
                  <Icon className="w-4 h-4 text-slate-500" />
                  {label}
                </Command.Item>
              ))}
            </Command.Group>

            {query && (
              <Command.Group heading={<span className="text-[10px] text-slate-500 uppercase tracking-wider px-2">Actions</span>}>
                <Command.Item
                  value={`ask: ${query}`}
                  onSelect={() => { navigate(`/chat?q=${encodeURIComponent(query)}`); }}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-300 hover:text-white cursor-pointer data-[selected=true]:bg-slate-800 data-[selected=true]:text-white"
                >
                  <MessageSquare className="w-4 h-4 text-indigo-400" />
                  Ask: &quot;{query}&quot;
                </Command.Item>
                <Command.Item
                  value={`repo: ${query}`}
                  onSelect={() => { setActiveRepo(query); setOpen(false); }}
                  className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-300 hover:text-white cursor-pointer data-[selected=true]:bg-slate-800 data-[selected=true]:text-white"
                >
                  <GitBranch className="w-4 h-4 text-emerald-400" />
                  Switch repo to &quot;{query}&quot;
                </Command.Item>
              </Command.Group>
            )}
          </Command.List>
          <div className="px-4 py-2 border-t border-slate-700/50 flex items-center gap-4 text-[10px] text-slate-500">
            <span><kbd className="bg-slate-800 px-1 rounded border border-slate-700">↑↓</kbd> navigate</span>
            <span><kbd className="bg-slate-800 px-1 rounded border border-slate-700">↵</kbd> select</span>
            <span><kbd className="bg-slate-800 px-1 rounded border border-slate-700">⌘K</kbd> toggle</span>
          </div>
        </Command>
      </div>
    </div>
  );
}
