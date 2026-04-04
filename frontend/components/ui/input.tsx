import { cn } from "@/lib/utils";
import { InputHTMLAttributes, forwardRef } from "react";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "w-full rounded-lg bg-slate-800/60 border border-slate-700 text-sm text-white placeholder-slate-500",
        "px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent",
        "disabled:opacity-50 disabled:cursor-not-allowed transition-colors",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
