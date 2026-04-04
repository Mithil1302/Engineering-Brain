"use client";

import { useState } from "react";
import { Calendar, Filter } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

interface FilterBarProps {
  filters: {
    pattern: string | null;
    from: string | null;
    to: string | null;
    aligned: boolean | null;
  };
  onFiltersChange: (filters: {
    pattern: string | null;
    from: string | null;
    to: string | null;
    aligned: boolean | null;
  }) => void;
}

const PATTERN_OPTIONS = [
  "Microservices",
  "Monolith",
  "CQRS",
  "BFF",
  "Saga",
  "Event-driven",
];

const DATE_PRESETS = [
  { label: "Today", days: 0 },
  { label: "Last 7 days", days: 7 },
  { label: "Last 30 days", days: 30 },
];

export function FilterBar({ filters, onFiltersChange }: FilterBarProps) {
  const [datePreset, setDatePreset] = useState<string>("Last 30 days");

  const handlePatternChange = (value: string) => {
    onFiltersChange({
      ...filters,
      pattern: value === "all" ? null : value,
    });
  };

  const handleAlignmentChange = (value: string) => {
    onFiltersChange({
      ...filters,
      aligned: value === "all" ? null : value === "aligned",
    });
  };

  const handleDatePresetChange = (label: string, days: number) => {
    setDatePreset(label);
    const now = new Date();
    const from = new Date(now);
    from.setDate(from.getDate() - days);
    
    onFiltersChange({
      ...filters,
      from: days === 0 ? now.toISOString().split("T")[0] : from.toISOString().split("T")[0],
      to: now.toISOString().split("T")[0],
    });
  };

  return (
    <div className="p-4 border-b border-slate-700/50 space-y-3">
      {/* Pattern filter */}
      <div>
        <label className="text-xs text-slate-400 mb-1.5 block">Pattern</label>
        <Select
          value={filters.pattern || "all"}
          onValueChange={handlePatternChange}
        >
          <SelectTrigger className="w-full bg-slate-800 border-slate-700">
            <SelectValue placeholder="All patterns" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All patterns</SelectItem>
            {PATTERN_OPTIONS.map((pattern) => (
              <SelectItem key={pattern} value={pattern}>
                {pattern}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Date range filter */}
      <div>
        <label className="text-xs text-slate-400 mb-1.5 block">Date range</label>
        <div className="flex gap-2">
          {DATE_PRESETS.map((preset) => (
            <Button
              key={preset.label}
              variant={datePreset === preset.label ? "default" : "outline"}
              size="sm"
              onClick={() => handleDatePresetChange(preset.label, preset.days)}
              className="flex-1 text-xs"
            >
              {preset.label}
            </Button>
          ))}
          <Popover>
            <PopoverTrigger asChild>
              <Button
                variant={datePreset === "Custom" ? "default" : "outline"}
                size="sm"
                className="text-xs"
              >
                <Calendar className="w-3 h-3" />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-4">
              <div className="space-y-3">
                <div>
                  <label className="text-xs text-slate-400 mb-1 block">From</label>
                  <input
                    type="date"
                    value={filters.from || ""}
                    onChange={(e) => {
                      setDatePreset("Custom");
                      onFiltersChange({ ...filters, from: e.target.value });
                    }}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 mb-1 block">To</label>
                  <input
                    type="date"
                    value={filters.to || ""}
                    onChange={(e) => {
                      setDatePreset("Custom");
                      onFiltersChange({ ...filters, to: e.target.value });
                    }}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-white"
                  />
                </div>
              </div>
            </PopoverContent>
          </Popover>
        </div>
      </div>

      {/* Alignment filter */}
      <div>
        <label className="text-xs text-slate-400 mb-1.5 block">Alignment</label>
        <div className="flex gap-2">
          <Button
            variant={filters.aligned === null ? "default" : "outline"}
            size="sm"
            onClick={() => handleAlignmentChange("all")}
            className="flex-1 text-xs"
          >
            All
          </Button>
          <Button
            variant={filters.aligned === true ? "default" : "outline"}
            size="sm"
            onClick={() => handleAlignmentChange("aligned")}
            className="flex-1 text-xs"
          >
            Aligned
          </Button>
          <Button
            variant={filters.aligned === false ? "default" : "outline"}
            size="sm"
            onClick={() => handleAlignmentChange("drifted")}
            className="flex-1 text-xs"
          >
            Drifted
          </Button>
        </div>
      </div>
    </div>
  );
}
