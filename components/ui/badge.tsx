import * as React from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "subtle" | "success" | "highlight";
}

export function Badge({
  className,
  variant = "default",
  ...props
}: BadgeProps) {
  const baseStyles =
    "inline-block text-xs font-alt px-3 py-1 rounded-full border transition";

    const variantStyles: Record<NonNullable<BadgeProps["variant"]>, string> = {
    default: "bg-subtle text-text border-subtle",
    subtle: "bg-background text-subtle border border-subtle",
    success: "bg-accent2 text-white border-transparent",
    highlight: "bg-accent text-white border-transparent",
  };

  return (
    <div className={cn(baseStyles, variantStyles[variant], className)} {...props} />
  );
}
