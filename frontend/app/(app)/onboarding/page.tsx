"use client";

import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { onboardingApi } from "@/lib/api";
import { OnboardingRole, OnboardingStage } from "@/lib/types";
import { RoleSelector } from "@/components/onboarding/RoleSelector";
import { StageTrack } from "@/components/onboarding/StageTrack";
import { StageDetail } from "@/components/onboarding/StageDetail";
import { TeammateMap } from "@/components/onboarding/TeammateMap";
import { useOnboardingData } from "@/hooks/useOnboardingData";
import { GraduationCap, Loader2, AlertCircle } from "lucide-react";
import confetti from "canvas-confetti";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import Link from "next/link";

// Skeleton components
function StageSkeleton() {
  return (
    <div className="w-[200px] h-[100px] bg-slate-800 rounded-2xl animate-pulse" />
  );
}

function StageDetailSkeleton() {
  return (
    <div className="space-y-4 p-6 bg-slate-800/30 rounded-2xl border border-slate-700">
      <div className="h-12 bg-slate-800 rounded animate-pulse" />
      <div className="h-12 bg-slate-800 rounded animate-pulse" />
      <div className="h-12 bg-slate-800 rounded animate-pulse" />
      <div className="h-24 bg-slate-800 rounded animate-pulse" />
      <div className="h-40 bg-slate-800 rounded animate-pulse" />
    </div>
  );
}

function EmptyOnboardingState() {
  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <GraduationCap className="w-12 h-12 text-slate-600 mb-4" />
      <h3 className="text-sm font-semibold text-slate-400 mb-2">
        Select your role to begin
      </h3>
      <p className="text-xs text-slate-500 max-w-sm">
        Choose your role to generate a personalized onboarding path for this
        repository.
      </p>
    </div>
  );
}

export default function OnboardingPage() {
  const { activeRepo, authHeaders, userRole, setUserRole } = useSession();
  const queryClient = useQueryClient();
  
  const [selectedStageIndex, setSelectedStageIndex] = useState(0);
  const [showCompletionDialog, setShowCompletionDialog] = useState(false);
  const [showCompletionCard, setShowCompletionCard] = useState(false);

  // Fetch onboarding data
  const {
    path,
    isLoading,
    isError,
    error,
    updateProgress,
    isUpdating,
  } = useOnboardingData(activeRepo, userRole as OnboardingRole | null, authHeaders);

  // Select role mutation
  const selectRoleMutation = useMutation({
    mutationFn: (role: OnboardingRole) =>
      onboardingApi.selectRole(
        { role, user_id: "current-user", repo: activeRepo },
        authHeaders()
      ),
    onSuccess: (_data, role) => {
      setUserRole(role);
      // Invalidate to fetch the path
      queryClient.invalidateQueries({ queryKey: ["onboarding-path", activeRepo, role] });
    },
  });

  const handleRoleSelect = (role: OnboardingRole) => {
    selectRoleMutation.mutate(role);
  };

  const stages = (path?.stages || []) as OnboardingStage[];
  const currentStageIndex = stages.findIndex((s: OnboardingStage) => !s.completed);
  const currentStage = currentStageIndex >= 0 ? stages[currentStageIndex] : null;

  // Auto-select current stage when path loads
  useEffect(() => {
    if (currentStageIndex >= 0) {
      setSelectedStageIndex(currentStageIndex);
    }
  }, [currentStageIndex]);

  const handleStageClick = (index: number) => {
    setSelectedStageIndex(index);
  };

  const handleMarkComplete = () => {
    setShowCompletionDialog(true);
  };

  const confirmMarkComplete = () => {
    if (!currentStage) return;

    const isLastStage = currentStageIndex === stages.length - 1;

    updateProgress({
      stage_id: currentStage.stage_id,
      user_id: "current-user",
      repo: activeRepo,
      completed_at: new Date().toISOString(),
    });

    setShowCompletionDialog(false);

    // Fire confetti if last stage
    if (isLastStage) {
      setTimeout(() => {
        confetti({
          particleCount: 200,
          spread: 70,
          origin: { y: 0.6 },
        });
        setShowCompletionCard(true);
      }, 200);
    } else {
      // Move to next stage
      setTimeout(() => {
        setSelectedStageIndex(currentStageIndex + 1);
      }, 500);
    }
  };

  // Show role selector if no role selected
  if (!userRole) {
    return <RoleSelector onSelect={handleRoleSelect} activeRepo={activeRepo} />;
  }

  // Loading state
  if (isLoading || selectRoleMutation.isPending) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8">
        <Loader2 className="w-8 h-8 text-blue-400 animate-spin mb-3" />
        <p className="text-sm text-slate-400">
          Loading your personalized learning path...
        </p>
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 text-center">
        <AlertCircle className="w-12 h-12 text-red-400 mb-4" />
        <h3 className="text-sm font-semibold text-slate-400 mb-2">
          Could not load your learning path for {activeRepo}
        </h3>
        <p className="text-xs text-slate-500 mb-4">
          {error instanceof Error ? error.message : "Try selecting your role again."}
        </p>
        <div className="flex gap-3">
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ["onboarding-path"] })}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 transition-colors"
          >
            Retry
          </button>
          <button
            onClick={() => setUserRole(null)}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-slate-400 hover:text-white transition-colors"
          >
            Change role
          </button>
        </div>
      </div>
    );
  }

  // Empty state
  if (!path || stages.length === 0) {
    return <EmptyOnboardingState />;
  }

  // Completion card
  if (showCompletionCard) {
    const completedCount = stages.filter((s: OnboardingStage) => s.completed).length;
    const totalResources = stages.reduce(
      (acc: number, s: OnboardingStage) => acc + (s.resources?.length || 0),
      0
    );

    return (
      <div className="h-full flex flex-col items-center justify-center p-8 text-center">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center mb-6">
          <GraduationCap className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-2xl font-bold text-white mb-3">
          You&apos;ve completed the onboarding path for {activeRepo}!
        </h1>
        <p className="text-sm text-muted mb-6 max-w-md">
          You&apos;ve completed {completedCount} stages and reviewed{" "}
          {totalResources} resources. You&apos;re ready to start contributing!
        </p>
        <div className="flex gap-3">
          <Link
            href="/qa"
            className="px-6 py-3 rounded-xl text-sm font-semibold text-white bg-blue-600 hover:bg-blue-500 transition-colors"
          >
            Start contributing
          </Link>
          <Link
            href="/graph"
            className="px-6 py-3 rounded-xl text-sm font-semibold text-slate-400 hover:text-white border border-slate-700 hover:border-slate-600 transition-colors"
          >
            View your team&apos;s graph
          </Link>
        </div>
      </div>
    );
  }

  const selectedStage = stages[selectedStageIndex];
  const completedCount = stages.filter((s: OnboardingStage) => s.completed).length;
  const totalCount = stages.length;

  // Mock engineers data - in real implementation this would come from API
  const mockEngineers = [
    {
      id: "eng-1",
      name: "Alice Johnson",
      role: "Senior Backend Engineer",
      owned_services: ["auth-service", "user-service"],
      expertise_tags: ["Go", "PostgreSQL", "Kubernetes"],
    },
    {
      id: "eng-2",
      name: "Bob Smith",
      role: "Staff SRE",
      owned_services: ["monitoring-service"],
      expertise_tags: ["Prometheus", "Grafana", "Terraform"],
    },
  ];

  return (
    <div className="min-w-[1280px] h-full overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white mb-1">
            {userRole.replace("_", " ").replace(/\b\w/g, (l) => l.toUpperCase())}{" "}
            Learning Path
          </h1>
          <p className="text-sm text-slate-400">{activeRepo}</p>
        </div>
        <button
          onClick={() => setUserRole(null)}
          className="text-sm text-slate-500 hover:text-slate-300 transition-colors"
        >
          Switch role
        </button>
      </div>

      {/* Progress Summary */}
      <div className="p-4 rounded-2xl bg-slate-800/30 border border-slate-700">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-white">Overall Progress</span>
          <span className="text-sm font-bold text-white">
            {completedCount}/{totalCount} stages
          </span>
        </div>
        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-green-500 transition-all duration-500"
            style={{
              width: `${totalCount > 0 ? (completedCount / totalCount) * 100 : 0}%`,
            }}
          />
        </div>
      </div>

      {/* Stage Track */}
      {isLoading ? (
        <div className="flex gap-4 overflow-x-auto pb-4">
          {[...Array(5)].map((_, i) => (
            <StageSkeleton key={i} />
          ))}
        </div>
      ) : (
        <StageTrack
          stages={stages}
          currentStageIndex={currentStageIndex}
          onStageClick={handleStageClick}
        />
      )}

      {/* Stage Detail */}
      {isLoading ? (
        <StageDetailSkeleton />
      ) : selectedStage ? (
        <StageDetail
          stage={selectedStage}
          userRole={userRole as OnboardingRole}
          activeRepo={activeRepo}
          onMarkComplete={
            selectedStageIndex === currentStageIndex && !selectedStage.completed
              ? handleMarkComplete
              : undefined
          }
          isCurrentStage={selectedStageIndex === currentStageIndex}
        />
      ) : null}

      {/* Teammate Map */}
      {selectedStage && (
        <TeammateMap
          engineers={mockEngineers}
          currentStageServices={["auth-service", "user-service"]}
        />
      )}

      {/* Completion Dialog */}
      <AlertDialog open={showCompletionDialog} onOpenChange={setShowCompletionDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Mark stage as complete?</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure? This will unlock the next stage.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={confirmMarkComplete} disabled={isUpdating}>
              {isUpdating ? "Completing..." : "Confirm"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
