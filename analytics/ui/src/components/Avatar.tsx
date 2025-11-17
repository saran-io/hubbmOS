import { cn } from "../lib/utils";
import type { ImgHTMLAttributes, ReactNode } from "react";

interface AvatarProps extends ImgHTMLAttributes<HTMLImageElement> {
  fallback?: ReactNode;
  className?: string;
}

export function Avatar({ fallback, className, ...props }: AvatarProps) {
  return (
    <div
      className={cn(
        "flex h-10 w-10 items-center justify-center overflow-hidden rounded-full bg-slate-200 text-sm font-semibold text-slate-600",
        className
      )}
    >
      {props.src ? (
        <img
          {...props}
          className={cn("h-full w-full object-cover", props.className)}
        />
      ) : (
        fallback
      )}
    </div>
  );
}

