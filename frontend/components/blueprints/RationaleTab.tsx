"use client";

import { useState, useRef, useEffect } from "react";
import { BarChart, Users, Shield, Clock, Code } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown } from "lucide-react";
import { parseConstraintReferences } from "@/lib/utils";

interface RationaleTabProps {
  blueprint: any;
}

const CONSTRAINT_ICONS: Record<string, any> = {
  scale: BarChart,
  team_size: Users,
  compliance: Shield,
  latency: Clock,
  existing_tech: Code,
};

export function RationaleTab({ blueprint }: RationaleTabProps) {
  const [highlightedConstraint, setHighlightedConstraint] = useState<string | null>(null);
  const [pulsingConstraint, setPulsingConstraint] = useState<string | null>(null);
  const constraintRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const decisions = blueprint.decisions || [];
  
  // Extract constraints from decisions
  const constraints = decisions
    .filter((d: any) => d.constraint)
    .map((d: any, i: number) => ({
      id: `${i + 1}`,
      type: d.constraint.split(":")[0] || "scale",
      text: d.constraint,
    }));

  const handleConstraintClick = (constraintId: string) => {
    const element = constraintRefs.current[constraintId];
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "center" });
      setPulsingConstraint(constraintId);
      setTimeout(() => setPulsingConstraint(null), 600);
    }
  };

  if (decisions.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500 text-sm">
        No architecture decisions recorded
      </div>
    );
  }

  return (
    <div className="flex gap-6">
      {/* Decisions column - 65% */}
      <div className="w-[65%] space-y-4">
        {decisions.map((decision: any, i: number) => {
          const constraintRefs = parseConstraintReferences(decision.rationale || "");
          const confidenceColor =
            (decision.confidence || 0) >= 0.8
              ? "bg-green-500"
              : (decision.confidence || 0) >= 0.5
              ? "bg-amber-500"
              : "bg-red-500";

          return (
            <div
              key={i}
              className="border border-slate-700/40 rounded-xl p-4 bg-slate-800/20"
            >
              {/* Confidence badge */}
              {decision.confidence !== undefined && (
                <div className={`absolute top-2 right-2 ${confidenceColor} text-white text-xs px-2 py-1 rounded font-semibold`}>
                  {Math.round((decision.confidence || 0) * 100)}%
                </div>
              )}

              {/* Decision title */}
              <h3 className="text-lg font-semibold text-white mb-3">{decision.title}</h3>

              {/* What was decided */}
              <div className="mb-3">
                <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">
                  What was decided
                </p>
                <p className="text-sm text-slate-300">{decision.title}</p>
              </div>

              {/* Why */}
              <div className="mb-3">
                <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">Why</p>
                <p className="text-sm text-slate-300 leading-relaxed">{decision.rationale}</p>
              </div>

              {/* Constraint drivers */}
              {constraintRefs.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">
                    Constraint drivers
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {constraintRefs.map((ref) => (
                      <button
                        key={ref}
                        onClick={() => handleConstraintClick(ref)}
                        className="px-2 py-1 rounded bg-slate-700 text-xs text-slate-300 hover:bg-blue-600 hover:text-white transition-colors"
                      >
                        Constraint {ref}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Alternatives considered */}
              {decision.alternatives && decision.alternatives.length > 0 && (
                <Collapsible>
                  <CollapsibleTrigger className="flex items-center gap-2 text-xs text-slate-400 hover:text-white transition-colors">
                    <ChevronDown className="w-3 h-3" />
                    Alternatives considered
                  </CollapsibleTrigger>
                  <CollapsibleContent className="mt-2 space-y-1">
                    {decision.alternatives.map((alt: string, j: number) => (
                      <div key={j} className="text-sm text-slate-400 pl-4">
                        • {alt}
                      </div>
                    ))}
                  </CollapsibleContent>
                </Collapsible>
              )}
            </div>
          );
        })}
      </div>

      {/* Constraints sidebar - 35% */}
      <div className="w-[35%] space-y-3">
        <h3 className="text-sm font-semibold text-white mb-3">Constraints</h3>
        {constraints.map((constraint: any) => {
          const Icon = CONSTRAINT_ICONS[constraint.type] || BarChart;
          const isPulsing = pulsingConstraint === constraint.id;
          const isHighlighted = highlightedConstraint === constraint.id;

          return (
            <div
              key={constraint.id}
              ref={(el) => {
                constraintRefs.current[constraint.id] = el;
              }}
              onMouseEnter={() => setHighlightedConstraint(constraint.id)}
              onMouseLeave={() => setHighlightedConstraint(null)}
              className={`p-3 rounded-lg border transition-all ${
                isHighlighted || isPulsing
                  ? "ring-2 ring-blue-500 shadow-lg shadow-blue-500/50 border-blue-500"
                  : "border-slate-700/40 bg-slate-800/20"
              } ${isPulsing ? "animate-pulse" : ""}`}
            >
              <div className="flex items-start gap-2">
                <Icon className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                  <div className="text-xs font-mono text-slate-500 mb-1">
                    Constraint {constraint.id}
                  </div>
                  <p className="text-sm text-slate-300">{constraint.text}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
