import * as React from "react";
import { cn } from "@/lib/utils";

type DivProps = React.HTMLAttributes<HTMLDivElement>;

export const Card = ({ className, ...props }: DivProps) => <div className={cn("ui-card", className)} {...props} />;
export const CardHeader = ({ className, ...props }: DivProps) => <div className={cn("ui-card-header", className)} {...props} />;
export const CardTitle = ({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) => <h3 className={cn("ui-card-title", className)} {...props} />;
export const CardDescription = ({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) => <p className={cn("ui-card-description", className)} {...props} />;
export const CardAction = ({ className, ...props }: DivProps) => <div className={cn("ui-card-action", className)} {...props} />;
export const CardContent = ({ className, ...props }: DivProps) => <div className={cn("ui-card-content", className)} {...props} />;
export const CardFooter = ({ className, ...props }: DivProps) => <div className={cn("ui-card-footer", className)} {...props} />;
