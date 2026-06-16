import { tool } from "@langchain/core/tools";
import { Octokit } from "octokit";
import { z } from "zod";

export function createGitHubTools(octokit: Octokit) {
  const getIssue = tool(
    async ({ owner, repo, issue_number }) => {
      const { data } = await octokit.rest.issues.get({ owner, repo, issue_number });
      return JSON.stringify({ title: data.title, body: data.body, labels: data.labels });
    },
    {
      name: "get_github_issue",
      description: "Fetch a GitHub issue by number",
      schema: z.object({
        owner: z.string(),
        repo: z.string(),
        issue_number: z.number(),
      }),
    }
  );

  const addLabel = tool(
    async ({ owner, repo, issue_number, labels }) => {
      await octokit.rest.issues.addLabels({ owner, repo, issue_number, labels });
      return `Labels added: ${labels.join(", ")}`;
    },
    {
      name: "add_github_label",
      description: "Add labels to a GitHub issue or PR",
      schema: z.object({
        owner: z.string(),
        repo: z.string(),
        issue_number: z.number(),
        labels: z.array(z.string()),
      }),
    }
  );

  const postComment = tool(
    async ({ owner, repo, issue_number, body }) => {
      await octokit.rest.issues.createComment({ owner, repo, issue_number, body });
      return "Comment posted";
    },
    {
      name: "post_github_comment",
      description: "Post a comment on a GitHub issue or PR",
      schema: z.object({
        owner: z.string(),
        repo: z.string(),
        issue_number: z.number(),
        body: z.string(),
      }),
    }
  );

  const getPRDiff = tool(
    async ({ owner, repo, pull_number }) => {
      const { data } = await octokit.rest.pulls.get({
        owner, repo, pull_number,
        mediaType: { format: "diff" },
      });
      return data as unknown as string;
    },
    {
      name: "get_pr_diff",
      description: "Fetch the diff of a pull request",
      schema: z.object({
        owner: z.string(),
        repo: z.string(),
        pull_number: z.number(),
      }),
    }
  );

  return { getIssue, addLabel, postComment, getPRDiff };
}
