"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import Icon from "@/components/Icon";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export const DialogContent = React.forwardRef<React.ElementRef<typeof DialogPrimitive.Content>, React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & { size?: "sm" | "md" | "lg"; hideClose?: boolean }>(
  ({ className, children, size = "md", hideClose, onOpenAutoFocus, ...props }, ref) => (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="ui-overlay" />
      <DialogPrimitive.Content ref={ref} className={cn("ui-dialog", `ui-dialog-${size}`, className)} onOpenAutoFocus={event => { if (onOpenAutoFocus) return onOpenAutoFocus(event); /* focus the dialog itself so no button (and its tooltip) is highlighted on open */ event.preventDefault(); (event.currentTarget as HTMLElement).focus(); }} {...props}>
        {children}
        {!hideClose && <DialogPrimitive.Close className="ui-dialog-close" aria-label="Close"><Icon name="close" /></DialogPrimitive.Close>}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  ),
);
DialogContent.displayName = "DialogContent";

export const DialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn("ui-dialog-header", className)} {...props} />;
export const DialogFooter = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn("ui-dialog-footer", className)} {...props} />;
export const DialogTitle = React.forwardRef<React.ElementRef<typeof DialogPrimitive.Title>, React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>>(({ className, ...props }, ref) => <DialogPrimitive.Title ref={ref} className={cn("ui-dialog-title", className)} {...props} />);
DialogTitle.displayName = "DialogTitle";
export const DialogDescription = React.forwardRef<React.ElementRef<typeof DialogPrimitive.Description>, React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>>(({ className, ...props }, ref) => <DialogPrimitive.Description ref={ref} className={cn("ui-dialog-description", className)} {...props} />);
DialogDescription.displayName = "DialogDescription";
