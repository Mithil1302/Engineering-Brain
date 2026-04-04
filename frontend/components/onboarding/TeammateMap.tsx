"use client";

import Link from "next/link";

interface Engineer {
  id: string;
  name: string;
  role: string;
  owned_services: string[];
  expertise_tags: string[];
}

interface TeammateMapProps {
  engineers: Engineer[];
  currentStageServices: string[];
}

// Hash function to deterministically select color from name
function getAvatarColor(name: string): string {
  const colors = [
    "bg-blue-500",
    "bg-purple-500",
    "bg-pink-500",
    "bg-red-500",
    "bg-orange-500",
    "bg-yellow-500",
    "bg-green-500",
    "bg-teal-500",
  ];
  const hash = name.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return colors[hash % colors.length];
}

function getInitials(name: string): string {
  const parts = name.split(" ");
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

export function TeammateMap({ engineers, currentStageServices }: TeammateMapProps) {
  // Filter engineers to only show those relevant to current stage
  const relevantEngineers = engineers.filter((engineer) =>
    engineer.owned_services.some((service) =>
      currentStageServices.includes(service)
    )
  );

  if (relevantEngineers.length === 0) {
    return null;
  }

  return (
    <div className="mt-8 p-6 bg-slate-800/30 rounded-2xl border border-slate-700">
      <h3 className="text-lg font-semibold text-white mb-4">Your Teammates</h3>
      <div className="grid grid-cols-3 gap-4">
        {relevantEngineers.map((engineer) => {
          const avatarColor = getAvatarColor(engineer.name);
          const initials = getInitials(engineer.name);
          const relevantServices = engineer.owned_services.filter((service) =>
            currentStageServices.includes(service)
          );

          return (
            <div
              key={engineer.id}
              className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/40"
            >
              <div className="flex items-start gap-3 mb-3">
                <div
                  className={`w-14 h-14 rounded-full ${avatarColor} flex items-center justify-center text-white font-bold text-lg shrink-0`}
                >
                  {initials}
                </div>
                <div className="flex-1 min-w-0">
                  <h4 className="font-semibold text-white">{engineer.name}</h4>
                  <p className="text-sm text-muted">{engineer.role}</p>
                </div>
              </div>

              {relevantServices.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs text-muted mb-2">Owns:</p>
                  <div className="flex flex-wrap gap-1">
                    {relevantServices.map((service) => (
                      <span
                        key={service}
                        className="px-2 py-0.5 rounded-full bg-slate-700 text-xs"
                      >
                        {service}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {engineer.expertise_tags.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs text-muted mb-2">Expertise:</p>
                  <div className="flex flex-wrap gap-1">
                    {engineer.expertise_tags.slice(0, 3).map((tag) => (
                      <span
                        key={tag}
                        className="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-500 text-xs"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              <Link
                href={`/graph?selectedNodeId=${engineer.id}`}
                className="text-xs text-blue-400 hover:text-blue-300"
              >
                View in graph →
              </Link>
            </div>
          );
        })}
      </div>
    </div>
  );
}
