"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { policyApi, governanceApi } from "@/lib/api";
import { Waiver } from "@/lib/types";
import { formatRelativeTime } from "@/lib/utils";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Tooltip, TooltipProvider } from "@/components/ui/tooltip";
import { Shield, Trash2, User } from "lucide-react";

/**
 * Get initials from a name (first letter of first and last name)
 */
function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0][0]?.toUpperCase() || "?";
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Avatar component displaying user initials
 */
function Avatar({ name }: { name: string }) {
  const initials = getInitials(name);
  // Deterministic color based on name hash
  const colors = [
    "bg-blue-500",
    "bg-green-500",
    "bg-amber-500",
    "bg-red-500",
    "bg-purple-500",
    "bg-pink-500",
    "bg-indigo-500",
    "bg-teal-500",
  ];
  const hash = name.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const colorClass = colors[hash % colors.length];

  return (
    <div
      className={`w-8 h-8 rounded-full ${colorClass} flex items-center justify-center text-white text-xs font-bold border-2 border-white/20`}
    >
      {initials}
    </div>
  );
}

/**
 * Check if a waiver expires within 7 days
 */
function expiresWithin7Days(expiresAt: string | undefined): boolean {
  if (!expiresAt) return false;
  const expiryDate = new Date(expiresAt);
  const now = new Date();
  const diffMs = expiryDate.getTime() - now.getTime();
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  return diffDays > 0 && diffDays <= 7;
}

/**
 * WaiverRow component displaying a single waiver in the table
 */
function WaiverRow({
  waiver,
  showRevoke,
  onRevoke,
}: {
  waiver: Waiver;
  showRevoke: boolean;
  onRevoke: (id: number) => void;
}) {
  const rulesList = waiver.rule_ids.join(", ");
  const rulesDisplay = rulesList.length > 40 ? rulesList.slice(0, 40) + "..." : rulesList;
  const showTooltip = rulesList.length > 40;
  const expiryWarning = expiresWithin7Days(waiver.expires_at);

  return (
    <tr className="border-b border-slate-700/30 hover:bg-slate-800/40 transition-colors">
      {/* Requested by */}
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <Avatar name={waiver.requested_by} />
          <span className="text-xs text-slate-200">{waiver.requested_by}</span>
        </div>
      </td>

      {/* Approved by */}
      <td className="px-4 py-3">
        {waiver.decided_by ? (
          <div className="flex items-center gap-2">
            <Avatar name={waiver.decided_by} />
            <span className="text-xs text-slate-200">{waiver.decided_by}</span>
          </div>
        ) : (
          <span className="text-[10px] px-2 py-1 rounded-full border border-amber-400/30 bg-amber-400/10 text-amber-400">
            Pending approval
          </span>
        )}
      </td>

      {/* Rules bypassed */}
      <td className="px-4 py-3">
        {showTooltip ? (
          <TooltipProvider>
            <Tooltip content={rulesList}>
              <span className="text-xs text-slate-300 font-mono cursor-help">{rulesDisplay}</span>
            </Tooltip>
          </TooltipProvider>
        ) : (
          <span className="text-xs text-slate-300 font-mono">{rulesDisplay}</span>
        )}
      </td>

      {/* Repo */}
      <td className="px-4 py-3">
        <span className="text-xs text-slate-400">{waiver.repo}</span>
      </td>

      {/* Expiry */}
      <td className="px-4 py-3">
        {waiver.expires_at ? (
          <span className={`text-xs ${expiryWarning ? "text-red-500 font-semibold" : "text-slate-400"}`}>
            {formatRelativeTime(waiver.expires_at)}
          </span>
        ) : (
          <span className="text-xs text-slate-500">—</span>
        )}
      </td>

      {/* Status */}
      <td className="px-4 py-3">
        <span
          className={`text-[10px] px-2 py-1 rounded-full border ${
            waiver.status === "approved"
              ? "text-emerald-400 border-emerald-400/30 bg-emerald-400/10"
              : waiver.status === "rejected"
              ? "text-red-400 border-red-400/30 bg-red-400/10"
              : waiver.status === "expired"
              ? "text-slate-400 border-slate-400/30 bg-slate-400/10"
              : "text-amber-400 border-amber-400/30 bg-amber-400/10"
          }`}
        >
          {waiver.status}
        </span>
      </td>

      {/* Actions */}
      {showRevoke && (
        <td className="px-4 py-3">
          <button
            type="button"
            onClick={() => onRevoke(waiver.id)}
            className="text-red-400 hover:text-red-300 transition-colors p-1.5 rounded-lg hover:bg-red-400/10"
            aria-label={`Revoke waiver ${waiver.id}`}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </td>
      )}
    </tr>
  );
}

/**
 * WaiverManagement component
 * Displays active and expired waivers in separate tabs
 * **Validates: Requirements 4.18, 4.19, 4.20**
 */
export function WaiverManagement() {
  const { activeRepo, authHeaders } = useSession();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"active" | "expired">("active");

  // Fetch all waivers
  const { data: waiversData, isLoading } = useQuery({
    queryKey: ["waivers", activeRepo],
    queryFn: () => policyApi.listWaivers(activeRepo ? { repo: activeRepo } : {}, authHeaders()),
    enabled: !!activeRepo,
  });

  const waivers = ((waiversData as Record<string, unknown>)?.items || []) as Waiver[];

  // Split waivers into active and expired
  const activeWaivers = waivers.filter((w) => w.status === "approved" || w.status === "pending");
  const expiredWaivers = waivers.filter((w) => w.status === "expired" || w.status === "rejected");

  // Revoke waiver mutation with optimistic update
  // **Validates: Property 24 (optimistic update with rollback)**
  const revokeMutation = useMutation({
    mutationFn: (waiverId: number) => governanceApi.deleteWaiver(waiverId, authHeaders()),
    onMutate: async (waiverId) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: ["waivers", activeRepo] });

      // Snapshot previous value
      const previousWaivers = queryClient.getQueryData(["waivers", activeRepo]);

      // Optimistically update to remove the waiver
      queryClient.setQueryData(["waivers", activeRepo], (old: unknown) => {
        const oldData = old as Record<string, unknown>;
        const items = (oldData?.items || []) as Waiver[];
        return {
          ...oldData,
          items: items.filter((w) => w.id !== waiverId),
        };
      });

      // Return context with previous value for rollback
      return { previousWaivers };
    },
    onError: (_error, _waiverId, context) => {
      // Rollback on error
      if (context?.previousWaivers) {
        queryClient.setQueryData(["waivers", activeRepo], context.previousWaivers);
      }
    },
    onSettled: () => {
      // Refetch after mutation completes
      queryClient.invalidateQueries({ queryKey: ["waivers", activeRepo] });
    },
  });

  const handleRevoke = (waiverId: number) => {
    if (confirm("Are you sure you want to revoke this waiver?")) {
      revokeMutation.mutate(waiverId);
    }
  };

  if (!activeRepo) {
    return (
      <div className="h-full flex items-center justify-center text-center p-8">
        <div>
          <Shield className="w-10 h-10 text-slate-600 mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-slate-400 mb-2">No repository selected</h2>
          <p className="text-sm text-slate-500">Select a repository to view waivers.</p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-16 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as "active" | "expired")} className="flex-1 flex flex-col">
        <div className="px-6 pt-6 pb-4 border-b border-slate-700/50">
          <TabsList>
            <TabsTrigger value="active">Active</TabsTrigger>
            <TabsTrigger value="expired">Expired</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="active" className="flex-1 overflow-y-auto px-6">
          {activeWaivers.length === 0 ? (
            <div className="py-12 text-center">
              <Shield className="w-10 h-10 text-slate-600 mx-auto mb-4" />
              <p className="text-sm text-slate-400">No active waivers</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700/50">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Requested by
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Approved by
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Rules bypassed
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Repo
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Expiry
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {activeWaivers.map((waiver) => (
                    <WaiverRow key={waiver.id} waiver={waiver} showRevoke={true} onRevoke={handleRevoke} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="expired" className="flex-1 overflow-y-auto px-6">
          {expiredWaivers.length === 0 ? (
            <div className="py-12 text-center">
              <Shield className="w-10 h-10 text-slate-600 mx-auto mb-4" />
              <p className="text-sm text-slate-400">No expired waivers</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700/50">
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Requested by
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Approved by
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Rules bypassed
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Repo
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Expiry
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {expiredWaivers.map((waiver) => (
                    <WaiverRow key={waiver.id} waiver={waiver} showRevoke={false} onRevoke={() => {}} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
