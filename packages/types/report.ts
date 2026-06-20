export interface WeeklyReportContributor {
  login: string;
  contributions: number;
}

export interface WeeklyReportGithubStats {
  stars: number;
  forks: number;
  watchers: number;
  open_issues_github: number;
  top_contributors: WeeklyReportContributor[];
}

export interface WeeklyReportData {
  repository: string;
  week_start: string;
  week_end: string;
  issues: {
    total_open: number;
    triaged: number;
    new_this_week: number;
    closed_this_week: number;
  };
  pull_requests: {
    total_open: number;
    new_this_week: number;
    merged_this_week: number;
    reviewed_this_week: number;
  };
  github?: WeeklyReportGithubStats;
}

export interface WeeklyReport {
  id: number;
  repository: string;
  week_start: string;
  week_end: string;
  report: WeeklyReportData;
  markdown: string;
  created_at: string;
}
