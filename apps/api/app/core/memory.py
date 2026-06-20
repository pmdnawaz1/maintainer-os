"""Neo4j (knowledge graph) and Qdrant (vector) memory layer for Maintainer OS."""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    HnswConfigDiff,
    MatchValue,
    OptimizersConfigDiff,
    PointStruct,
    SearchRequest,
    VectorParams,
)

from app.core.config import settings

log = structlog.get_logger()

# ─── Singletons ──────────────────────────────────────────────────────────────

_neo4j_driver: AsyncDriver | None = None
_qdrant_client: AsyncQdrantClient | None = None

COLLECTION_NAME = "maintainer_memory"
VECTOR_SIZE = 1536  # text-embedding-3-small / ada-002


def get_neo4j() -> AsyncDriver:
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _neo4j_driver


def get_qdrant() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )
    return _qdrant_client


# ─── Neo4j: Schema setup ─────────────────────────────────────────────────────

async def define_adr_schema(driver: AsyncDriver) -> None:
    """Create constraints and indexes for Architecture Decision Record nodes."""
    async with driver.session() as session:
        await session.run(
            "CREATE CONSTRAINT decision_id IF NOT EXISTS "
            "FOR (d:Decision) REQUIRE d.id IS UNIQUE"
        )
        await session.run(
            "CREATE INDEX decision_status IF NOT EXISTS "
            "FOR (d:Decision) ON (d.status)"
        )
        await session.run(
            "CREATE INDEX decision_created IF NOT EXISTS "
            "FOR (d:Decision) ON (d.created_at)"
        )


async def define_code_schema(driver: AsyncDriver) -> None:
    """Create constraints and indexes for File and Class relationship nodes."""
    async with driver.session() as session:
        await session.run(
            "CREATE CONSTRAINT file_path IF NOT EXISTS "
            "FOR (f:File) REQUIRE f.path IS UNIQUE"
        )
        await session.run(
            "CREATE CONSTRAINT class_fqn IF NOT EXISTS "
            "FOR (c:Class) REQUIRE c.fqn IS UNIQUE"
        )
        await session.run(
            "CREATE INDEX file_language IF NOT EXISTS "
            "FOR (f:File) ON (f.language)"
        )


async def define_taste_schema(driver: AsyncDriver) -> None:
    """Create constraints for project taste nodes (coding standards, patterns)."""
    async with driver.session() as session:
        await session.run(
            "CREATE CONSTRAINT standard_id IF NOT EXISTS "
            "FOR (s:CodingStandard) REQUIRE s.id IS UNIQUE"
        )
        await session.run(
            "CREATE CONSTRAINT pattern_id IF NOT EXISTS "
            "FOR (p:PreferredPattern) REQUIRE p.id IS UNIQUE"
        )
        await session.run(
            "CREATE CONSTRAINT antipattern_id IF NOT EXISTS "
            "FOR (a:AntiPattern) REQUIRE a.id IS UNIQUE"
        )


async def seed_initial_graph(driver: AsyncDriver) -> None:
    """Seed the graph with the project's base architecture decisions and standards."""
    async with driver.session() as session:
        # Core ADR: tech stack decision
        await session.run(
            """
            MERGE (d:Decision {id: 'adr-001'})
            ON CREATE SET
              d.title       = 'Core Tech Stack',
              d.status      = 'accepted',
              d.context     = 'Need a full-stack AI system for OSS maintenance',
              d.decision    = 'Next.js 15 + FastAPI + LangGraph + Neo4j + Qdrant + Postgres',
              d.consequences = 'Polyglot stack; strong separation between orchestration and storage',
              d.created_at  = datetime()
            """,
        )
        # Coding standard: async-first
        await session.run(
            """
            MERGE (s:CodingStandard {id: 'std-001'})
            ON CREATE SET
              s.name        = 'Async-first Python',
              s.description = 'All I/O in FastAPI handlers and services must be async',
              s.created_at  = datetime()
            """,
        )
        # Anti-pattern: sync calls in async context
        await session.run(
            """
            MERGE (a:AntiPattern {id: 'ap-001'})
            ON CREATE SET
              a.name        = 'Blocking sync call in async handler',
              a.description = 'Never call synchronous blocking code inside async FastAPI routes',
              a.created_at  = datetime()
            """,
        )
        log.info("neo4j_graph_seeded")


async def ensure_neo4j_schema() -> None:
    """Run all schema setup in order. Safe to call on every startup (idempotent)."""
    driver = get_neo4j()
    await define_adr_schema(driver)
    await define_code_schema(driver)
    await define_taste_schema(driver)
    await seed_initial_graph(driver)
    log.info("neo4j_schema_ready")


# ─── Neo4j: Query helpers ────────────────────────────────────────────────────

async def find_related_decisions_for_pr(
    changed_files: list[str],
) -> list[dict[str, Any]]:
    """Return ADRs that govern files changed in a PR.

    Traversal: File → [:GOVERNED_BY] → Decision
    """
    driver = get_neo4j()
    async with driver.session() as session:
        result = await session.run(
            """
            UNWIND $paths AS path
            MATCH (f:File {path: path})-[:GOVERNED_BY]->(d:Decision)
            RETURN DISTINCT d.id AS id, d.title AS title,
                   d.decision AS decision, d.status AS status
            ORDER BY d.created_at DESC
            """,
            paths=changed_files,
        )
        return [dict(record) async for record in result]


async def get_files_affected_by_change(file_path: str, depth: int = 2) -> list[str]:
    """Return files that import/use the given file, up to `depth` hops away."""
    driver = get_neo4j()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (origin:File {path: $path})
            CALL apoc.path.subgraphNodes(origin, {
              relationshipFilter: '<IMPORTS|<USES',
              maxLevel: $depth
            }) YIELD node AS f
            WHERE f <> origin
            RETURN f.path AS path
            ORDER BY f.path
            """,
            path=file_path,
            depth=depth,
        )
        return [record["path"] async for record in result]


async def store_decision(
    title: str,
    context: str,
    decision: str,
    consequences: str = "",
    status: str = "accepted",
    related_files: list[str] | None = None,
) -> str:
    """Persist an ADR to Neo4j and wire it to any relevant File nodes."""
    driver = get_neo4j()
    decision_id = f"adr-{uuid.uuid4().hex[:8]}"
    async with driver.session() as session:
        await session.run(
            """
            CREATE (d:Decision {
              id: $id, title: $title, status: $status,
              context: $context, decision: $decision,
              consequences: $consequences, created_at: datetime()
            })
            """,
            id=decision_id,
            title=title,
            status=status,
            context=context,
            decision=decision,
            consequences=consequences,
        )
        for path in (related_files or []):
            await session.run(
                """
                MERGE (f:File {path: $path})
                WITH f
                MATCH (d:Decision {id: $did})
                MERGE (f)-[:GOVERNED_BY]->(d)
                """,
                path=path,
                did=decision_id,
            )
    log.info("decision_stored", id=decision_id, title=title)
    return decision_id


# ─── Qdrant: Collection setup ────────────────────────────────────────────────

async def ensure_qdrant_collection() -> None:
    """Create the vector collection with tuned HNSW params if it doesn't exist."""
    client = get_qdrant()
    collections = await client.get_collections()
    names = [c.name for c in collections.collections]
    if COLLECTION_NAME not in names:
        await client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
                on_disk=False,
            ),
            hnsw_config=HnswConfigDiff(
                m=settings.qdrant_hnsw_m,
                ef_construct=settings.qdrant_hnsw_ef_construct,
                full_scan_threshold=10_000,
                on_disk=False,
            ),
            optimizers_config=OptimizersConfigDiff(
                indexing_threshold=20_000,
            ),
        )
        log.info("qdrant_collection_created", name=COLLECTION_NAME)
    else:
        # Update HNSW params on existing collection without recreating it
        await client.update_collection(
            collection_name=COLLECTION_NAME,
            hnsw_config=HnswConfigDiff(
                m=settings.qdrant_hnsw_m,
                ef_construct=settings.qdrant_hnsw_ef_construct,
            ),
        )


# ─── Qdrant: TTL search cache ────────────────────────────────────────────────

_search_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _cache_key(query_vector: list[float], filters: dict | None, limit: int) -> str:
    payload = f"{query_vector[:8]}|{filters}|{limit}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_cached(key: str) -> list[dict[str, Any]] | None:
    entry = _search_cache.get(key)
    if entry and (time.monotonic() - entry[0]) < settings.qdrant_cache_ttl:
        return entry[1]
    _search_cache.pop(key, None)
    return None


def _set_cached(key: str, results: list[dict[str, Any]]) -> None:
    _search_cache[key] = (time.monotonic(), results)


# ─── Qdrant: Search & upsert ─────────────────────────────────────────────────

def _validate_vector(vector: list[float]) -> None:
    if len(vector) != VECTOR_SIZE:
        raise ValueError(f"Expected {VECTOR_SIZE}-dim vector, got {len(vector)}")


async def search_vectors(
    query_vector: list[float],
    limit: int = 5,
    filters: dict[str, Any] | None = None,
    score_threshold: float | None = None,
) -> list[dict[str, Any]]:
    """Semantic search with caching, filtering, and score thresholding."""
    _validate_vector(query_vector)

    cache_key = _cache_key(query_vector, filters, limit)
    cached = _get_cached(cache_key)
    if cached is not None:
        log.debug("qdrant_cache_hit", key=cache_key[:8])
        return cached

    client = get_qdrant()
    threshold = score_threshold if score_threshold is not None else settings.qdrant_score_threshold

    qdrant_filter: Filter | None = None
    if filters:
        qdrant_filter = Filter(
            must=[
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filters.items()
            ]
        )

    hits = await client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=limit,
        query_filter=qdrant_filter,
        score_threshold=threshold,
        search_params={"hnsw_ef": settings.qdrant_search_ef},
        with_payload=True,
    )

    results = [
        {"id": str(h.id), "score": h.score, "payload": h.payload}
        for h in hits
    ]
    _set_cached(cache_key, results)
    return results


async def batch_upsert_vectors(
    points: list[dict[str, Any]],
    batch_size: int = 100,
) -> None:
    """Bulk-insert vectors into Qdrant in batches.

    Each point must have: id (str|int), vector (list[float]), payload (dict).
    """
    client = get_qdrant()
    for i in range(0, len(points), batch_size):
        chunk = points[i : i + batch_size]
        structs: list[PointStruct] = []
        for p in chunk:
            _validate_vector(p["vector"])
            structs.append(
                PointStruct(
                    id=p["id"] if isinstance(p["id"], int) else uuid.uuid5(uuid.NAMESPACE_URL, str(p["id"])).int >> 64,
                    vector=p["vector"],
                    payload=p.get("payload", {}),
                )
            )
        await client.upsert(collection_name=COLLECTION_NAME, points=structs)
        log.info("qdrant_batch_upserted", batch=i // batch_size + 1, count=len(structs))


async def upsert_memory(
    content: str,
    vector: list[float],
    memory_type: str,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Store a single memory chunk with full payload."""
    _validate_vector(vector)
    point_id = uuid.uuid4()
    client = get_qdrant()
    await client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=point_id.int >> 64,
                vector=vector,
                payload={
                    "content": content,
                    "type": memory_type,
                    "tags": tags or [],
                    **(metadata or {}),
                },
            )
        ],
    )
    return str(point_id)


# ─── Postgres pgvector: hybrid search ────────────────────────────────────────

async def hybrid_search_issues(
    db: Any,  # AsyncSession — imported lazily to avoid circular dep
    query: str,
    query_vector: list[float] | None = None,
    limit: int = 10,
    search_type: str = "hybrid",
) -> list[dict[str, Any]]:
    """Search Issues by keyword, semantic (pgvector), or hybrid (RRF) strategy."""
    from sqlalchemy import func, select
    from app.db.models import Issue

    if search_type == "keyword" or query_vector is None:
        tsq = func.plainto_tsquery("english", query)
        tsv = func.to_tsvector("english", func.concat(Issue.title, " ", func.coalesce(Issue.body, "")))
        stmt = (
            select(Issue)
            .where(tsv.op("@@")(tsq))
            .order_by(func.ts_rank(tsv, tsq).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        issues = result.scalars().all()

    elif search_type == "semantic":
        _validate_vector(query_vector)
        stmt = (
            select(Issue)
            .where(Issue.embedding.is_not(None))
            .order_by(Issue.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        result = await db.execute(stmt)
        issues = result.scalars().all()

    else:  # hybrid: Reciprocal Rank Fusion of semantic + keyword results
        _validate_vector(query_vector)
        sem_stmt = (
            select(Issue)
            .where(Issue.embedding.is_not(None))
            .order_by(Issue.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        tsq = func.plainto_tsquery("english", query)
        tsv = func.to_tsvector("english", func.concat(Issue.title, " ", func.coalesce(Issue.body, "")))
        kw_stmt = (
            select(Issue)
            .where(tsv.op("@@")(tsq))
            .order_by(func.ts_rank(tsv, tsq).desc())
            .limit(limit)
        )
        sem_result = await db.execute(sem_stmt)
        kw_result = await db.execute(kw_stmt)

        rrf_k = 60
        scores: dict[int, float] = {}
        items: dict[int, Any] = {}
        for rank, item in enumerate(sem_result.scalars().all()):
            scores[item.id] = scores.get(item.id, 0.0) + 1.0 / (rrf_k + rank + 1)
            items[item.id] = item
        for rank, item in enumerate(kw_result.scalars().all()):
            scores[item.id] = scores.get(item.id, 0.0) + 1.0 / (rrf_k + rank + 1)
            items[item.id] = item

        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[:limit]
        return [
            {
                "id": items[i].id,
                "github_number": items[i].github_number,
                "title": items[i].title,
                "status": items[i].status,
            }
            for i in sorted_ids
        ]

    return [
        {
            "id": i.id,
            "github_number": i.github_number,
            "title": i.title,
            "status": i.status,
        }
        for i in issues
    ]


async def hybrid_search_pull_requests(
    db: Any,  # AsyncSession — imported lazily to avoid circular dep
    query: str,
    query_vector: list[float] | None = None,
    limit: int = 10,
    search_type: str = "hybrid",
) -> list[dict[str, Any]]:
    """Search PullRequests by keyword, semantic (pgvector), or hybrid (RRF) strategy."""
    from sqlalchemy import func, select
    from app.db.models import PullRequest

    if search_type == "keyword" or query_vector is None:
        tsq = func.plainto_tsquery("english", query)
        tsv = func.to_tsvector("english", func.concat(PullRequest.title, " ", func.coalesce(PullRequest.body, "")))
        stmt = (
            select(PullRequest)
            .where(tsv.op("@@")(tsq))
            .order_by(func.ts_rank(tsv, tsq).desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        prs = result.scalars().all()

    elif search_type == "semantic":
        _validate_vector(query_vector)
        stmt = (
            select(PullRequest)
            .where(PullRequest.embedding.is_not(None))
            .order_by(PullRequest.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        result = await db.execute(stmt)
        prs = result.scalars().all()

    else:  # hybrid: Reciprocal Rank Fusion of semantic + keyword results
        _validate_vector(query_vector)
        sem_stmt = (
            select(PullRequest)
            .where(PullRequest.embedding.is_not(None))
            .order_by(PullRequest.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        tsq = func.plainto_tsquery("english", query)
        tsv = func.to_tsvector("english", func.concat(PullRequest.title, " ", func.coalesce(PullRequest.body, "")))
        kw_stmt = (
            select(PullRequest)
            .where(tsv.op("@@")(tsq))
            .order_by(func.ts_rank(tsv, tsq).desc())
            .limit(limit)
        )
        sem_result = await db.execute(sem_stmt)
        kw_result = await db.execute(kw_stmt)

        rrf_k = 60
        scores: dict[int, float] = {}
        items: dict[int, Any] = {}
        for rank, item in enumerate(sem_result.scalars().all()):
            scores[item.id] = scores.get(item.id, 0.0) + 1.0 / (rrf_k + rank + 1)
            items[item.id] = item
        for rank, item in enumerate(kw_result.scalars().all()):
            scores[item.id] = scores.get(item.id, 0.0) + 1.0 / (rrf_k + rank + 1)
            items[item.id] = item

        sorted_ids = sorted(scores, key=lambda x: scores[x], reverse=True)[:limit]
        return [
            {
                "id": items[i].id,
                "github_number": items[i].github_number,
                "title": items[i].title,
                "status": items[i].status,
            }
            for i in sorted_ids
        ]

    return [
        {
            "id": pr.id,
            "github_number": pr.github_number,
            "title": pr.title,
            "status": pr.status,
        }
        for pr in prs
    ]
