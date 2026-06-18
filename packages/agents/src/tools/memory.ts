import { tool } from "@langchain/core/tools";
import neo4j, { Driver } from "neo4j-driver";
import { QdrantClient } from "@qdrant/js-client-rest";
import { z } from "zod";
import type { Issue, PullRequest, Repository } from "@maintainer-os/types";

type MemoryPayload = {
  content: string;
  type: string;
  tags: string[];
  issue?: Pick<Issue, "id" | "github_number" | "title" | "status">;
  pull_request?: Pick<PullRequest, "id" | "github_number" | "title" | "status">;
  repository?: Pick<Repository, "full_name">;
};

const COLLECTION = "maintainer_memory";
const VECTOR_SIZE = 1536;
const DEFAULT_SCORE_THRESHOLD = 0.70;
const HNSW_EF = 128;

export function createMemoryTools(neo4jDriver: Driver, qdrant: QdrantClient, embedFn: (text: string) => Promise<number[]>) {
  const searchMemory = tool(
    async ({ query, limit, filters, score_threshold }) => {
      const vector = await embedFn(query);
      if (vector.length !== VECTOR_SIZE) {
        throw new Error(`Embedding must be ${VECTOR_SIZE}-dim, got ${vector.length}`);
      }

      const searchParams: Record<string, unknown> = {
        vector,
        limit,
        with_payload: true,
        params: { hnsw_ef: HNSW_EF },
        score_threshold: score_threshold ?? DEFAULT_SCORE_THRESHOLD,
      };

      if (filters && Object.keys(filters).length > 0) {
        searchParams.filter = {
          must: Object.entries(filters).map(([key, value]) => ({
            key,
            match: { value },
          })),
        };
      }

      const results = await qdrant.search(COLLECTION, searchParams as Parameters<typeof qdrant.search>[1]);
      return JSON.stringify(
        results.map((r) => ({ id: r.id, score: r.score, payload: r.payload }))
      );
    },
    {
      name: "search_project_memory",
      description: "Semantic search over project memory (architecture decisions, past bugs, coding standards, project taste)",
      schema: z.object({
        query: z.string().describe("Natural language query"),
        limit: z.number().default(5),
        filters: z.record(z.string()).optional().describe("Exact-match payload filters e.g. {type: 'decision'}"),
        score_threshold: z.number().optional().describe("Minimum cosine similarity (0-1). Defaults to 0.70"),
      }),
    }
  );

  const storeMemory = tool(
    async ({ content, type, tags, vector }) => {
      if (vector.length !== VECTOR_SIZE) {
        throw new Error(`Vector must be ${VECTOR_SIZE}-dim, got ${vector.length}`);
      }

      // Store in Neo4j knowledge graph
      const session = neo4jDriver.session();
      try {
        await session.run(
          `CREATE (m:Memory {
            content: $content, type: $type, tags: $tags, createdAt: datetime()
          })`,
          { content, type, tags }
        );
      } finally {
        await session.close();
      }

      // Store vector in Qdrant
      const pointId = Math.abs(
        Array.from(content).reduce((h, c) => (Math.imul(31, h) + c.charCodeAt(0)) | 0, 0)
      );
      const payload: MemoryPayload = { content, type, tags };
      await qdrant.upsert(COLLECTION, {
        points: [{ id: pointId, vector, payload }],
      });

      return `Memory stored — Neo4j node created, Qdrant point ${pointId} upserted`;
    },
    {
      name: "store_project_memory",
      description: "Store an important finding with its embedding. Writes to both Neo4j (graph) and Qdrant (vector).",
      schema: z.object({
        content: z.string(),
        type: z.enum(["decision", "bug", "standard", "context", "antipattern"]),
        tags: z.array(z.string()).default([]),
        vector: z.array(z.number()).length(VECTOR_SIZE).describe("1536-dim embedding of content"),
      }),
    }
  );

  const findRelatedDecisions = tool(
    async ({ file_paths }) => {
      const session = neo4jDriver.session();
      try {
        const result = await session.run(
          `UNWIND $paths AS path
           MATCH (f:File {path: path})-[:GOVERNED_BY]->(d:Decision)
           RETURN DISTINCT d.id AS id, d.title AS title, d.decision AS decision, d.status AS status
           ORDER BY d.created_at DESC`,
          { paths: file_paths }
        );
        return JSON.stringify(result.records.map((r) => r.toObject()));
      } finally {
        await session.close();
      }
    },
    {
      name: "find_related_decisions",
      description: "Find architecture decisions that govern the given files (useful during PR review)",
      schema: z.object({
        file_paths: z.array(z.string()).describe("List of file paths changed in the PR"),
      }),
    }
  );

  return { searchMemory, storeMemory, findRelatedDecisions };
}
