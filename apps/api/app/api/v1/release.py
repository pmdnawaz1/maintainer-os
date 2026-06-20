"""Automated release process endpoints."""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.db.models import Release, Repository
from app.tasks.release_task import VALID_BUMP_TYPES

router = APIRouter()


@router.post("/trigger")
async def trigger_release(
    repo: str,
    bump: str = "auto",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger automated release process for a repository.

    - **repo**: full repository name (e.g. ``owner/repo``)
    - **bump**: semver bump strategy — ``major``, ``minor``, ``patch``, or ``auto``
      (``auto`` infers the bump from PR labels and conventional commit prefixes)

    The release task is queued asynchronously. Poll ``GET /releases?repo={repo}``
    for the result once the task completes.
    """
    if bump not in VALID_BUMP_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid bump type '{bump}'. Must be one of: {', '.join(sorted(VALID_BUMP_TYPES))}",
        )

    repo_result = await db.execute(select(Repository).where(Repository.full_name == repo))
    repository = repo_result.scalar_one_or_none()
    if not repository:
        raise HTTPException(status_code=404, detail=f"Repository '{repo}' not found")
    if not repository.installation_id:
        raise HTTPException(
            status_code=409,
            detail=f"Repository '{repo}' has no GitHub App installation — cannot create releases",
        )

    from app.tasks.release_task import trigger_release as release_task

    release_task.delay(repository.id, bump)

    return {"status": "queued", "repo": repo, "bump": bump}


@router.get("/")
async def list_releases(
    repo: str | None = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List stored release records, optionally filtered by repository full name.

    Results are ordered newest-first.
    """
    stmt = (
        select(Release, Repository.full_name)
        .join(Repository, Release.repository_id == Repository.id)
        .order_by(Release.created_at.desc())
        .limit(limit)
    )
    if repo:
        stmt = stmt.where(Repository.full_name == repo)

    result = await db.execute(stmt)
    releases = []
    for record, full_name in result:
        releases.append({
            "id": record.id,
            "repository": full_name,
            "version": record.version,
            "previous_version": record.previous_version,
            "bump_type": record.bump_type,
            "changelog": json.loads(record.changelog_json),
            "markdown": record.changelog_markdown,
            "release_url": record.release_url,
            "github_release_id": record.github_release_id,
            "created_at": record.created_at.isoformat(),
        })
    return releases
