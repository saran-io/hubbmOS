import { cn } from "../lib/utils";
import type { ReactNode } from "react";

interface BadgeProps {
  className?: string;
  children: ReactNode;
}

export function Badge({ className, children }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-3 py-0.5 text-xs font-semibold",
        className
      )}
    >
      {children}
    </span>
  );
}

