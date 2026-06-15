import { CircleDot, GitPullRequest, BookOpen, CheckCircle2 } from "lucide-react";

const stats = [
  {
    label: "Open Issues",
    value: "—",
    icon: CircleDot,
    description: "Auto-triaged by AI",
  },
  {
    label: "Open PRs",
    value: "—",
    icon: GitPullRequest,
    description: "Pending review",
  },
  {
    label: "Docs Updated",
    value: "—",
    icon: BookOpen,
    description: "This week",
  },
  {
    label: "Actions Taken",
    value: "—",
    icon: CheckCircle2,
    description: "Last 24 hours",
  },
];

export function StatsCards() {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      {stats.map(({ label, value, icon: Icon, description }) => (
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
