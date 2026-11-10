import * as React from "react";
import Icon, { type IconName } from "@/components/Icon";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// KPI tile for dashboards: label, big value, optional trend badge and hint.
export function StatCard({ label, value, icon, delta, trend = "neutral", hint, className }: {
  label: string; value: React.ReactNode; icon?: IconName; delta?: string; trend?: "up" | "down" | "neutral"; hint?: string; className?: string;
}) {
  return <Card className={cn("ui-stat", className)}>
    <div className="ui-stat-top"><span className="ui-stat-label">{label}</span>{icon && <span className="ui-stat-icon"><Icon name={icon} size={18} /></span>}</div>
    <div className="ui-stat-value">{value}</div>
    <div className="ui-stat-foot">
      {delta && <Badge variant={trend === "up" ? "success" : trend === "down" ? "destructive" : "outline"}>{trend === "up" ? "\u25B2 " : trend === "down" ? "\u25BC " : ""}{delta}</Badge>}
      {hint && <span className="small muted">{hint}</span>}
    </div>
  </Card>;
}

// Responsive grid that keeps KPI tiles aligned at any width.
export function StatGrid({ children }: { children: React.ReactNode }) {
  return <div className="ui-stat-grid">{children}</div>;
}
