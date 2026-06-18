import { Annotation } from "@langchain/langgraph";
import type { IssueStatus, PRStatus } from "@maintainer-os/types";

export const TriageState = Annotation.Root({
  repoFullName: Annotation<string>(),
  issueNumber: Annotation<number>(),
  issueTitle: Annotation<string>(),
  issueBody: Annotation<string>(),
  label: Annotation<IssueStatus | null>({ default: () => null, reducer: (_, b) => b }),
  suggestedResponse: Annotation<string | null>({ default: () => null, reducer: (_, b) => b }),
  relatedIssues: Annotation<number[]>({ default: () => [], reducer: (_, b) => b }),
  memoryContext: Annotation<string | null>({ default: () => null, reducer: (_, b) => b }),
});

export const ReviewState = Annotation.Root({
  repoFullName: Annotation<string>(),
  prNumber: Annotation<number>(),
  prTitle: Annotation<string>(),
  prBody: Annotation<string>(),
  diff: Annotation<string>(),
  feedback: Annotation<string | null>({ default: () => null, reducer: (_, b) => b }),
  approved: Annotation<boolean | null>({ default: () => null, reducer: (_, b) => b }),
  prStatus: Annotation<PRStatus | null>({ default: () => null, reducer: (_, b) => b }),
  securityIssues: Annotation<string[]>({ default: () => [], reducer: (_, b) => b }),
  memoryContext: Annotation<string | null>({ default: () => null, reducer: (_, b) => b }),
});

export type TriageStateType = typeof TriageState.State;
export type ReviewStateType = typeof ReviewState.State;
