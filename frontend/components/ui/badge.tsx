import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export const badgeVariants = cva("ui-badge", {
  variants: { variant: { default: "ui-badge-default", success: "ui-badge-success", warning: "ui-badge-warning", destructive: "ui-badge-destructive", info: "ui-badge-info", outline: "ui-badge-outline" } },
  defaultVariants: { variant: "default" },
});

export function Badge({ className, variant, dot, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants> & { dot?: boolean }) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props}>{dot && <span className="ui-badge-dot" aria-hidden="true" />}{props.children}</span>;
}
