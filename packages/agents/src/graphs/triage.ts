import { ChatAnthropic } from "@langchain/anthropic";
import { StateGraph, END } from "@langchain/langgraph";
import type { RunnableConfig } from "@langchain/core/runnables";
import { TriageState, TriageStateType } from "../state";

const TRIAGE_LABELS = ["bug", "feature", "documentation", "question", "duplicate", "security", "wontfix"];

const TRIAGE_PROMPT = (state: TriageStateType) => `You are an expert open-source maintainer triaging a GitHub issue.

Repository: ${state.repoFullName}
Issue #${state.issueNumber}: ${state.issueTitle}
Body: ${state.issueBody}

${state.memoryContext ? `Project context from memory:\n${state.memoryContext}` : ""}

Tasks:
1. Classify this issue with ONE label from: ${TRIAGE_LABELS.join(", ")}
2. Write a helpful, friendly response (1-3 sentences) for the issue author.

Respond in JSON:
{
  "label": "<one of the labels>",
  "response": "<your response to the author>"
}`;

async function fetchMemoryNode(
  state: TriageStateType,
  config?: RunnableConfig,
): Promise<Partial<TriageStateType>> {
  const searchMemory = config?.configurable?.searchMemory as
    | ((args: { query: string; limit: number }) => Promise<string>)
    | undefined;

  if (!searchMemory) return { memoryContext: null };

  try {
    const query = `${state.issueTitle}\n${state.issueBody ?? ""}`.slice(0, 500);
    const raw = await searchMemory({ query, limit: 3 });
    const results = JSON.parse(raw) as Array<{ payload: { content: string } }>;
    const context = results.map((r) => r.payload.content).filter(Boolean).join("\n\n");
    return { memoryContext: context || null };
  } catch {
    return { memoryContext: null };
  }
}

async function classifyNode(state: TriageStateType): Promise<Partial<TriageStateType>> {
  const model = new ChatAnthropic({
    model: "claude-haiku-4-5-20251001",
    temperature: 0,
  });

  const response = await model.invoke(TRIAGE_PROMPT(state));
  const content = response.content as string;

  try {
    const parsed = JSON.parse(content);
    return {
      label: parsed.label,
      suggestedResponse: parsed.response,
    };
  } catch {
    return {
      label: "question",
      suggestedResponse: "Thank you for opening this issue! We'll look into it shortly.",
    };
  }
}

export async function buildTriageGraph(withCheckpointer = false) {
  const graph = new StateGraph(TriageState)
    .addNode("fetch_memory", fetchMemoryNode)
    .addNode("classify", classifyNode)
    .addEdge("__start__", "fetch_memory")
    .addEdge("fetch_memory", "classify")
    .addEdge("classify", END);

  if (withCheckpointer) {
    const { getCheckpointer } = await import("../checkpointer");
    const checkpointer = await getCheckpointer();
    return graph.compile({ checkpointer });
  }
  return graph.compile();
}
