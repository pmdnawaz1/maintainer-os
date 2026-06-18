export type PRStatus = "open" | "reviewed" | "approved" | "merged" | "closed";

export interface PullRequest {
  id: number;
  github_number: number;
  title: string;
  body?: string | null;
  status: PRStatus;
  review_feedback?: string | null;
  created_at: string;
}
