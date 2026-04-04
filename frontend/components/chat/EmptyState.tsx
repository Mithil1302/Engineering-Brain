"use client";
import { MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";

// Suggestion cards for empty state
const SUGGESTION_CARDS = [
  {
    category: "Architecture",
    color: "blue",
    questions: [
      "What does the payments service do?",
      "What services depend on the auth service?",
    ],
  },
  {
    category: "Policy",
    color: "amber",
    questions: [
      "Which PRs are currently blocked by policy?",
      "Show me active waivers for this repo",
    ],
  },
  {
    category: "Onboarding",
    color: "green",
    questions: [
      "What should I understand first as a new backend engineer?",
      "Who owns the notification service?",
    ],
  },
  {
    category: "Impact",
    color: "red",
    questions: [
      "What breaks if I deprecate the /v1/users endpoint?",
      "What's affected if I change the user_id field type?",
    ],
  },
];

interface EmptyStateProps {
  onSend: (question: string) => void;
}

export function EmptyState({ onSend }: EmptyStateProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center p-8">
      {/* Logo */}
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center mb-6 shadow-lg">
        <MessageSquare className="w-8 h-8 text-white" />
      </div>

      {/* Heading */}
      <h2 className="text-xl md:text-2xl font-bold text-white mb-2">
        Ask anything about your codebase
      </h2>

      {/* Subheading */}
      <p className="text-sm md:text-base text-slate-400 text-center mb-12 max-w-2xl">
        I have full context of your services, APIs, policies, and architecture
        decisions
      </p>

      {/* 2x4 grid of suggestion cards */}
      <div className="grid grid-cols-2 gap-4 w-full max-w-4xl">
        {SUGGESTION_CARDS.map((card) => (
          <div
            key={card.category}
            className={cn(
              "rounded-xl bg-slate-800/50 border-l-4 p-6 space-y-3",
              card.color === "blue" && "border-l-blue-500",
              card.color === "amber" && "border-l-amber-500",
              card.color === "green" && "border-l-green-500",
              card.color === "red" && "border-l-red-500"
            )}
          >
            <h3
              className={cn(
                "text-sm md:text-base font-semibold",
                card.color === "blue" && "text-blue-400",
                card.color === "amber" && "text-amber-400",
                card.color === "green" && "text-green-400",
                card.color === "red" && "text-red-400"
              )}
            >
              {card.category}
            </h3>
            <div className="space-y-2">
              {card.questions.map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => onSend(question)}
                  className="w-full text-left text-sm md:text-base text-slate-300 hover:text-white hover:bg-slate-700/50 px-3 py-2 rounded-lg transition-colors"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
