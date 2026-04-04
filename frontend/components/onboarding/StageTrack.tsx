"use client";

import { OnboardingStage } from "@/lib/types";
import { CheckCircle, Lock, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface StageTrackProps {
  stages: OnboardingStage[];
  currentStageIndex: number;
  onStageClick: (index: number) => void;
}

export function StageTrack({ stages, currentStageIndex, onStageClick }: StageTrackProps) {
  const completedCount = stages.filter((s) => s.completed).length;
  const totalCount = stages.length;
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  return (
    <div className="relative">
      {/* Progress line background */}
      <div className="absolute top-[50px] left-0 right-0 h-0.5 bg-gray-600 z-0" />
      
      {/* Progress line foreground */}
      <div
        className="absolute top-[50px] left-0 h-0.5 bg-green-500 z-0 transition-all duration-500"
        style={{ width: `${progressPercent}%` }}
      />

      {/* Stage cards */}
      <div className="relative flex gap-4 overflow-x-auto pb-4 z-10">
        {stages.map((stage, index) => {
          const isCompleted = stage.completed || false;
          const isCurrent = index === currentStageIndex;
          const isFuture = index > currentStageIndex;
          const isClickable = isCompleted || isCurrent;

          return (
            <div key={stage.stage_id} className="relative flex flex-col items-center">
              <button
                onClick={() => isClickable && onStageClick(index)}
                disabled={!isClickable}
                className={cn(
                  "w-[200px] h-[100px] rounded-2xl border-2 transition-all duration-300 flex flex-col items-start justify-between p-4",
                  isCompleted && "bg-green-500/10 border-green-500/20",
                  isCurrent && "bg-white border-blue-500 shadow-lg",
                  isFuture && "bg-gray-700/50 border-gray-600 opacity-60 cursor-not-allowed",
                  isClickable && "hover:scale-105"
                )}
              >
                {/* Status indicator */}
                <div className="absolute top-2 right-2">
                  {isCompleted && (
                    <CheckCircle className="w-5 h-5 text-green-500" />
                  )}
                  {isCurrent && (
                    <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
                  )}
                  {isFuture && (
                    <Lock className="w-4 h-4 text-gray-500" />
                  )}
                </div>

                {/* Stage content */}
                <div className="flex-1 w-full">
                  <h3 className={cn(
                    "text-sm font-semibold mb-1 line-clamp-2",
                    isCurrent ? "text-slate-900" : "text-white"
                  )}>
                    {stage.title}
                  </h3>
                  {!isCompleted && (
                    <div className="flex items-center gap-2 text-xs text-muted">
                      {stage.resources && (
                        <span>{stage.resources.length} resources</span>
                      )}
                      {stage.estimated_minutes && (
                        <span>• {stage.estimated_minutes}m</span>
                      )}
                    </div>
                  )}
                  {isCompleted && (
                    <p className="text-xs text-green-500">Completed</p>
                  )}
                </div>
              </button>

              {/* Active stage indicator arrow */}
              {isCurrent && (
                <ChevronDown className="absolute -bottom-4 left-1/2 -translate-x-1/2 w-6 h-6 text-blue-500 animate-bounce" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
