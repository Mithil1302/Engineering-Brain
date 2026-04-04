"use client";

import { OnboardingRole } from "@/lib/types";
import { Code, Server, Layout, Database, Users } from "lucide-react";

interface RoleSelectorProps {
  onSelect: (role: OnboardingRole) => void;
  activeRepo: string;
}

const ROLES: Array<{
  id: OnboardingRole;
  label: string;
  icon: React.ElementType;
  description: string;
}> = [
  {
    id: "backend_engineer",
    label: "Backend Engineer",
    icon: Code,
    description: "Services, APIs, data schemas, and system dependencies",
  },
  {
    id: "sre",
    label: "SRE",
    icon: Server,
    description: "Infrastructure, incident patterns, runbooks, and reliability decisions",
  },
  {
    id: "frontend_developer",
    label: "Frontend Developer",
    icon: Layout,
    description: "API contracts, BFF patterns, and frontend-relevant services",
  },
  {
    id: "data_engineer",
    label: "Data Engineer",
    icon: Database,
    description: "Data schemas, pipeline services, and data flow dependencies",
  },
  {
    id: "engineering_manager",
    label: "Engineering Manager",
    icon: Users,
    description: "Team ownership, service health, and architectural decisions",
  },
];

export function RoleSelector({ onSelect, activeRepo }: RoleSelectorProps) {
  return (
    <div className="fixed inset-0 z-50 bg-slate-900/95 flex items-center justify-center transition-opacity duration-300">
      <div className="flex flex-col items-center max-w-4xl w-full px-8">
        {/* Logo placeholder - using a simple icon */}
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center mb-6">
          <span className="text-2xl font-bold text-white">KB</span>
        </div>

        <h1 className="text-3xl font-bold text-white mb-3">
          Welcome to {activeRepo}
        </h1>
        <p className="text-lg text-slate-400 mb-12 text-center max-w-2xl">
          What&apos;s your role on this team? I&apos;ll build a personalized learning path for you.
        </p>

        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 w-full">
          {ROLES.map((role) => {
            const Icon = role.icon;
            return (
              <button
                key={role.id}
                onClick={() => onSelect(role.id)}
                className="group relative p-6 rounded-2xl border border-slate-700 bg-slate-800/50 hover:bg-slate-800 hover:border-blue-500 hover:shadow-lg transition-all duration-200 text-left"
              >
                <div className="flex items-start gap-4">
                  <div className="w-12 h-12 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0 group-hover:bg-blue-500/20 transition-colors">
                    <Icon className="w-6 h-6 text-blue-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-xl font-semibold text-white mb-2">
                      {role.label}
                    </h3>
                    <p className="text-sm text-slate-400 leading-relaxed">
                      {role.description}
                    </p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
