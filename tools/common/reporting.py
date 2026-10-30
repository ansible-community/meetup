"""Shared helpers for private community audit reports."""

from __future__ import annotations

import datetime as dt
import html
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote, urlencode

from tools.common.ansible_events_lib import ApiError, discourse_req

GROUP_MEMBERS_PAGE_SIZE = 200
REPORT_OUTPUT_DIRECTORY = Path("tools/output")
MEETUP_GROUP_SNAPSHOT_PATH = Path("tools/data/meetup-groups.json")

ReportCell = str | list[str]
ReportRow = dict[str, ReportCell]


@dataclass(frozen=True)
class ReportSection:
    """One independently built report section in a combined HTML document."""

    title: str
    anchor: str
    fieldnames: list[str]
    rows: list[ReportRow]


def discourse_get_json(endpoint: str, *, run_as: str | None = None, **params: Any) -> dict[str, Any]:
    """Fetch a Discourse JSON object using the shared retrying API client."""
    query = urlencode(params)
    request_path = f"{endpoint}?{query}" if query else endpoint
    return discourse_req("GET", request_path, run_as=run_as)


def response_records(data: dict[str, Any], key: str, endpoint: str) -> list[dict[str, Any]]:
    """Validate and return object records from a response list."""
    value = data.get(key)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ApiError(f"Discourse response from {endpoint} is missing a valid {key} list")
    return value


def list_discourse_groups() -> list[dict[str, Any]]:
    """Fetch all pages from the Discourse group directory."""
    groups: list[dict[str, Any]] = []
    page = 0
    while True:
        endpoint = "groups.json"
        data = discourse_get_json(endpoint, page=page)
        batch = response_records(data, "groups", endpoint)
        groups.extend(batch)
        if not batch:
            return groups
        page += 1


def group_member_usernames(group_name: str) -> set[str]:
    """Return every username in a group, following offset pagination."""
    usernames: set[str] = set()
    offset = 0
    while True:
        endpoint = f"groups/{quote(group_name, safe='')}/members.json"
        data = discourse_get_json(endpoint, offset=offset, limit=GROUP_MEMBERS_PAGE_SIZE)
        batch = response_records(data, "members", endpoint)
        page_usernames: list[str] = []
        for member in batch:
            username = member.get("username")
            if not isinstance(username, str) or not username:
                raise ApiError(f"Discourse group {group_name!r} returned a member without a username")
            page_usernames.append(username)
        usernames.update(page_usernames)
        if len(batch) < GROUP_MEMBERS_PAGE_SIZE:
            return usernames
        offset += GROUP_MEMBERS_PAGE_SIZE


def group_members_by_name(group_names: Iterable[str]) -> dict[str, set[str]]:
    """Fetch memberships once per unique group name."""
    return {name: group_member_usernames(name) for name in dict.fromkeys(group_names)}


def usernames_for_groups(group_names: Iterable[str], memberships: dict[str, set[str]]) -> set[str]:
    """Return the distinct usernames found in the requested group memberships."""
    return set().union(*(memberships[name] for name in group_names))


def user_badge_awards(username: str) -> list[int]:
    """Return badge IDs awarded to a user from Discourse's user-badges endpoint."""
    endpoint = f"user-badges/{quote(username, safe='')}.json"
    data = discourse_get_json(endpoint)
    awards = response_records(data, "user_badges", endpoint)
    badge_ids: list[int] = []
    for award in awards:
        badge_id = award.get("badge_id")
        if not isinstance(badge_id, int) or isinstance(badge_id, bool):
            raise ApiError(f"Discourse user badges for {username!r} contains an invalid badge ID")
        badge_ids.append(badge_id)
    return badge_ids


def report_output_path(
    prefix: str,
    *,
    now: dt.datetime | None = None,
    output_directory: Path = REPORT_OUTPUT_DIRECTORY,
) -> Path:
    """Return a timestamped HTML report path under the configured output directory."""
    timestamp = (now or dt.datetime.now().astimezone()).astimezone().strftime("%Y%m%d-%H%M%S")
    return output_directory / f"{prefix}-{timestamp}.html"


def _render_cell(value: ReportCell) -> str:
    if isinstance(value, list):
        items = sorted((item for item in value if item), key=str.casefold)
        if not items:
            items = ["None"]
        return "<ul>" + "".join(f"<li>{html.escape(item, quote=True)}</li>" for item in items) + "</ul>"
    return html.escape(value, quote=True)


def _render_anchor_link(anchor: str, label: str) -> str:
    escaped_anchor = html.escape(anchor, quote=True)
    escaped_label = html.escape(label, quote=True)
    return (
        f'<a class="heading-anchor" href="#{escaped_anchor}" '
        f'aria-label="{escaped_label}" title="{escaped_label}">'
        '<svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" '
        'fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19'
        'a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.82-2.83l8.49-8.48"/>'
        "</svg></a>"
    )


def _render_section(section: ReportSection) -> str:
    anchor = html.escape(section.anchor, quote=True)
    title = html.escape(section.title)
    headers = "".join(f'<th scope="col">{html.escape(field)}</th>' for field in section.fieldnames)
    rows = "\n".join(
        "<tr>" + "".join(f"<td>{_render_cell(row[field])}</td>" for field in section.fieldnames) + "</tr>"
        for row in section.rows
    )
    if not rows:
        rows = f'<tr><td colspan="{len(section.fieldnames)}">No records found.</td></tr>'

    return (
        f'<section aria-labelledby="{anchor}">'
        f'<h2 id="{anchor}">{title}{_render_anchor_link(section.anchor, f"Link to {section.title} heading")}</h2>'
        f"<table><thead><tr>{headers}</tr></thead><tbody>{rows}</tbody></table>"
        "</section>"
    )


def render_html_report(title: str, sections: list[ReportSection], *, generated_at: dt.datetime) -> str:
    """Render report sections with a linked table of contents and sorted cell lists."""
    generated_display = generated_at.astimezone(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    toc = "\n".join(
        f'<li><a href="#{html.escape(section.anchor, quote=True)}">{html.escape(section.title)}</a></li>'
        for section in sections
    )
    rendered_sections = "\n".join(_render_section(section) for section in sections)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ color: #202124; font: 16px/1.5 system-ui, sans-serif;
           margin: 2rem auto; max-width: 100rem; padding: 0 1rem; }}
    table {{ border-collapse: collapse; margin: 1rem 0; width: 100%; }}
    th, td {{ border: 1px solid #bbb; padding: .5rem .65rem; text-align: left; vertical-align: top; }}
    th {{ background: #eee; }}
    tbody tr:nth-child(even) {{ background: #f8f8f8; }}
    td ul {{ margin: 0; padding-left: 1.25rem; }}
    h1, h2 {{ align-items: center; display: flex; gap: .5rem; }}
    .heading-anchor {{ align-items: center; border-radius: .2rem; color: #4b5563;
                       display: inline-flex; flex: 0 0 auto; justify-content: center;
                       margin-left: auto; min-height: 1.75rem; min-width: 1.75rem; }}
    .heading-anchor:hover {{ background: #eef0f2; color: #111827; }}
    .heading-anchor:focus-visible {{ outline: 2px solid #2563eb; outline-offset: 2px; }}
    @media print {{ body {{ max-width: none; }} a {{ color: inherit; }} }}
  </style>
</head>
<body>
  <h1 id="report-title">{html.escape(title)}{_render_anchor_link("report-title", "Link to report heading")}</h1>
  <nav id="table-of-contents" aria-label="Table of contents">
    <h2 id="contents-heading">Contents{_render_anchor_link("contents-heading", "Link to contents heading")}</h2>
    <ul>{toc}</ul>
  </nav>
  {rendered_sections}
  <footer><p>Generated {html.escape(generated_display)}</p></footer>
</body>
</html>
"""


def write_private_text(content: str, output_path: Path, *, overwrite: bool = False) -> None:
    """Write a private text file, optionally replacing it atomically."""
    output_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if overwrite:
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output_path.name}.", dir=output_path.parent)
        temporary_path = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output_file:
                descriptor = -1
                output_file.write(content)
            os.replace(temporary_path, output_path)
        except Exception:
            if descriptor >= 0:
                os.close(descriptor)
            temporary_path.unlink(missing_ok=True)
            raise
        return

    descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as output_file:
            descriptor = -1
            output_file.write(content)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        output_path.unlink(missing_ok=True)
        raise


def write_private_html(content: str, output_path: Path, *, overwrite: bool = False) -> None:
    """Write a private HTML report, optionally replacing it atomically."""
    write_private_text(content, output_path, overwrite=overwrite)
