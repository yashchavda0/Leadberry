"use client";

import * as React from "react";
import * as AlertPrimitive from "@radix-ui/react-alert-dialog";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export const AlertDialog = AlertPrimitive.Root;
export const AlertDialogTrigger = AlertPrimitive.Trigger;

export const AlertDialogContent = React.forwardRef<React.ElementRef<typeof AlertPrimitive.Content>, React.ComponentPropsWithoutRef<typeof AlertPrimitive.Content>>(({ className, ...props }, ref) => (
  <AlertPrimitive.Portal>
    <AlertPrimitive.Overlay className="ui-overlay" />
    <AlertPrimitive.Content ref={ref} className={cn("ui-dialog ui-dialog-sm ui-alert", className)} {...props} />
  </AlertPrimitive.Portal>
));
AlertDialogContent.displayName = "AlertDialogContent";

export const AlertDialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn("ui-dialog-header", className)} {...props} />;
export const AlertDialogFooter = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn("ui-dialog-footer", className)} {...props} />;
export const AlertDialogTitle = React.forwardRef<React.ElementRef<typeof AlertPrimitive.Title>, React.ComponentPropsWithoutRef<typeof AlertPrimitive.Title>>(({ className, ...props }, ref) => <AlertPrimitive.Title ref={ref} className={cn("ui-dialog-title", className)} {...props} />);
AlertDialogTitle.displayName = "AlertDialogTitle";
export const AlertDialogDescription = React.forwardRef<React.ElementRef<typeof AlertPrimitive.Description>, React.ComponentPropsWithoutRef<typeof AlertPrimitive.Description>>(({ className, ...props }, ref) => <AlertPrimitive.Description ref={ref} className={cn("ui-dialog-description", className)} {...props} />);
AlertDialogDescription.displayName = "AlertDialogDescription";
export const AlertDialogAction = React.forwardRef<React.ElementRef<typeof AlertPrimitive.Action>, React.ComponentPropsWithoutRef<typeof AlertPrimitive.Action> & { variant?: "default" | "destructive" }>(({ className, variant = "default", ...props }, ref) => <AlertPrimitive.Action ref={ref} className={cn(buttonVariants({ variant }), className)} {...props} />);
AlertDialogAction.displayName = "AlertDialogAction";
export const AlertDialogCancel = React.forwardRef<React.ElementRef<typeof AlertPrimitive.Cancel>, React.ComponentPropsWithoutRef<typeof AlertPrimitive.Cancel>>(({ className, ...props }, ref) => <AlertPrimitive.Cancel ref={ref} className={cn(buttonVariants({ variant: "outline" }), className)} {...props} />);
AlertDialogCancel.displayName = "AlertDialogCancel";
