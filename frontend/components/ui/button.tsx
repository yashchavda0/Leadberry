import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

export const buttonVariants = cva("ui-btn", {
  variants: {
    variant: { default: "ui-btn-default", secondary: "ui-btn-secondary", outline: "ui-btn-outline", ghost: "ui-btn-ghost", destructive: "ui-btn-destructive", link: "ui-btn-link" },
    size: { default: "", sm: "ui-btn-sm", lg: "ui-btn-lg", icon: "ui-btn-icon" },
  },
  defaultVariants: { variant: "default", size: "default" },
});

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> { asChild?: boolean }

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild = false, type, ...props }, ref) => {
  const Component = asChild ? Slot : "button";
  return <Component ref={ref} type={asChild ? undefined : type ?? "button"} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
});
Button.displayName = "Button";
