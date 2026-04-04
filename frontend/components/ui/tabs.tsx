"use client";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <TabsPrimitive.List className={cn("flex gap-1 bg-slate-800/50 rounded-lg p-1 border border-slate-700/50", className)}>
      {children}
    </TabsPrimitive.List>
  );
}

export function TabsTrigger({ value, children, className }: { value: string; children: React.ReactNode; className?: string }) {
  return (
    <TabsPrimitive.Trigger
      value={value}
      className={cn(
        "flex-1 px-3 py-1.5 text-sm font-medium rounded-md transition-all",
        "text-slate-400 hover:text-white",
        "data-[state=active]:bg-slate-700 data-[state=active]:text-white data-[state=active]:shadow-sm",
        className
      )}
    >
      {children}
    </TabsPrimitive.Trigger>
  );
}

export function TabsContent({ value, children, className }: { value: string; children: React.ReactNode; className?: string }) {
  return (
    <TabsPrimitive.Content value={value} className={cn("mt-4", className)}>
      {children}
    </TabsPrimitive.Content>
  );
}
