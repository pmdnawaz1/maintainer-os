/**
 * LangGraph Postgres checkpointer for stateful, resumable agent runs.
 * Stores graph state in the same Postgres instance as the rest of the app.
 * Enables human-in-the-loop pauses and crash recovery.
 */

import { PostgresSaver } from "@langchain/langgraph-checkpoint-postgres";

let _checkpointer: PostgresSaver | null = null;

export async function getCheckpointer(): Promise<PostgresSaver> {
  if (_checkpointer) return _checkpointer;

  const dbUrl = process.env.DATABASE_URL;
  if (!dbUrl) throw new Error("DATABASE_URL env var required for checkpointer");

  // Strip SQLAlchemy driver prefix (e.g. postgresql+asyncpg://) → postgresql://
  const pgUrl = dbUrl.replace(/^postgresql\+\w+:\/\//, "postgresql://");
  _checkpointer = PostgresSaver.fromConnString(pgUrl);
  await _checkpointer.setup(); // creates langgraph_checkpoints table if absent
  return _checkpointer;
}
