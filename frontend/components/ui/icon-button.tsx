"use client";

import * as React from "react";
import Link from "next/link";
import { Button, type ButtonProps } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

// Icon-only button with an accessible name and a tooltip; pass `href` to render a link.
export const IconButton = React.forwardRef<HTMLButtonElement, Omit<ButtonProps, "size" | "asChild"> & { label: string; href?: string }>(({ label, href, variant = "outline", children, ...props }, ref) => (
  <Tooltip>
    <TooltipTrigger asChild>
      {href
        ? <Button asChild variant={variant} size="icon"><Link href={href} aria-label={label}>{children}</Link></Button>
        : <Button ref={ref} variant={variant} size="icon" aria-label={label} {...props}>{children}</Button>}
    </TooltipTrigger>
    <TooltipContent>{label}</TooltipContent>
  </Tooltip>
));
IconButton.displayName = "IconButton";
