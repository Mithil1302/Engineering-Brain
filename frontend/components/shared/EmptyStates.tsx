import { GitBranch, Shield, GraduationCap } from "lucide-react";

interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description: string;
}

function EmptyState({ icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-center">
      <div className="mb-4">{icon}</div>
      <h3 className="text-lg font-semibold text-slate-200 mb-2">{title}</h3>
      <p className="text-sm text-slate-400 max-w-md">{description}</p>
    </div>
  );
}

export function EmptyGraphState() {
  return (
    <EmptyState
      icon={<GitBranch className="w-12 h-12 text-slate-600" />}
      title="No graph data found"
      description="The knowledge graph for this repository hasn't been indexed yet. Trigger an indexing run to populate the graph."
    />
  );
}

export function EmptyPolicyRunsState() {
  return (
    <EmptyState
      icon={<Shield className="w-12 h-12 text-slate-600" />}
      title="No policy runs found"
      description="Policy runs will appear here when pull requests are opened or updated."
    />
  );
}

export function EmptyOnboardingState() {
  return (
    <EmptyState
      icon={<GraduationCap className="w-12 h-12 text-slate-600" />}
      title="Select your role to begin"
      description="Choose your role to generate a personalized onboarding path for this repository."
    />
  );
}
