import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Minimal Progress bar. shadcn's default uses `@radix-ui/react-progress`,
 * but that would add a runtime dep for a single-purpose visual. This div
 * version has identical semantics via `role="progressbar"` and is a11y-clean.
 */
function Progress({
  className,
  value,
  ...props
}: React.ComponentProps<"div"> & { value?: number }) {
  const clamped =
    typeof value === "number" ? Math.max(0, Math.min(100, value)) : 0;
  return (
    <div
      data-slot="progress"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={clamped}
      className={cn(
        "relative h-2 w-full overflow-hidden rounded-full bg-muted",
        className
      )}
      {...props}
    >
      <div
        data-slot="progress-indicator"
        className="h-full bg-primary transition-transform"
        style={{
          transform: `translateX(-${100 - clamped}%)`,
          width: "100%",
        }}
      />
    </div>
  );
}

export { Progress };
