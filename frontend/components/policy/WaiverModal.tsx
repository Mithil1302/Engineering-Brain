"use client";

import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { governanceApi } from "@/lib/api";
import {
  Dialog,
  DialogContent,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { DayPicker } from "react-day-picker";
import { format, addDays } from "date-fns";
import { Calendar, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import "react-day-picker/style.css";

interface WaiverModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ruleIds: string[];
  repo: string;
  prNumber?: number;
}

export function WaiverModal({
  open,
  onOpenChange,
  ruleIds,
  repo,
  prNumber,
}: WaiverModalProps) {
  const { authHeaders } = useSession();
  const queryClient = useQueryClient();

  // Form state
  const [justification, setJustification] = useState("");
  const [expiryDate, setExpiryDate] = useState<Date>(addDays(new Date(), 7));
  const [isCalendarOpen, setIsCalendarOpen] = useState(false);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [apiError, setApiError] = useState<string | null>(null);

  // Reset form when modal opens/closes
  useEffect(() => {
    if (open) {
      setJustification("");
      setExpiryDate(addDays(new Date(), 7));
      setValidationErrors([]);
      setApiError(null);
    }
  }, [open]);

  // Create waiver mutation
  const createWaiverMutation = useMutation({
    mutationFn: async () => {
      const body = {
        rule_ids: ruleIds,
        justification,
        expires_at: expiryDate.toISOString(),
        repo,
        pr_number: prNumber || 0,
      };
      return governanceApi.createWaiver(body, authHeaders());
    },
    onSuccess: () => {
      // Close modal
      onOpenChange(false);
      
      // Invalidate policy run query to refresh data
      queryClient.invalidateQueries({ queryKey: ["policy-runs"] });
      
      // TODO: Push success notification via UISlice when available
      // For now, we'll just log success
      console.log("Waiver created successfully");
    },
    onError: (error: any) => {
      // Display API error message
      const errorMessage = error.message || "Failed to create waiver";
      setApiError(errorMessage);
    },
  });

  // Client-side validation
  const validateForm = (): boolean => {
    const errors: string[] = [];

    // Validate rule_ids not empty
    if (!ruleIds || ruleIds.length === 0) {
      errors.push("At least one rule must be selected");
    }

    // Validate justification >= 50 characters
    if (justification.trim().length < 50) {
      errors.push("Justification must be at least 50 characters");
    }

    // Validate expiry date <= 30 days from now
    const now = new Date();
    const maxExpiryDate = addDays(now, 30);
    if (expiryDate > maxExpiryDate) {
      errors.push("Expiry date cannot be more than 30 days from today");
    }

    // Validate expiry date is in the future
    if (expiryDate <= now) {
      errors.push("Expiry date must be in the future");
    }

    setValidationErrors(errors);
    return errors.length === 0;
  };

  // Handle submit
  const handleSubmit = () => {
    setApiError(null);
    
    if (!validateForm()) {
      return;
    }

    createWaiverMutation.mutate();
  };

  // Character count for justification
  const charCount = justification.length;
  const isCharCountBelowMin = charCount < 50;

  // Calculate max date (30 days from today)
  const maxDate = addDays(new Date(), 30);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        {/* Header */}
        <div className="space-y-2 mb-4">
          <h2 className="text-lg font-semibold text-white">Request Waiver</h2>
          <p className="text-sm text-slate-400">
            Request a temporary waiver to bypass policy rules for this PR.
          </p>
        </div>

        <div className="space-y-4 py-4">
          {/* Rule being waived (read-only pre-filled select) */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-200">
              Rule being waived
            </label>
            <Select value={ruleIds[0]} disabled={true}>
              <SelectTrigger className="w-full opacity-60 cursor-not-allowed">
                <SelectValue>
                  {ruleIds.length === 1
                    ? ruleIds[0]
                    : `${ruleIds.length} rules selected`}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {ruleIds.map((ruleId) => (
                  <SelectItem key={ruleId} value={ruleId}>
                    {ruleId}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Justification textarea with character counter */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-200">
              Justification
            </label>
            <textarea
              value={justification}
              onChange={(e) => setJustification(e.target.value)}
              placeholder="Explain why this waiver is needed..."
              className="w-full min-h-[120px] px-3 py-2 text-sm bg-slate-900 border border-slate-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              disabled={createWaiverMutation.isPending}
            />
            <div className="flex justify-end">
              <span
                className={cn(
                  "text-xs",
                  isCharCountBelowMin ? "text-red-500" : "text-slate-400"
                )}
              >
                {charCount}/50 minimum
              </span>
            </div>
          </div>

          {/* Expiry date picker */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-slate-200">
              Expiry date
            </label>
            <Popover open={isCalendarOpen} onOpenChange={setIsCalendarOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className={cn(
                    "w-full justify-start text-left font-normal",
                    !expiryDate && "text-slate-400"
                  )}
                  disabled={createWaiverMutation.isPending}
                >
                  <Calendar className="mr-2 h-4 w-4" />
                  {expiryDate ? format(expiryDate, "PPP") : "Select date"}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <DayPicker
                  mode="single"
                  selected={expiryDate}
                  onSelect={(date) => {
                    if (date) {
                      setExpiryDate(date);
                      setIsCalendarOpen(false);
                    }
                  }}
                  disabled={(date) => {
                    const today = new Date();
                    today.setHours(0, 0, 0, 0);
                    return date < today || date > maxDate;
                  }}
                  initialFocus
                />
              </PopoverContent>
            </Popover>
            <p className="text-xs text-slate-400">
              Maximum 30 days from today
            </p>
          </div>

          {/* Validation errors */}
          {validationErrors.length > 0 && (
            <div className="rounded-md bg-red-500/10 border border-red-500/20 p-3">
              <ul className="list-disc list-inside space-y-1">
                {validationErrors.map((error, index) => (
                  <li key={index} className="text-sm text-red-500">
                    {error}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* API error */}
          {apiError && (
            <div className="text-sm text-red-500 mt-2">
              {apiError}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 pt-4 border-t border-slate-700">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={createWaiverMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={createWaiverMutation.isPending}
          >
            {createWaiverMutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Submit Request
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
