"use client";

import { useState, useEffect, useMemo } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useSession } from "@/store/session";
import { policyApi } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { Calendar, Search, X } from "lucide-react";
import { DayPicker } from "react-day-picker";
import { cn } from "@/lib/utils";
import "react-day-picker/style.css";

type OutcomeOption = "all" | "pass" | "warn" | "block";

interface FilterBarProps {
  className?: string;
}

export function FilterBar({ className }: FilterBarProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { activeRepo, authHeaders } = useSession();

  // Read initial values from URL
  const [outcome, setOutcome] = useState<OutcomeOption>(
    (searchParams.get("outcome") as OutcomeOption) || "all"
  );
  const [ruleset, setRuleset] = useState<string>(
    searchParams.get("ruleset") || "all"
  );
  const [dateRange, setDateRange] = useState<string>(
    searchParams.get("range") || "last7"
  );
  const [searchText, setSearchText] = useState<string>(
    searchParams.get("search") || ""
  );
  const [customDateFrom, setCustomDateFrom] = useState<Date | undefined>(
    searchParams.get("from") ? new Date(searchParams.get("from")!) : undefined
  );
  const [customDateTo, setCustomDateTo] = useState<Date | undefined>(
    searchParams.get("to") ? new Date(searchParams.get("to")!) : undefined
  );
  const [showCustomDatePicker, setShowCustomDatePicker] = useState(false);

  // Debounced search text
  const [debouncedSearch, setDebouncedSearch] = useState(searchText);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchText);
    }, 200);
    return () => clearTimeout(timer);
  }, [searchText]);

  // Fetch rulesets
  const { data: rulesetsData } = useQuery({
    queryKey: ["policy-rulesets", activeRepo],
    queryFn: () => policyApi.rulesets(activeRepo!, authHeaders()),
    enabled: !!activeRepo,
  });

  const rulesets = useMemo(() => {
    if (!rulesetsData) return [];
    return Array.isArray(rulesetsData) ? rulesetsData : (rulesetsData as any).items || [];
  }, [rulesetsData]);

  // Sync filters to URL
  useEffect(() => {
    const params = new URLSearchParams();
    
    if (outcome !== "all") params.set("outcome", outcome);
    if (ruleset !== "all") params.set("ruleset", ruleset);
    if (dateRange !== "last7") params.set("range", dateRange);
    if (debouncedSearch) params.set("search", debouncedSearch);
    
    if (dateRange === "custom") {
      if (customDateFrom) params.set("from", customDateFrom.toISOString().split("T")[0]);
      if (customDateTo) params.set("to", customDateTo.toISOString().split("T")[0]);
    }

    const queryString = params.toString();
    const newUrl = queryString ? `?${queryString}` : window.location.pathname;
    router.replace(newUrl, { scroll: false });
  }, [outcome, ruleset, dateRange, debouncedSearch, customDateFrom, customDateTo, router]);

  const handleOutcomeChange = (value: OutcomeOption) => {
    setOutcome(value);
  };

  const handleRulesetChange = (value: string) => {
    setRuleset(value);
  };

  const handleDateRangeChange = (value: string) => {
    setDateRange(value);
    if (value !== "custom") {
      setCustomDateFrom(undefined);
      setCustomDateTo(undefined);
      setShowCustomDatePicker(false);
    } else {
      setShowCustomDatePicker(true);
    }
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchText(e.target.value);
  };

  const handleClearSearch = () => {
    setSearchText("");
  };

  const getOutcomeDotColor = (opt: OutcomeOption) => {
    switch (opt) {
      case "pass":
        return "bg-emerald-400";
      case "warn":
        return "bg-amber-400";
      case "block":
        return "bg-red-400";
      default:
        return "bg-slate-400";
    }
  };

  return (
    <div className={cn("flex flex-col gap-3 p-4 border-b border-slate-700/50", className)}>
      {/* Row 1: Outcome segmented control */}
      <div className="flex gap-1.5">
        {(["all", "pass", "warn", "block"] as OutcomeOption[]).map((opt) => (
          <button
            key={opt}
            type="button"
            onClick={() => handleOutcomeChange(opt)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all capitalize",
              outcome === opt
                ? "bg-indigo-600 text-white"
                : "bg-slate-800/50 text-slate-400 hover:text-white hover:bg-slate-800"
            )}
          >
            <span className={cn("w-2 h-2 rounded-full", getOutcomeDotColor(opt))} />
            {opt}
          </button>
        ))}
      </div>

      {/* Row 2: Ruleset, Date Range, Search */}
      <div className="flex gap-3">
        {/* Ruleset Dropdown */}
        <div className="flex-1">
          <Select value={ruleset} onValueChange={handleRulesetChange}>
            <SelectTrigger className="w-full bg-slate-800 border-slate-700 text-sm">
              <SelectValue placeholder="All rulesets" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All rulesets</SelectItem>
              {rulesets.map((rs: any) => (
                <SelectItem key={rs.name || rs} value={rs.name || rs}>
                  {rs.name || rs}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Date Range Selector */}
        <div className="flex gap-1.5">
          <Button
            type="button"
            variant={dateRange === "today" ? "default" : "outline"}
            size="sm"
            onClick={() => handleDateRangeChange("today")}
            className={cn(
              "text-xs",
              dateRange === "today"
                ? "bg-indigo-600 text-white hover:bg-indigo-500"
                : "bg-slate-800/50 border-slate-700 text-slate-400 hover:text-white hover:bg-slate-800"
            )}
          >
            Today
          </Button>
          <Button
            type="button"
            variant={dateRange === "last7" ? "default" : "outline"}
            size="sm"
            onClick={() => handleDateRangeChange("last7")}
            className={cn(
              "text-xs",
              dateRange === "last7"
                ? "bg-indigo-600 text-white hover:bg-indigo-500"
                : "bg-slate-800/50 border-slate-700 text-slate-400 hover:text-white hover:bg-slate-800"
            )}
          >
            Last 7 days
          </Button>
          <Button
            type="button"
            variant={dateRange === "last30" ? "default" : "outline"}
            size="sm"
            onClick={() => handleDateRangeChange("last30")}
            className={cn(
              "text-xs",
              dateRange === "last30"
                ? "bg-indigo-600 text-white hover:bg-indigo-500"
                : "bg-slate-800/50 border-slate-700 text-slate-400 hover:text-white hover:bg-slate-800"
            )}
          >
            Last 30 days
          </Button>
          
          {/* Custom Date Range Popover */}
          <Popover open={showCustomDatePicker} onOpenChange={setShowCustomDatePicker}>
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant={dateRange === "custom" ? "default" : "outline"}
                size="sm"
                className={cn(
                  "text-xs",
                  dateRange === "custom"
                    ? "bg-indigo-600 text-white hover:bg-indigo-500"
                    : "bg-slate-800/50 border-slate-700 text-slate-400 hover:text-white hover:bg-slate-800"
                )}
              >
                <Calendar className="w-3 h-3 mr-1" />
                Custom
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-0" align="start">
              <div className="p-4 space-y-3">
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">From</label>
                  <DayPicker
                    mode="single"
                    selected={customDateFrom}
                    onSelect={(date) => {
                      setCustomDateFrom(date);
                      setDateRange("custom");
                    }}
                    className="text-slate-200"
                    classNames={{
                      day_button: "text-slate-200 hover:bg-slate-800 rounded",
                      selected: "bg-indigo-600 text-white hover:bg-indigo-500",
                      today: "font-bold text-indigo-400",
                      outside: "text-slate-600",
                      disabled: "text-slate-700",
                    }}
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1.5 block">To</label>
                  <DayPicker
                    mode="single"
                    selected={customDateTo}
                    onSelect={(date) => {
                      setCustomDateTo(date);
                      setDateRange("custom");
                    }}
                    disabled={(date) => customDateFrom ? date < customDateFrom : false}
                    className="text-slate-200"
                    classNames={{
                      day_button: "text-slate-200 hover:bg-slate-800 rounded",
                      selected: "bg-indigo-600 text-white hover:bg-indigo-500",
                      today: "font-bold text-indigo-400",
                      outside: "text-slate-600",
                      disabled: "text-slate-700",
                    }}
                  />
                </div>
              </div>
            </PopoverContent>
          </Popover>
        </div>

        {/* Search Input */}
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <Input
            type="text"
            placeholder="Search by PR number or branch..."
            value={searchText}
            onChange={handleSearchChange}
            className="pl-9 pr-9 bg-slate-800 border-slate-700 text-sm"
          />
          {searchText && (
            <button
              type="button"
              onClick={handleClearSearch}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition-colors"
              aria-label="Clear search"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
