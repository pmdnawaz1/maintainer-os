export type IssueStatus = "open" | "triaged" | "resolved" | "closed";

export interface Issue {
  id: number;
  github_number: number;
  title: string;
  body?: string | null;
  status: IssueStatus;
  triage_label: string | null;
  ai_response?: string | null;
  created_at: string;
}
