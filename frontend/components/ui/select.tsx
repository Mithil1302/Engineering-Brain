"use client";
import * as SelectPrimitive from "@radix-ui/react-select";
import { ChevronDown, Check } from "lucide-react";
import { cn } from "@/lib/utils";

export const Select = SelectPrimitive.Root;
export const SelectValue = SelectPrimitive.Value;

export function SelectTrigger({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <SelectPrimitive.Trigger
      className={cn(
        "flex items-center justify-between gap-2 w-full rounded-lg bg-slate-800/60 border border-slate-700",
        "px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500",
        "hover:border-slate-600 transition-colors",
        className
      )}
    >
      {children}
      <SelectPrimitive.Icon><ChevronDown className="w-4 h-4 text-slate-400" /></SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

export function SelectContent({ children }: { children: React.ReactNode }) {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Content className="z-50 glass rounded-lg border border-slate-700 shadow-xl overflow-hidden">
        <SelectPrimitive.Viewport className="p-1">
          {children}
        </SelectPrimitive.Viewport>
      </SelectPrimitive.Content>
    </SelectPrimitive.Portal>
  );
}

export function SelectItem({ value, children }: { value: string; children: React.ReactNode }) {
  return (
    <SelectPrimitive.Item
      value={value}
      className="flex items-center gap-2 px-3 py-2 text-sm text-slate-300 hover:text-white hover:bg-slate-700 rounded-md cursor-pointer focus:outline-none data-[highlighted]:bg-slate-700 data-[highlighted]:text-white"
    >
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator><Check className="w-3 h-3 text-indigo-400" /></SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  );
}
