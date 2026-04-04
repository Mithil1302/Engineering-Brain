/**
 * PolicyErrorState component
 * 
 * Displays error states for policy runs with specific messages:
 * - Empty results: "No policy runs found for {activeRepo} in the selected date range"
 * - Network errors: "Failed to load policy runs. Check your connection."
 * Both include a retry button.
 * 
 * Requirements: 4.23, 8.6
 * Properties: 38 (error state with retry)
 */

import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface PolicyErrorStateProps {
  type: "empty" | "network";
  activeRepo: string;
  onRetry: () => void;
}

export function PolicyErrorState({ type, activeRepo, onRetry }: PolicyErrorStateProps) {
  const message = type === "empty"
    ? `No policy runs found for ${activeRepo} in the selected date range`
    : "Failed to load policy runs. Check your connection.";

  return (
    <div className="flex flex-col items-center justify-center h-full p-8 text-center">
      <AlertCircle className="w-12 h-12 text-slate-600 mb-4" />
      <p className="text-sm text-slate-400 mb-4 max-w-md">{message}</p>
      <Button
        onClick={onRetry}
        variant="outline"
        size="sm"
        className="flex items-center gap-2"
      >
        <RefreshCw className="w-4 h-4" />
        Retry
      </Button>
    </div>
  );
}

/**
 * PolicyListErrorState component
 * 
 * Error state specifically for the policy run list panel.
 */
interface PolicyListErrorStateProps {
  type: "empty" | "network";
  activeRepo: string;
  onRetry: () => void;
}

export function PolicyListErrorState({ type, activeRepo, onRetry }: PolicyListErrorStateProps) {
  const message = type === "empty"
    ? `No policy runs found for ${activeRepo} in the selected date range`
    : "Failed to load policy runs. Check your connection.";

  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <AlertCircle className="w-10 h-10 text-slate-600 mb-3" />
      <p className="text-xs text-slate-400 mb-3 max-w-xs">{message}</p>
      <Button
        onClick={onRetry}
        variant="outline"
        size="sm"
        className="flex items-center gap-2 text-xs"
      >
        <RefreshCw className="w-3 h-3" />
        Retry
      </Button>
    </div>
  );
}
