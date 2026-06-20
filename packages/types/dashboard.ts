export interface DashboardStats {
  open_issues: number;
  triaged_issues: number;
  open_prs: number;
  repositories: number;
}

export type ActivityType = "issue" | "pull_request";

export interface ActivityItem {
  id: number;
  type: ActivityType;
  title: string;
  repo: string;
  status: string;
  created_at: string;
}
