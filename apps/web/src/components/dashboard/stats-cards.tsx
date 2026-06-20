"use client";

import { AlertCircle, CheckCircle2, CircleDot, GitPullRequest, LayoutDashboard } from "lucide-react";
import { useDashboardStats } from "@/lib/use-api-hooks";
import { Skeleton } from "@/components/ui/skeleton";
import type { DashboardStats } from "@maintainer-os/types";

const STAT_DEFS: {
  key: keyof DashboardStats;
  label: string;
  icon: React.ElementType;
  description: string;
}[] = [
  { key: "open_issues",    label: "Open Issues",  icon: CircleDot,       description: "Auto-triaged by AI" },
  { key: "open_prs",       label: "Open PRs",     icon: GitPullRequest,  description: "Pending review" },
  { key: "repositories",   label: "Repositories", icon: LayoutDashboard, description: "Connected" },
  { key: "triaged_issues", label: "Triaged",      icon: CheckCircle2,    description: "Issues triaged" },
];

function StatCardSkeleton() {
  return (
    <div className="rounded-lg border bg-card p-6 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-4 w-4 rounded-full" />
      </div>
      <Skeleton className="h-8 w-12 mt-1" />
      <Skeleton className="h-3 w-24 mt-2" />
    </div>
  );
}

export function StatsCards() {
  const { data: stats, isLoading, isError } = useDashboardStats();

  if (isLoading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {STAT_DEFS.map(({ label }) => <StatCardSkeleton key={label} />)}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 flex items-center gap-2 text-destructive text-sm">
        <AlertCircle className="h-4 w-4 shrink-0" />
        Failed to load dashboard stats. Retrying automatically.
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {STAT_DEFS.map(({ key, label, icon: Icon, description }) => (
        <div key={label} className="rounded-lg border bg-card p-6 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-muted-foreground">{label}</span>
            <Icon className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="text-2xl font-bold">{stats?.[key] ?? "—"}</div>
          <p className="text-xs text-muted-foreground mt-1">{description}</p>
        </div>
      ))}
    </div>
  );
}
