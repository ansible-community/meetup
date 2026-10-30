from __future__ import annotations

import datetime as dt
import stat
from pathlib import Path

import pytest

from tools.common.ansible_events_lib import (
    BADGE_MEETUP_ATTENDEE,
    BADGE_MEETUP_MIGRATED,
    BADGE_MEETUP_SPEAKER,
    ApiError,
    MIGRATED_GROUP_NAME,
)
from tools.common import reporting
from tools.reports import audit_attendees, audit_organisers, generate_all


def test_list_discourse_groups_paginates_and_keeps_empty_group_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            {"groups": [{"name": "one"}]},
            {"groups": [{"name": "two"}]},
            {"groups": []},
        ]
    )
    requests: list[tuple[str, dict[str, object]]] = []

    def get_json(endpoint: str, **params: object) -> dict[str, object]:
        requests.append((endpoint, params))
        return next(responses)

    monkeypatch.setattr(reporting, "discourse_get_json", get_json)

    assert reporting.list_discourse_groups() == [{"name": "one"}, {"name": "two"}]
    assert requests == [("groups.json", {"page": 0}), ("groups.json", {"page": 1}), ("groups.json", {"page": 2})]


def test_group_member_usernames_paginates_deduplicates_and_accepts_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            {"members": [{"username": f"user-{i}"} for i in range(reporting.GROUP_MEMBERS_PAGE_SIZE)]},
            {"members": [{"username": "user-0"}, {"username": "last"}]},
        ]
    )
    requests: list[tuple[str, dict[str, object]]] = []

    def get_json(endpoint: str, **params: object) -> dict[str, object]:
        requests.append((endpoint, params))
        return next(responses)

    monkeypatch.setattr(reporting, "discourse_get_json", get_json)

    usernames = reporting.group_member_usernames("meetup-attendee-new-york")

    assert len(usernames) == reporting.GROUP_MEMBERS_PAGE_SIZE + 1
    assert requests == [
        ("groups/meetup-attendee-new-york/members.json", {"offset": 0, "limit": 200}),
        ("groups/meetup-attendee-new-york/members.json", {"offset": 200, "limit": 200}),
    ]

    monkeypatch.setattr(reporting, "discourse_get_json", lambda *_args, **_kwargs: {"members": []})
    assert reporting.group_member_usernames("empty") == set()


def test_group_member_usernames_rejects_malformed_member(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reporting, "discourse_get_json", lambda *_args, **_kwargs: {"members": [{}]})

    with pytest.raises(ApiError, match="without a username"):
        reporting.group_member_usernames("organisers")


def test_group_members_by_name_deduplicates_group_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[str] = []

    def members(group_name: str) -> set[str]:
        requests.append(group_name)
        return {group_name}

    monkeypatch.setattr(reporting, "group_member_usernames", members)

    assert reporting.group_members_by_name(["london", "paris", "london"]) == {
        "london": {"london"},
        "paris": {"paris"},
    }
    assert requests == ["london", "paris"]
    assert reporting.usernames_for_groups(["london", "paris"], {"london": {"alice"}, "paris": {"alice", "bob"}}) == {
        "alice",
        "bob",
    }
    assert reporting.usernames_for_groups([], {}) == set()


def test_user_badge_awards_returns_ids_and_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reporting,
        "discourse_get_json",
        lambda _endpoint: {"user_badges": [{"badge_id": 123}, {"badge_id": 124}]},
    )
    assert reporting.user_badge_awards("alice") == [123, 124]

    monkeypatch.setattr(reporting, "discourse_get_json", lambda _endpoint: {"user_badges": [{"badge_id": True}]})
    with pytest.raises(ApiError, match="invalid badge ID"):
        reporting.user_badge_awards("alice")


def test_write_private_html_creates_restricted_file_and_refuses_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "report.html"
    reporting.write_private_html("<html>audit</html>", destination)

    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert destination.read_text(encoding="utf-8") == "<html>audit</html>"
    with pytest.raises(FileExistsError):
        reporting.write_private_html("<html>replacement</html>", destination)


def test_html_report_has_toc_anchors_and_sorted_bullet_cells() -> None:
    section = reporting.ReportSection(
        "Organisers & groups",
        "organisers",
        ["Groups", "Locations", "Username"],
        [{"Groups": ["zeta", "Alpha"], "Locations": ["Paris", "London"], "Username": "<alice>"}],
    )
    document = reporting.render_html_report(
        "Audit & report", [section], generated_at=dt.datetime(2026, 10, 26, tzinfo=dt.UTC)
    )

    assert '<a href="#organisers">Organisers &amp; groups</a>' in document
    assert '<h2 id="organisers">Organisers &amp; groups<a class="heading-anchor"' in document
    assert '<svg aria-hidden="true" viewBox="0 0 24 24"' in document
    assert document.count('class="heading-anchor"') == 3
    assert '<h1 id="report-title">Audit &amp; report' in document
    assert '<h2 id="contents-heading">Contents' in document
    assert "Back to table of contents" not in document
    assert "<li>Alpha</li><li>zeta</li>" in document
    assert "<li>London</li><li>Paris</li>" in document
    assert "&lt;alice&gt;" in document
    assert "<ul><li>None</li></ul>" not in document


def test_attendee_group_names_accepts_only_lowercase_alpha_city_slugs() -> None:
    groups = [
        {"name": "meetup-attendee-london"},
        {"name": "meetup-attendee-newyork"},
        {"name": "meetup-attendee-new-york"},
        {"name": "meetup-attendee-London"},
        {"name": "meetup-attendee-"},
        {"name": "unrelated"},
    ]

    assert audit_attendees.attendee_group_names(groups) == [
        "meetup-attendee-london",
        "meetup-attendee-newyork",
    ]


def test_invite_link_usernames_paginates_and_ignores_non_link_invites(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            {"invites": [{"invite_source": "link", "user": {"username": "alice"}}, {"invite_source": "email"}]},
            {"invites": [{"invite_source": "link", "user": {"username": "bob"}}]},
            {"invites": []},
        ]
    )
    requests: list[tuple[str, str | None, dict[str, object]]] = []

    def get_json(endpoint: str, *, run_as: str | None = None, **params: object) -> dict[str, object]:
        requests.append((endpoint, run_as, params))
        return next(responses)

    monkeypatch.setattr(audit_attendees, "get_json", get_json)

    assert audit_attendees.invite_link_usernames() == {"alice", "bob"}
    assert [request[2]["offset"] for request in requests] == [0, 2, 3]
    assert all(request[1] == "gundalow" for request in requests)


def test_attendee_report_counts_cumulative_account_age_and_invite_percentage(monkeypatch: pytest.MonkeyPatch) -> None:
    now = dt.datetime(2026, 10, 25, 12, tzinfo=dt.UTC)
    memberships = {
        "meetup-attendee-london": {"alice", "bob", "unknown"},
        "meetup-attendee-paris": {"alice", "charlie"},
        "meetup-attendee-empty": set(),
    }
    created = {
        "alice": now - dt.timedelta(hours=12),
        "bob": now - dt.timedelta(days=2),
        "charlie": now - dt.timedelta(days=11),
        "unknown": None,
    }
    fetched: list[str] = []

    def account_created_at(username: str) -> dt.datetime | None:
        fetched.append(username)
        return created[username]

    monkeypatch.setattr(audit_attendees, "account_created_at", account_created_at)
    rows = audit_attendees.build_report(
        list(memberships),
        {"alice", "charlie"},
        now=now,
        members_by_group={**memberships, "unused-group": {"not-a-report-member"}},
    )
    london, paris, empty = rows

    assert fetched == ["alice", "bob", "charlie", "unknown"]
    assert london["Attendee group"] == ["meetup-attendee-london"]
    assert london["Members"] == "3"
    assert london["Accounts created in past 1 day(s)"] == "1"
    assert london["Accounts created in past 2 day(s)"] == "2"
    assert london["Accounts created in past 10 day(s)"] == "2"
    assert london["Forum invite-link members (%)"] == "33.3%"
    assert paris["Members"] == "2"
    assert paris["Forum invite-link members"] == "2"
    assert paris["Forum invite-link members (%)"] == "100.0%"
    assert empty["Members"] == "0"
    assert empty["Forum invite-link members (%)"] == "N/A"


def test_attendee_badges_report_counts_awards_per_group(monkeypatch: pytest.MonkeyPatch) -> None:
    groups = ["meetup-attendee-london", "meetup-attendee-paris", MIGRATED_GROUP_NAME]
    members = {
        "meetup-attendee-london": {"alice", "bob"},
        "meetup-attendee-paris": {"alice"},
        MIGRATED_GROUP_NAME: {"bob"},
    }
    awards = {"alice": [BADGE_MEETUP_ATTENDEE, BADGE_MEETUP_ATTENDEE], "bob": [BADGE_MEETUP_MIGRATED]}
    calls: list[str] = []

    def user_awards(username: str) -> list[int]:
        calls.append(username)
        return awards[username]

    monkeypatch.setattr(audit_attendees, "user_badge_awards", user_awards)

    rows = audit_attendees.build_badges_report(groups, members_by_group=members)

    assert calls == ["alice", "bob"]
    assert rows[0] == {
        "Group": ["meetup-attendee-london"],
        "Members": "2",
        "Meetup attendee badge awards": "2",
        "Meetup migrated badge awards": "1",
    }
    assert rows[1]["Meetup attendee badge awards"] == "2"
    assert rows[2]["Meetup migrated badge awards"] == "1"


def test_attendee_account_timestamp_parsing() -> None:
    assert audit_attendees.parse_created_at("2026-10-25T12:00:00Z") == dt.datetime(2026, 10, 25, 12, tzinfo=dt.UTC)
    assert audit_attendees.parse_created_at("not a timestamp") is None
    assert audit_attendees.parse_created_at(None) is None


def test_organiser_memberships_deduplicate_and_skip_empty_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[str] = []

    def group_members(name: str) -> set[str]:
        requests.append(name)
        return {"alice"} if name == "meetup-organisers-london" else {"alice", "bob"}

    monkeypatch.setattr(audit_organisers, "group_member_usernames", group_members)
    groups = [
        {"name": "meetup-organisers-london", "user_count": 1},
        {"name": "meetup-organisers-paris", "user_count": 2},
        {"name": "meetup-organisers-empty", "user_count": 0},
        {"name": "unrelated", "user_count": 10},
    ]

    assert audit_organisers.organizer_memberships(groups) == {
        "alice": {"meetup-organisers-london", "meetup-organisers-paris"},
        "bob": {"meetup-organisers-paris"},
    }
    assert requests == ["meetup-organisers-london", "meetup-organisers-paris"]


def test_other_group_memberships_excludes_system_and_organiser_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    groups = [
        {"name": "everyone", "user_count": 3},
        {"name": "trust_level_2", "user_count": 2},
        {"name": "meetup-organisers-london", "user_count": 1},
        {"name": "community-team", "user_count": 2},
        {"name": "empty-custom", "user_count": 0},
    ]
    visited: list[str] = []

    def group_members(name: str) -> set[str]:
        visited.append(name)
        return {"alice", "other"}

    monkeypatch.setattr(audit_organisers, "group_member_usernames", group_members)

    assert audit_organisers.other_group_memberships(groups, {"alice"}) == {"alice": {"community-team"}}
    assert visited == ["community-team"]


def test_organiser_profile_formats_disabled_unknown_2fa_and_city_field(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter(
        [
            {
                "user": {
                    "username": "alice",
                    "id": 123,
                    "second_factor_enabled": False,
                    "created_at": "2024-01-01T00:00:00Z",
                    "last_seen_at": None,
                    "custom_fields": {},
                }
            },
            {"user": {"username": "alice", "custom_fields": {"user_field_4": ["London", "Paris"]}}},
        ]
    )
    endpoints: list[str] = []

    def get_json(endpoint: str) -> dict[str, object]:
        endpoints.append(endpoint)
        return next(responses)

    monkeypatch.setattr(audit_organisers, "get_json", get_json)
    monkeypatch.setattr(
        audit_organisers,
        "user_badge_awards",
        lambda _username: [BADGE_MEETUP_SPEAKER, BADGE_MEETUP_ATTENDEE],
    )

    assert audit_organisers.user_profile("alice") == {
        "2FA": "Not enabled",
        "Badges (speaker / organiser / attendee)": "✅❌✅",
        "Account created": "2024-01-01T00:00:00Z",
        "Last seen": "Unknown",
        "Event locations": ["London", "Paris"],
    }
    assert endpoints == ["u/alice.json", "admin/users/123.json"]


def test_organiser_profile_marks_missing_2fa_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = iter([{"user": {"username": "alice", "id": 1}}, {"user": {"username": "alice"}}])
    monkeypatch.setattr(audit_organisers, "get_json", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(audit_organisers, "user_badge_awards", lambda _username: [])

    assert audit_organisers.user_profile("alice")["2FA"] == "Unknown"


def test_generate_all_collects_before_writing_and_uses_shared_timestamp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    written: list[tuple[str, Path]] = []
    attendee_calls: list[list[str]] = []
    destination = tmp_path / "community.html"
    monkeypatch.setattr(generate_all, "list_discourse_groups", lambda: [{"name": "groups"}])
    monkeypatch.setattr(
        generate_all,
        "build_organiser_report",
        lambda _groups: [
            {
                "Username": "alice",
                "Organiser groups": ["meetup-organisers-london"],
                "2FA": "Enabled",
                "Badges (speaker / organiser / attendee)": "✅❌❌",
                "Account created": "2024-01-01",
                "Last seen": "2026-10-26",
                "Event locations": ["London"],
                "Other groups": ["CommunityTeam"],
            }
        ],
    )
    monkeypatch.setattr(generate_all, "attendee_group_names", lambda _groups: ["meetup-attendee-london"])
    monkeypatch.setattr(
        generate_all, "group_members_by_name", lambda group_names: {name: {"alice"} for name in group_names}
    )
    monkeypatch.setattr(generate_all, "invite_link_usernames", lambda: {"alice"})
    monkeypatch.setattr(
        generate_all,
        "build_badges_report",
        lambda _groups, **_kwargs: [
            {
                "Group": [MIGRATED_GROUP_NAME],
                "Members": "1",
                "Meetup attendee badge awards": "0",
                "Meetup migrated badge awards": "1",
            }
        ],
    )

    def build_attendee(groups: list[str], _users: set[str], **_kwargs: object) -> list[dict[str, object]]:
        attendee_calls.append(groups)
        return [
            {
                "Attendee group": groups,
                "Members": "1",
                "Accounts created in past 1 day(s)": "0",
                "Accounts created in past 2 day(s)": "0",
                "Accounts created in past 3 day(s)": "0",
                "Accounts created in past 4 day(s)": "0",
                "Accounts created in past 5 day(s)": "0",
                "Accounts created in past 10 day(s)": "0",
                "Forum invite-link members": "1",
                "Forum invite-link members (%)": "100.0%",
            }
        ]

    monkeypatch.setattr(generate_all, "build_attendee_report", build_attendee)

    def write(content: str, path: Path) -> None:
        written.append((content, path))

    monkeypatch.setattr(generate_all, "write_private_html", write)

    output = generate_all.generate_all_reports(destination)

    assert output == destination
    assert len(written) == 1
    content, path = written[0]
    assert path == destination
    assert 'href="#organiser-accounts"' in content
    assert 'href="#migrated-attendees"' in content
    assert 'href="#attendee-groups"' in content
    assert 'href="#attendee-badges"' in content
    assert content.index('href="#migrated-attendees"') < content.index('href="#attendee-groups"')
    assert content.count("<!doctype html>") == 1
    assert attendee_calls == [[MIGRATED_GROUP_NAME], ["meetup-attendee-london"]]


def test_generate_all_refuses_existing_output_before_api_requests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "existing.html"
    destination.touch()
    monkeypatch.setattr(generate_all, "list_discourse_groups", lambda: pytest.fail("API should not be called"))

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        generate_all.generate_all_reports(destination)


def test_generate_all_api_failure_does_not_write_partial_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    writes: list[Path] = []
    monkeypatch.setattr(generate_all, "list_discourse_groups", lambda: [{"name": "groups"}])
    monkeypatch.setattr(generate_all, "build_organiser_report", lambda _groups: [{"Username": "alice"}])

    def fail_attendee_report(*_args: object, **_kwargs: object) -> list[dict[str, str]]:
        raise ApiError("simulated attendee API failure")

    monkeypatch.setattr(generate_all, "attendee_group_names", lambda _groups: ["meetup-attendee-london"])
    monkeypatch.setattr(
        generate_all, "group_members_by_name", lambda group_names: {name: {"alice"} for name in group_names}
    )
    monkeypatch.setattr(generate_all, "invite_link_usernames", lambda: {"alice"})
    monkeypatch.setattr(generate_all, "build_attendee_report", fail_attendee_report)
    monkeypatch.setattr(generate_all, "write_private_html", lambda _content, path: writes.append(path))

    with pytest.raises(ApiError, match="simulated attendee API failure"):
        generate_all.generate_all_reports(tmp_path / "community.html")
    assert writes == []
