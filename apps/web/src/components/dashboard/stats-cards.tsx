"use client";

import { CheckCircle2, CircleDot, GitPullRequest, LayoutDashboard } from "lucide-react";
import { useDashboardStats } from "@/lib/use-api-hooks";

export function StatsCards() {
  const { data: stats, isLoading } = useDashboardStats();

  const val = (n: number | undefined) => (isLoading ? "…" : String(n ?? "—"));

  const items = [
    {
      label: "Open Issues",
      value: val(stats?.open_issues),
      icon: CircleDot,
      description: "Auto-triaged by AI",
    },
    {
      label: "Open PRs",
      value: val(stats?.open_prs),
      icon: GitPullRequest,
      description: "Pending review",
    },
    {
      label: "Repositories",
      value: val(stats?.repositories),
      icon: LayoutDashboard,
      description: "Connected",
    },
    {
      label: "Triaged",
      value: val(stats?.triaged_issues),
      icon: CheckCircle2,
      description: "Issues triaged",
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {items.map(({ label, value, icon: Icon, description }) => (
        <div key={label} className="rounded-lg border bg-card p-6 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-muted-foreground">{label}</span>
            <Icon className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="text-2xl font-bold">{value}</div>
          <p className="text-xs text-muted-foreground mt-1">{description}</p>
        </div>
      ))}
    </div>
  );
}
