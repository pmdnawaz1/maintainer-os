"""Automated release process: changelog generation → semver bump → GitHub Release."""

import asyncio
import json
import re
from datetime import datetime, timezone

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import Release, Repository
from app.services.github_auth import get_installation_token
from app.tasks.celery_app import celery_app

log = structlog.get_logger()

GITHUB_API = "https://api.github.com"

_BREAKING_RE = re.compile(r"(BREAKING[\s\-]CHANGE|^[a-z]+\(?.+?\)?!:)", re.MULTILINE | re.IGNORECASE)
_FEAT_RE = re.compile(r"^feat(\(.+?\))?[!:]", re.IGNORECASE)
_FIX_RE = re.compile(r"^(fix|bug)(\(.+?\))?[!:]", re.IGNORECASE)
_DOCS_RE = re.compile(r"^docs(\(.+?\))?[!:]", re.IGNORECASE)

VALID_BUMP_TYPES = {"major", "minor", "patch", "auto"}


# ---------------------------------------------------------------------------
# Semver helpers
# ---------------------------------------------------------------------------

def _parse_version(tag: str) -> tuple[int, int, int]:
    """Parse 'v1.2.3' or '1.2.3' → (major, minor, patch). Returns (0, 0, 0) on failure."""
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", tag.strip())
    if not match:
        return (0, 0, 0)
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _bump_version(current_tag: str | None, bump_type: str) -> str:
    """Compute next semantic version tag string (e.g. 'v1.3.0')."""
    major, minor, patch = _parse_version(current_tag or "v0.0.0")
    if bump_type == "major":
        return f"v{major + 1}.0.0"
    elif bump_type == "minor":
        return f"v{major}.{minor + 1}.0"
    else:
        return f"v{major}.{minor}.{patch + 1}"


# ---------------------------------------------------------------------------
# Changelog helpers
# ---------------------------------------------------------------------------

def _pr_labels(pr: dict) -> list[str]:
    return [label["name"].lower() for label in pr.get("labels", [])]


def _categorize_pr(pr: dict) -> str:
    title = pr.get("title", "")
    labels = _pr_labels(pr)
    body = pr.get("body", "") or ""

    if _BREAKING_RE.search(title) or "breaking-change" in labels or "BREAKING CHANGE" in body:
        return "breaking"
    if _FEAT_RE.match(title) or "feature" in labels or "enhancement" in labels:
        return "features"
    if _FIX_RE.match(title) or "bug" in labels or "fix" in labels:
        return "fixes"
    if _DOCS_RE.match(title) or "documentation" in labels:
        return "docs"
    return "other"


def _detect_bump_type(prs: list[dict]) -> str:
    """Infer the required semver bump from PR titles and labels."""
    has_breaking = False
    has_feature = False

    for pr in prs:
        cat = _categorize_pr(pr)
        if cat == "breaking":
            has_breaking = True
        elif cat == "features":
            has_feature = True

    if has_breaking:
        return "major"
    if has_feature:
        return "minor"
    return "patch"


def _build_changelog(
    prs: list[dict],
    version: str,
    previous_version: str | None,
) -> tuple[dict, str]:
    """Build structured changelog JSON and Markdown body from a list of merged PRs."""
    categories: dict[str, list[dict]] = {
        "breaking": [],
        "features": [],
        "fixes": [],
        "docs": [],
        "other": [],
    }
    for pr in prs:
        cat = _categorize_pr(pr)
        categories[cat].append({
            "number": pr["number"],
            "title": pr["title"],
            "author": pr["user"]["login"],
            "url": pr["html_url"],
        })

    changelog_json: dict = {
        "version": version,
        "previous_version": previous_version,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "total_prs": len(prs),
        "changes": categories,
    }

    # Markdown
    md = f"## {version}\n\n"
    if previous_version:
        md += f"> Changes since {previous_version}\n\n"

    section_labels = {
        "breaking": "⚠️ Breaking Changes",
        "features": "✨ New Features",
        "fixes": "🐛 Bug Fixes",
        "docs": "📖 Documentation",
        "other": "🔧 Other Changes",
    }
    has_any = False
    for key, label in section_labels.items():
        items = categories[key]
        if not items:
            continue
        has_any = True
        md += f"### {label}\n\n"
        for item in items:
            md += f"- {item['title']} ([#{item['number']}]({item['url']})) by @{item['author']}\n"
        md += "\n"

    if not has_any:
        md += "_No notable changes._\n"

    return changelog_json, md


# ---------------------------------------------------------------------------
# Core async logic
# ---------------------------------------------------------------------------

async def _async_trigger_release(repo_id: int, bump_type: str) -> dict:
    """Fetch PRs, build changelog, bump version, create GitHub Release, persist record."""
    engine = create_async_engine(settings.database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as db:
            repo_result = await db.execute(select(Repository).where(Repository.id == repo_id))
            repo = repo_result.scalar_one_or_none()
            if not repo:
                log.warning("release_repo_not_found", repo_id=repo_id)
                return {"status": "error", "reason": "repository not found"}
            if not repo.installation_id:
                log.warning("release_no_installation", repo=repo.full_name)
                return {"status": "error", "reason": "no GitHub App installation for this repository"}

            token = await get_installation_token(repo.installation_id)
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            async with httpx.AsyncClient(timeout=30) as client:
                # 1. Determine last release tag and publish date
                previous_version: str | None = None
                since_date: str | None = None
                latest_resp = await client.get(
                    f"{GITHUB_API}/repos/{repo.full_name}/releases/latest",
                    headers=headers,
                )
                if latest_resp.status_code == 200:
                    latest = latest_resp.json()
                    previous_version = latest.get("tag_name")
                    since_date = latest.get("published_at")
                    log.info("release_last_found", repo=repo.full_name, tag=previous_version)
                else:
                    log.info("release_no_previous", repo=repo.full_name)

                # 2. Fetch merged PRs (up to 100) since last release
                prs_resp = await client.get(
                    f"{GITHUB_API}/repos/{repo.full_name}/pulls",
                    headers=headers,
                    params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 100},
                )
                prs_resp.raise_for_status()
                all_prs = prs_resp.json()

                merged_prs = [
                    pr for pr in all_prs
                    if pr.get("merged_at")
                    and (since_date is None or pr["merged_at"] > since_date)
                ]
                log.info("release_prs_collected", repo=repo.full_name, count=len(merged_prs))

                # 3. Auto-detect bump type if requested
                resolved_bump = _detect_bump_type(merged_prs) if bump_type == "auto" else bump_type

                # 4. Compute next version tag
                next_version = _bump_version(previous_version, resolved_bump)

                # 5. Build changelog
                changelog_json, changelog_markdown = _build_changelog(
                    merged_prs, next_version, previous_version
                )

                # 6. Create GitHub Release
                create_resp = await client.post(
                    f"{GITHUB_API}/repos/{repo.full_name}/releases",
                    headers=headers,
                    json={
                        "tag_name": next_version,
                        "name": next_version,
                        "body": changelog_markdown,
                        "draft": False,
                        "prerelease": False,
                    },
                )
                create_resp.raise_for_status()
                release_data = create_resp.json()
                release_url: str = release_data.get("html_url", "")
                github_release_id: int | None = release_data.get("id")

            # 7. Persist release record
            record = Release(
                repository_id=repo.id,
                version=next_version,
                previous_version=previous_version,
                bump_type=resolved_bump,
                changelog_json=json.dumps(changelog_json),
                changelog_markdown=changelog_markdown,
                release_url=release_url,
                github_release_id=github_release_id,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)

            log.info(
                "release_published",
                repo=repo.full_name,
                version=next_version,
                url=release_url,
                record_id=record.id,
            )
            return {
                "status": "ok",
                "version": next_version,
                "previous_version": previous_version,
                "bump_type": resolved_bump,
                "prs_included": len(merged_prs),
                "release_url": release_url,
                "record_id": record.id,
            }
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.tasks.release_task.trigger_release",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def trigger_release(self, repo_id: int, bump_type: str = "auto") -> dict:
    """Celery task — build changelog and publish a GitHub Release for a repository."""
    try:
        result = asyncio.run(_async_trigger_release(repo_id, bump_type))
        log.info("release_task_done", repo_id=repo_id, result=result)
        return result
    except Exception as exc:
        log.error("release_task_failed", repo_id=repo_id, bump_type=bump_type, error=str(exc))
        raise self.retry(exc=exc)
