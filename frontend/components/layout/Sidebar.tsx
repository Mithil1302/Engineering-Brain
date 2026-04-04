"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  MessageSquare, GitBranch, BarChart3, Shield, Layers, GraduationCap,
  Zap, Bell, Settings, LogOut, ChevronDown, Search, AlertTriangle
} from "lucide-react";
import { cn, healthColor, gradeColor } from "@/lib/utils";
import { useSession } from "@/store/session";
import { policyApi } from "@/lib/api";
import { Input } from "@/components/ui/input";

const NAV = [
  { href: "/chat", label: "Q&A Assistant", icon: MessageSquare, desc: "Ask anything" },
  { href: "/graph", label: "Knowledge Graph", icon: GitBranch, desc: "Service map" },
  { href: "/health", label: "System Health", icon: BarChart3, desc: "Dashboard" },
  { href: "/policy", label: "CI/CD Policy", icon: Shield, desc: "PR checks" },
  { href: "/architecture", label: "Architecture", icon: Layers, desc: "Blueprints" },
  { href: "/onboarding", label: "Onboarding", icon: GraduationCap, desc: "Learning paths" },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, activeRepo, setActiveRepo, logout, authHeaders } = useSession();
  const [repoInput, setRepoInput] = useState(activeRepo);
  const [showRepoDropdown, setShowRepoDropdown] = useState(false);
  const [notifications, setNotifications] = useState<string[]>([]);

  // Fetch health score for sidebar indicator
  const { data: healthData } = useQuery({
    queryKey: ["sidebar-health", activeRepo],
    queryFn: () => activeRepo
      ? policyApi.healthSnapshots(activeRepo, { limit: "1" }, authHeaders())
      : null,
    enabled: !!activeRepo,
    refetchInterval: 30000,
    retry: false,
  });

  // Fetch alerts
  const { data: alertsData } = useQuery({
    queryKey: ["sidebar-alerts", activeRepo],
    queryFn: () => activeRepo
      ? policyApi.emitRetryAlerts(activeRepo, authHeaders())
      : null,
    enabled: !!activeRepo,
    refetchInterval: 60000,
    retry: false,
  });

  const latestHealth = (healthData as any)?.items?.[0];
  const score = latestHealth?.score ?? null;
  const grade = latestHealth?.grade ?? null;
  const hasAlerts = (alertsData as any)?.alerts
    ? Object.values((alertsData as any).alerts).some((a: any) => a?.triggered)
    : false;

  function handleRepoChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const value = e.target.value;
    if (value) {
      setActiveRepo(value);
    }
  }

  // SSE for live alerts
  useEffect(() => {
    if (!activeRepo) return;
    // Polling fallback since SSE requires backend support
    const interval = setInterval(async () => {
      try {
        const data = await policyApi.emitRetryAlerts(activeRepo, authHeaders());
        const triggered = Object.entries((data as any)?.alerts || {})
          .filter(([, v]: any) => v?.triggered)
          .map(([k]) => k);
        if (triggered.length > 0) {
          setNotifications(triggered);
        }
      } catch {}
    }, 30000);
    return () => clearInterval(interval);
  }, [activeRepo]);

  return (
    <aside className="w-60 shrink-0 flex flex-col h-screen bg-[#0c0c0e] border-r border-slate-800 z-20">
      {/* Logo */}
      <div className="p-4 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
            <Zap className="w-5 h-5 text-slate-900" />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-100 tracking-tight">KA-CHOW</div>
            <div className="text-[10px] text-slate-500 font-medium tracking-wider uppercase">Engineering Brain</div>
          </div>
        </div>
      </div>

      {/* Repo Selector */}
      <div className="p-3 border-b border-slate-700/50">
        <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 font-medium">Repository</div>
        <div className="relative">
          <select
            value={activeRepo || ""}
            onChange={handleRepoChange}
            aria-label="Select repository"
            className="w-full bg-[#09090b] border border-slate-800 rounded-md text-xs text-slate-200 px-3 py-1.5 focus:outline-none focus:border-slate-600 appearance-none"
          >
            <option value="" disabled>Select a repository...</option>
            {user?.repo_scope?.map(repo => (
              <option key={repo} value={repo}>{repo}</option>
            ))}
          </select>
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500 pointer-events-none" />
        </div>
        {activeRepo && (
          <div className="mt-1.5 flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[11px] text-slate-400 truncate">{activeRepo}</span>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon, desc }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md transition-colors group",
                active
                  ? "bg-slate-800/80 text-slate-100"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40"
              )}
            >
              <Icon className={cn("w-4 h-4 shrink-0", active ? "text-slate-200" : "text-slate-500 group-hover:text-slate-400")} />
              <div className="min-w-0">
                <div className="text-sm font-medium leading-tight">{label}</div>
                <div className="text-[10px] text-slate-500 leading-tight">{desc}</div>
              </div>
              {href === "/policy" && hasAlerts && (
                <div className="ml-auto w-2 h-2 rounded-full bg-red-400 animate-pulse shrink-0" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Health Score Indicator */}
      <div className="p-3 border-t border-slate-700/50">
        {score !== null ? (
          <div className="glass rounded-xl p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] text-slate-500 uppercase tracking-wider font-medium">System Health</span>
              <span className={cn("text-[10px] font-bold px-1.5 py-0.5 rounded border", gradeColor(grade))}>
                {grade}
              </span>
            </div>
            <div className="flex items-end gap-1">
              <span className="text-2xl font-bold" style={{ color: healthColor(score) }}>
                {score.toFixed(0)}
              </span>
              <span className="text-slate-500 text-xs mb-0.5">/100</span>
            </div>
            <div className="mt-2 h-1.5 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${score}%`, backgroundColor: healthColor(score) }}
              />
            </div>
            {score < 60 && (
              <div className="mt-2 flex items-center gap-1.5 text-[10px] text-red-400">
                <AlertTriangle className="w-3 h-3" />
                Health critical
              </div>
            )}
          </div>
        ) : (
          <div className="glass rounded-xl p-3 text-center">
            <div className="text-[10px] text-slate-500">Select a repo to see health</div>
          </div>
        )}

        {/* Notifications */}
        {notifications.length > 0 && (
          <div className="mt-2 flex items-center gap-2 px-2 py-1.5 bg-red-500/10 border border-red-500/20 rounded-lg">
            <Bell className="w-3.5 h-3.5 text-red-400 shrink-0" />
            <span className="text-[10px] text-red-300">{notifications.length} active alert{notifications.length > 1 ? "s" : ""}</span>
          </div>
        )}

        {/* User */}
        {user && (
          <div className="mt-2 flex items-center gap-2 px-2 py-1.5">
            <div className="w-6 h-6 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-[10px] font-medium text-slate-300 shrink-0">
              {user.subject[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[11px] text-slate-200 font-medium truncate">{user.subject}</div>
              <div className="text-[10px] text-slate-500 capitalize">{user.role}</div>
            </div>
            <button onClick={() => { logout(); router.push("/login"); }} aria-label="Log out" className="text-slate-500 hover:text-red-400 transition-colors">
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
