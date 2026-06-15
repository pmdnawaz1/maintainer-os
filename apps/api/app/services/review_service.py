"""PR review service — bridges webhook events to the LangGraph reviewer agent."""

import structlog
from github import Github

from app.services.github_auth import get_installation_token

log = structlog.get_logger()


async def review_pull_request(
    installation_id: int,
    repo_full_name: str,
    pr_number: int,
) -> None:
    """Run the review agent on a GitHub PR and post feedback."""
    token = await get_installation_token(installation_id)
    gh = Github(token)
    repo = gh.get_repo(repo_full_name)
    pr = repo.get_pull(pr_number)

    diff = pr.get_files()
    diff_text = "\n".join(
        f"--- {f.filename}\n+++ {f.filename}\n{f.patch or ''}" for f in diff
    )

    from packages_agents import buildReviewGraph  # resolved at runtime

    graph = buildReviewGraph()
    result = await graph.ainvoke({
        "repoFullName": repo_full_name,
        "prNumber": pr_number,
        "prTitle": pr.title,
        "prBody": pr.body or "",
        "diff": diff_text,
    })

    feedback: str = result.get("feedback", "")
    approved: bool = result.get("approved", False)
    security_issues: list[str] = result.get("securityIssues", [])

    event = "APPROVE" if approved and not security_issues else "REQUEST_CHANGES"
    body = feedback
    if security_issues:
        body += "\n\n**Security issues found:**\n" + "\n".join(f"- {s}" for s in security_issues)

    pr.create_review(body=body, event=event)
    log.info("review_complete", repo=repo_full_name, pr=pr_number, approved=approved)
