"""GitHub helper service.

This module provides two ways to obtain a user's contribution total:
 - Authenticated GraphQL query when `GITHUB_TOKEN` is present
 - Public contributions page scrape as a fallback

The file uses consistent 4-space indentation to avoid Python "mixed indent" errors
that were causing the FastAPI app to crash on import.
"""

import json
import logging
import re
from datetime import datetime, timezone
from urllib import error, request
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..config import get_settings


logger = logging.getLogger("portfolio.api.github")
logger.setLevel(logging.INFO)


GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
GITHUB_CONTRIBUTIONS_URL = "https://github.com/users/{username}/contributions"

# Simple in-memory cache to avoid repeated heavy GraphQL queries
_CACHE: dict = {"total": None, "updated_at": None, "expires_at": 0}
_CACHE_TTL_SECONDS = 60 * 10  # 10 minutes


def get_github_commit_total() -> tuple[int, datetime]:
    settings = get_settings()
    if not settings.github_username:
        raise RuntimeError("GITHUB_USERNAME is not configured.")

    if settings.github_token:
        commit_total = _get_commit_total_with_token(settings.github_username, settings.github_token)
        return commit_total, datetime.now(timezone.utc)

    commit_total = _get_public_contribution_total(settings.github_username)
    return commit_total, datetime.now(timezone.utc)


def _get_commit_total_with_token(username: str, token: str) -> int:
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
                    totalPullRequestReviewContributions
                    contributionCalendar { totalContributions }
        }
      }
    }
    """

    # Use an in-memory cache to avoid repeated expensive requests
    now_ts = time.time()
    if _CACHE.get("total") is not None and _CACHE.get("expires_at", 0) > now_ts:
        logger.info("github_stats_cache_hit username=%s", username)
        return _CACHE["total"]

    logger.info("github_stats_request_start username=%s source=token", username)

    def _graphql_request(payload_bytes: bytes) -> dict:
        req = request.Request(
            GITHUB_GRAPHQL_URL,
            data=payload_bytes,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "portfolio-website",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            logger.exception("github_stats_request_failed status=%s detail=%s", exc.code, detail)
            raise RuntimeError(f"GitHub API error ({exc.code}): {detail}") from exc
        except error.URLError as exc:
            logger.exception("github_stats_connection_failed")
            raise RuntimeError(f"GitHub connection failed: {exc.reason}") from exc

    # 1) Ask GitHub for the account creation year to limit the number of yearly queries
    created_query = """
    query($login: String!) {
      user(login: $login) { createdAt }
    }
    """
    payload = json.dumps({"query": created_query, "variables": {"login": username}}).encode("utf-8")
    body = _graphql_request(payload)
    user_data = body.get("data", {}).get("user")
    if not user_data or not user_data.get("createdAt"):
        raise RuntimeError("GitHub user not found or missing createdAt.")

    created_year = datetime.fromisoformat(user_data["createdAt"].replace("Z", "+00:00")).year
    current_year = datetime.now(timezone.utc).year
    years = list(range(created_year, current_year + 1))

    def _fetch_year(year: int) -> int:
        range_from = f"{year}-01-01T00:00:00Z"
        range_to = f"{year+1}-01-01T00:00:00Z" if year < current_year else datetime.now(timezone.utc).isoformat()
        payload = json.dumps({"query": query, "variables": {"login": username, "from": range_from, "to": range_to}}).encode("utf-8")
        body = _graphql_request(payload)
        if body.get("errors"):
            logger.error("github_stats_graphql_error errors=%s year=%s", body["errors"], year)
            raise RuntimeError(f"GitHub GraphQL error: {body['errors']}")
        user = body.get("data", {}).get("user")
        if not user:
            raise RuntimeError("GitHub user not found.")
        
        collection = user["contributionsCollection"]
        # Use the contribution calendar total which matches the GitHub contributions UI.
        # This includes all contribution types counted by the graph, not just the
        # four explicit contribution fields.
        calendar = collection.get("contributionCalendar", {})
        return calendar.get("totalContributions", 0)

    total_commits = 0
    max_workers = min(8, max(2, len(years)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_fetch_year, y): y for y in years}
        for fut in as_completed(futures):
            year = futures[fut]
            try:
                year_total = fut.result()
                total_commits += year_total
            except Exception:
                logger.exception("github_stats_year_fetch_failed year=%s", year)
                raise

    # Cache and return
    _CACHE["total"] = total_commits
    _CACHE["updated_at"] = datetime.now(timezone.utc)
    _CACHE["expires_at"] = time.time() + _CACHE_TTL_SECONDS

    logger.info(
        "github_stats_request_complete username=%s total_contributions=%s source=token",
        username,
        total_commits,
    )
    return total_commits


def _get_public_contribution_total(username: str) -> int:
    contributions_url = GITHUB_CONTRIBUTIONS_URL.format(username=username)
    contributions_request = request.Request(
        contributions_url,
        headers={"User-Agent": "portfolio-website", "Accept": "text/html"},
        method="GET",
    )

    logger.info("github_stats_request_start username=%s source=public", username)
    try:
        with request.urlopen(contributions_request, timeout=10) as response:
            body = response.read().decode("utf-8", errors="ignore")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        logger.exception("github_stats_public_request_failed status=%s detail=%s", exc.code, detail)
        raise RuntimeError(f"GitHub public contributions error ({exc.code}): {detail}") from exc
    except error.URLError as exc:
        logger.exception("github_stats_public_connection_failed")
        raise RuntimeError(f"GitHub public contributions connection failed: {exc.reason}") from exc

    match = re.search(r"([\d,]+) contributions in the last year", body, re.IGNORECASE)
    if not match:
        raise RuntimeError("Could not parse GitHub public contribution count.")

    commit_total = int(match.group(1).replace(",", ""))
    logger.info(
        "github_stats_request_complete username=%s total_commit_contributions=%s source=public",
        username,
        commit_total,
    )
    return commit_total


def get_github_commit_for_year(year: int) -> tuple[int, datetime]:
    """Fetch commit count for a specific year (e.g., 2026 for all of 2026 YTD)."""
    settings = get_settings()
    if not settings.github_username:
        raise RuntimeError("GITHUB_USERNAME is not configured.")

    if settings.github_token:
        commit_total = _get_commit_total_for_year_with_token(settings.github_username, settings.github_token, year)
        return commit_total, datetime.now(timezone.utc)

    raise RuntimeError("Year-specific queries require GITHUB_TOKEN.")


def _get_commit_total_for_year_with_token(username: str, token: str, year: int) -> int:
    """Query GitHub GraphQL for all contributions (commits, PRs, issues, reviews) in a specific year."""
    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalIssueContributions
          totalPullRequestContributions
                    totalPullRequestReviewContributions
                    contributionCalendar { totalContributions }
        }
      }
    }
    """

    now = datetime.now(timezone.utc)
    range_from = f"{year}-01-01T00:00:00Z"
    # If querying current year, use now; otherwise use end of that year
    if year == now.year:
        range_to = now.isoformat()
    else:
        range_to = f"{year+1}-01-01T00:00:00Z"

    payload = json.dumps({
        "query": query,
        "variables": {"login": username, "from": range_from, "to": range_to},
    }).encode("utf-8")

    github_request = request.Request(
        GITHUB_GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "portfolio-website",
        },
        method="POST",
    )

    logger.info("github_stats_year_request_start username=%s year=%s source=token", username, year)
    try:
        with request.urlopen(github_request, timeout=10) as response:
            body = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        logger.exception("github_stats_year_request_failed status=%s detail=%s", exc.code, detail)
        raise RuntimeError(f"GitHub API error ({exc.code}): {detail}") from exc
    except error.URLError as exc:
        logger.exception("github_stats_year_connection_failed")
        raise RuntimeError(f"GitHub connection failed: {exc.reason}") from exc

    if body.get("errors"):
        logger.error("github_stats_year_graphql_error errors=%s year=%s", body["errors"], year)
        raise RuntimeError(f"GitHub GraphQL error: {body['errors']}")

    user = body.get("data", {}).get("user")
    if not user:
        raise RuntimeError("GitHub user not found.")

    collection = user["contributionsCollection"]
    commit_contrib = collection.get("totalCommitContributions", 0)
    issue_contrib = collection.get("totalIssueContributions", 0)
    pr_contrib = collection.get("totalPullRequestContributions", 0)
    pr_review_contrib = collection.get("totalPullRequestReviewContributions", 0)
    calendar_total = collection.get("contributionCalendar", {}).get("totalContributions", 0)

    logger.info(
        "github_stats_year_breakdown username=%s year=%s commits=%s issues=%s prs=%s reviews=%s calendar_total=%s",
        username,
        year,
        commit_contrib,
        issue_contrib,
        pr_contrib,
        pr_review_contrib,
        calendar_total,
    )
    logger.info(
        "github_stats_year_request_complete username=%s year=%s total_contributions=%s source=token",
        username,
        year,
        calendar_total,
    )
    return calendar_total