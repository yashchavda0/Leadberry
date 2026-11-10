"use client";

import * as React from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

// Use instead of the native `title` attribute: <Tip label="Refresh"><button>…</button></Tip>.
// Disabled controls don't emit hover events, so they are wrapped in a span.
export function Tip({ label, shortcut, side, disabled, children }: { label: React.ReactNode; shortcut?: string; side?: "top" | "right" | "bottom" | "left"; disabled?: boolean; children: React.ReactElement }) {
  return <Tooltip>
    <TooltipTrigger asChild>{disabled ? <span className="tip-wrap" tabIndex={0}>{children}</span> : children}</TooltipTrigger>
    <TooltipContent side={side} shortcut={shortcut}>{label}</TooltipContent>
  </Tooltip>;
}
