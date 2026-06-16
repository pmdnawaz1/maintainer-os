import { ChatAnthropic } from "@langchain/anthropic";
import { StateGraph, END } from "@langchain/langgraph";
import { ReviewState, ReviewStateType } from "../state";

const REVIEW_PROMPT = (state: ReviewStateType) => `You are a senior software engineer reviewing a GitHub pull request.

Repository: ${state.repoFullName}
PR #${state.prNumber}: ${state.prTitle}
Description: ${state.prBody}

${state.memoryContext ? `Project standards from memory:\n${state.memoryContext}` : ""}

Diff:
\`\`\`diff
${state.diff.slice(0, 8000)}
\`\`\`

Review for:
1. Correctness and logic errors
2. Security vulnerabilities (injection, auth bypass, data exposure)
3. Performance concerns
4. Adherence to project coding standards

Respond in JSON:
{
  "feedback": "<detailed, actionable review with line references>",
  "approved": <true if low-risk, false if changes required>,
  "security_issues": ["<issue1>", "<issue2>"] // empty array if none
}`;

async function fetchMemoryNode(state: ReviewStateType): Promise<Partial<ReviewStateType>> {
  return { memoryContext: null };
}

async function reviewNode(state: ReviewStateType): Promise<Partial<ReviewStateType>> {
  const model = new ChatAnthropic({
    model: "claude-sonnet-4-6",
    temperature: 0,
  });

  const response = await model.invoke(REVIEW_PROMPT(state));
  const content = response.content as string;

  try {
    const parsed = JSON.parse(content);
    return {
      feedback: parsed.feedback,
      approved: parsed.approved,
      securityIssues: parsed.security_issues ?? [],
    };
  } catch {
    return {
      feedback: "Unable to generate automated review. Please review manually.",
      approved: false,
      securityIssues: [],
    };
  }
}

export async function buildReviewGraph(withCheckpointer = false) {
  const graph = new StateGraph(ReviewState)
    .addNode("fetch_memory", fetchMemoryNode)
    .addNode("review", reviewNode)
    .addEdge("__start__", "fetch_memory")
    .addEdge("fetch_memory", "review")
    .addEdge("review", END);

  if (withCheckpointer) {
    const { getCheckpointer } = await import("../checkpointer");
    const checkpointer = await getCheckpointer();
    return graph.compile({ checkpointer });
  }
  return graph.compile();
}
