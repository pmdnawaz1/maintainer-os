import { tool } from "@langchain/core/tools";
import neo4j, { Driver } from "neo4j-driver";
import { QdrantClient } from "@qdrant/js-client-rest";
import { z } from "zod";

const COLLECTION = "maintainer_memory";

export function createMemoryTools(neo4jDriver: Driver, qdrant: QdrantClient) {
  const searchMemory = tool(
    async ({ query, limit }) => {
      // Placeholder: embed query and search Qdrant
      // In production, call OpenAI embeddings API here
      const results = await qdrant.search(COLLECTION, {
        vector: new Array(1536).fill(0), // replace with real embedding
        limit,
        with_payload: true,
      });
      return JSON.stringify(results.map((r) => r.payload));
    },
    {
      name: "search_project_memory",
      description: "Search project memory (architecture decisions, past bugs, coding standards)",
      schema: z.object({
        query: z.string().describe("Natural language query"),
        limit: z.number().default(5),
      }),
    }
  );

  const storeMemory = tool(
    async ({ content, type, tags }) => {
      const session = neo4jDriver.session();
      try {
        await session.run(
          `CREATE (m:Memory {content: $content, type: $type, tags: $tags, createdAt: datetime()})`,
          { content, type, tags }
        );
        return "Memory stored in Neo4j";
      } finally {
        await session.close();
      }
    },
    {
      name: "store_project_memory",
      description: "Store an important finding (architecture decision, bug root cause, coding standard)",
      schema: z.object({
        content: z.string(),
        type: z.enum(["decision", "bug", "standard", "context"]),
        tags: z.array(z.string()).default([]),
      }),
    }
  );

  return { searchMemory, storeMemory };
}
