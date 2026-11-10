"use client";

import * as React from "react";
import * as MenuPrimitive from "@radix-ui/react-dropdown-menu";
import { cn } from "@/lib/utils";

export const DropdownMenu = MenuPrimitive.Root;
export const DropdownMenuTrigger = MenuPrimitive.Trigger;
export const DropdownMenuGroup = MenuPrimitive.Group;

export const DropdownMenuContent = React.forwardRef<React.ElementRef<typeof MenuPrimitive.Content>, React.ComponentPropsWithoutRef<typeof MenuPrimitive.Content>>(({ className, sideOffset = 6, align = "end", ...props }, ref) => (
  <MenuPrimitive.Portal><MenuPrimitive.Content ref={ref} sideOffset={sideOffset} align={align} className={cn("ui-menu", className)} {...props} /></MenuPrimitive.Portal>
));
DropdownMenuContent.displayName = "DropdownMenuContent";

export const DropdownMenuItem = React.forwardRef<React.ElementRef<typeof MenuPrimitive.Item>, React.ComponentPropsWithoutRef<typeof MenuPrimitive.Item> & { destructive?: boolean }>(({ className, destructive, ...props }, ref) => (
  <MenuPrimitive.Item ref={ref} className={cn("ui-menu-item", destructive && "ui-menu-item-destructive", className)} {...props} />
));
DropdownMenuItem.displayName = "DropdownMenuItem";

export const DropdownMenuLabel = ({ className, ...props }: React.ComponentPropsWithoutRef<typeof MenuPrimitive.Label>) => <MenuPrimitive.Label className={cn("ui-menu-label", className)} {...props} />;
export const DropdownMenuSeparator = ({ className, ...props }: React.ComponentPropsWithoutRef<typeof MenuPrimitive.Separator>) => <MenuPrimitive.Separator className={cn("ui-menu-separator", className)} {...props} />;
