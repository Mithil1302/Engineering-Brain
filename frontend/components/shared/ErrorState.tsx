import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";

interface ErrorStateProps {
  error: Error | ApiError | unknown;
  onRetry?: () => void;
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  let message = "An unexpected error occurred";

  if (error instanceof ApiError) {
    switch (error.status) {
      case 401:
        message = "Authentication required";
        break;
      case 403:
        message = "Permission denied";
        break;
      case 404:
        message = "Resource not found";
        break;
      case 500:
        message = "Server error";
        break;
      default:
        message = error.message;
    }
  } else if (error instanceof Error) {
    message = error.message;
  }

  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <AlertCircle className="w-12 h-12 text-red-500 mb-4" />
      <p className="text-slate-300 mb-4">{message}</p>
      {onRetry && (
        <Button onClick={onRetry} variant="outline">
          Retry
        </Button>
      )}
    </div>
  );
}
