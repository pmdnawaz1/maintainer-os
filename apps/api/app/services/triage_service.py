"""Triage service — bridges webhook events to the LangGraph triage agent."""

import structlog
from github import Github

from app.services.github_auth import get_installation_token

log = structlog.get_logger()


async def triage_issue(
    installation_id: int,
    repo_full_name: str,
    issue_number: int,
) -> None:
    """Run the triage agent on a GitHub issue and post results back."""
    token = await get_installation_token(installation_id)
    gh = Github(token)
    repo = gh.get_repo(repo_full_name)
    issue = repo.get_issue(issue_number)

    # Lazy import to avoid loading LangGraph at startup
    from packages_agents import buildTriageGraph  # resolved at runtime via PYTHONPATH

    graph = buildTriageGraph()
    result = await graph.ainvoke({
        "repoFullName": repo_full_name,
        "issueNumber": issue_number,
        "issueTitle": issue.title,
        "issueBody": issue.body or "",
    })

    label: str = result.get("label", "question")
    response: str = result.get("suggestedResponse", "")

    # Apply label
    try:
        repo.get_label(label)
        issue.add_to_labels(label)
    except Exception:
        log.warning("triage_label_missing", label=label, repo=repo_full_name)

    # Post comment
    if response:
        issue.create_comment(response)

    log.info(
        "triage_complete",
        repo=repo_full_name,
        issue=issue_number,
        label=label,
    )
