"use client";

import * as React from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

// Warm-up: after one tooltip shows, neighbours open instantly (skipDelayDuration), like React Spectrum.
export const TooltipProvider = ({ delayDuration = 300, skipDelayDuration = 500, ...props }: React.ComponentProps<typeof TooltipPrimitive.Provider>) => <TooltipPrimitive.Provider delayDuration={delayDuration} skipDelayDuration={skipDelayDuration} {...props} />;
export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;

export const TooltipContent = React.forwardRef<React.ElementRef<typeof TooltipPrimitive.Content>, React.ComponentPropsWithoutRef<typeof TooltipPrimitive.Content> & { shortcut?: string }>(({ className, sideOffset = 8, shortcut, children, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content ref={ref} sideOffset={sideOffset} collisionPadding={8} className={cn("ui-tooltip", className)} {...props}>
      {children}{shortcut && <kbd className="ui-tooltip-kbd">{shortcut}</kbd>}
      <TooltipPrimitive.Arrow className="ui-tooltip-arrow" width={12} height={6} />
    </TooltipPrimitive.Content>
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = "TooltipContent";
