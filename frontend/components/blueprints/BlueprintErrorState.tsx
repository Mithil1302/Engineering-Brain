import { Layers } from "lucide-react";
import { Button } from "@/components/ui/button";

interface BlueprintErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function BlueprintErrorState({ message, onRetry }: BlueprintErrorStateProps) {
  return (
    <div className="flex-1 flex items-center justify-center text-center p-6">
      <div>
        <Layers className="w-8 h-8 text-slate-700 mx-auto mb-3" />
        <p className="text-sm text-slate-500 mb-4">{message}</p>
        {onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    </div>
  );
}
