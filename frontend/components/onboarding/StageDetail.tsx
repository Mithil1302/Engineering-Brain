"use client";

import { OnboardingStage, OnboardingRole } from "@/lib/types";
import { File, Book, FileText, CheckCircle, ExternalLink } from "lucide-react";
import { cn, getHealthColor } from "@/lib/utils";
import Link from "next/link";
import { useState } from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown } from "lucide-react";

interface StageDetailProps {
  stage: OnboardingStage;
  userRole: OnboardingRole;
  activeRepo: string;
  onMarkComplete?: () => void;
  isCurrentStage: boolean;
}

export function StageDetail({
  stage,
  userRole,
  activeRepo,
  onMarkComplete,
  isCurrentStage,
}: StageDetailProps) {
  const resources = stage.resources || [];
  const [readResources, setReadResources] = useState<Set<string>>(new Set());

  const handleResourceCheck = (resourceTitle: string) => {
    setReadResources((prev) => {
      const next = new Set(prev);
      if (next.has(resourceTitle)) {
        next.delete(resourceTitle);
      } else {
        next.add(resourceTitle);
      }
      return next;
    });
  };

  const readCount = readResources.size;
  const totalCount = resources.length;

  return (
    <div className="space-y-6 p-6 bg-slate-800/30 rounded-2xl border border-slate-700">
      {/* Documentation Resources */}
      {resources.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-white mb-4">
            Documentation Resources
          </h3>
          <div className="space-y-3">
            {resources.map((resource, index) => {
              const isRead = readResources.has(resource.title);
              const Icon =
                resource.type === "code"
                  ? File
                  : resource.type === "adr"
                  ? FileText
                  : Book;
              const iconColor =
                resource.type === "code"
                  ? "text-sky-400"
                  : resource.type === "adr"
                  ? "text-purple-400"
                  : "text-emerald-400";

              return (
                <div
                  key={index}
                  className="flex items-start gap-4 p-4 rounded-xl bg-slate-800/50 border border-slate-700/40"
                >
                  <Icon className={cn("w-5 h-5 shrink-0 mt-0.5", iconColor)} />
                  <div className="flex-1 min-w-0">
                    <h4 className="font-semibold text-white mb-1">
                      {resource.title}
                    </h4>
                    {resource.service_name && (
                      <p className="text-xs text-muted mb-1">
                        {activeRepo} / {resource.service_name}
                      </p>
                    )}
                    {resource.description && (
                      <p className="text-sm text-slate-400 mb-2">
                        {resource.description}
                      </p>
                    )}
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-muted">~5 min read</span>
                      <Link
                        href={`/qa?q=${encodeURIComponent(
                          `Explain ${resource.title} and why it matters for a ${userRole} on the ${activeRepo} team`
                        )}`}
                        className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                      >
                        Ask about this
                      </Link>
                    </div>
                  </div>
                  <button
                    onClick={() => handleResourceCheck(resource.title)}
                    className={cn(
                      "w-5 h-5 rounded border-2 flex items-center justify-center shrink-0 transition-colors",
                      isRead
                        ? "bg-green-500 border-green-500"
                        : "border-slate-600 hover:border-slate-500"
                    )}
                  >
                    {isRead && <CheckCircle className="w-4 h-4 text-white" />}
                  </button>
                </div>
              );
            })}
          </div>
          <div className="mt-4 text-sm text-muted">
            {readCount} of {totalCount} read
          </div>
        </div>
      )}

      {/* Key Services Section - Mock data for now */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-4">Key Services</h3>
        <div className="grid grid-cols-2 gap-4">
          {/* Placeholder service cards */}
          <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/40">
            <h4 className="font-semibold text-white mb-2">Example Service</h4>
            <p className="text-sm text-slate-400 mb-3 truncate">
              Core service for this stage
            </p>
            <div className="flex items-center gap-2 mb-3">
              <span
                className="px-2 py-0.5 rounded text-xs font-bold"
                style={{
                  backgroundColor: `${getHealthColor(85)}20`,
                  color: getHealthColor(85),
                }}
              >
                85
              </span>
            </div>
            <div className="flex gap-2">
              <Link
                href={`/graph?selectedNodeId=example-service`}
                className="text-xs text-blue-400 hover:text-blue-300"
              >
                View in graph
              </Link>
              <Link
                href={`/qa?q=${encodeURIComponent(
                  `What does the example service do and how does it relate to my work as a ${userRole}?`
                )}`}
                className="text-xs text-blue-400 hover:text-blue-300"
              >
                Ask about this
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Relevant ADRs Section - Mock data */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-4">Relevant ADRs</h3>
        <div className="space-y-3">
          <Collapsible>
            <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/40">
              <div className="flex items-start gap-3 mb-2">
                <span className="px-2 py-0.5 rounded bg-slate-700 text-xs font-mono">
                  ADR-001
                </span>
                <div className="flex-1">
                  <h4 className="font-semibold text-white mb-1">
                    Example Architecture Decision
                  </h4>
                  <span className="px-2 py-0.5 rounded text-xs bg-green-500/10 text-green-500">
                    accepted
                  </span>
                </div>
              </div>
              <p className="text-sm text-muted mb-2">
                Why this matters for you: This decision impacts how you work
                with the system.
              </p>
              <CollapsibleTrigger className="flex items-center gap-2 text-xs text-blue-400 hover:text-blue-300">
                <span>View details</span>
                <ChevronDown className="w-3 h-3" />
              </CollapsibleTrigger>
              <CollapsibleContent className="mt-3 pt-3 border-t border-slate-700/40">
                <p className="text-sm text-slate-400 mb-2">
                  Decision summary and consequences would appear here.
                </p>
              </CollapsibleContent>
            </div>
          </Collapsible>
        </div>
      </div>

      {/* Starter Task Section - Mock data */}
      <div>
        <h3 className="text-lg font-semibold text-white mb-4">Starter Task</h3>
        <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/40">
          <div className="flex items-start gap-3 mb-3">
            <h4 className="text-lg font-semibold text-white flex-1">
              #123: Example starter task
            </h4>
            <span className="px-2 py-0.5 rounded text-xs bg-green-500 text-white">
              Good first issue
            </span>
          </div>
          <p className="text-sm text-slate-400 mb-3 line-clamp-3">
            This is an example starter task description that would help you get
            familiar with the codebase...
          </p>
          <div className="flex flex-wrap gap-2 mb-3">
            <span className="px-2 py-0.5 rounded-full bg-slate-700 text-xs">
              backend
            </span>
            <span className="px-2 py-0.5 rounded-full bg-slate-700 text-xs">
              api
            </span>
          </div>
          <div className="flex gap-3">
            <a
              href="#"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-blue-400 hover:text-blue-300 flex items-center gap-1"
            >
              <ExternalLink className="w-4 h-4" />
              Open issue
            </a>
            <Link
              href={`/qa?q=${encodeURIComponent(
                `Give me full context on issue #123 in ${activeRepo}. What do I need to understand to work on this as a ${userRole}? What services are involved?`
              )}`}
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              Get context
            </Link>
          </div>
        </div>
      </div>

      {/* Mark Complete Button */}
      {isCurrentStage && !stage.completed && onMarkComplete && (
        <button
          onClick={onMarkComplete}
          className="w-full py-3 rounded-xl text-sm font-semibold text-white bg-green-600 hover:bg-green-500 transition-colors flex items-center justify-center gap-2"
        >
          <CheckCircle className="w-5 h-5" />
          Mark this stage complete
        </button>
      )}
    </div>
  );
}
