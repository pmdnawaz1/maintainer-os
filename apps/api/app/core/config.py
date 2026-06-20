from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    secret_key: str = "change-me-in-production"
    frontend_url: str = "http://localhost:3000"
    allowed_origins: list[str] = ["http://localhost:3000"]

    @property
    def cors_origins(self) -> list[str]:
        origins = list(self.allowed_origins)
        if self.frontend_url not in origins:
            origins.append(self.frontend_url)
        return origins

    # Database
    database_url: str = "postgresql+asyncpg://maintainer:maintainer_secret@localhost:5432/maintainer_os"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "maintainer_secret"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_hnsw_m: int = 16                  # HNSW bi-directional link count
    qdrant_hnsw_ef_construct: int = 200      # build-time candidate list size
    qdrant_search_ef: int = 128              # query-time candidate list size
    qdrant_score_threshold: float = 0.70     # minimum cosine similarity to return
    qdrant_cache_ttl: int = 300              # search result cache TTL in seconds

    # Redis
    redis_url: str = "redis://localhost:6379"

    # GitHub App
    github_app_id: str = ""
    github_app_private_key: str = ""
    github_webhook_secret: str = ""

    # AI
    anthropic_api_key: str = ""
    openai_api_key: str = ""


settings = Settings()
