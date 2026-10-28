from __future__ import annotations

from typing import Any

import pytest

from tools.common.ansible_events_lib import CITIES, ApiError
from tools.environment import check_setup


def statuses(checker: check_setup.SetupChecker) -> dict[str, str]:
    return {result.name: result.status for result in checker.results}


def test_compare_reports_matching_and_mismatching_fields() -> None:
    checker = check_setup.SetupChecker()

    checker._compare(
        "matching", "GET settings", {"name": "Meetup", "items": [1, 2]}, {"name": "Meetup", "items": [2, 1]}, "fix"
    )
    checker._compare("mismatching", "GET settings", {"name": "Meetup", "active": True}, {"name": "Other"}, "fix")

    assert [(result.name, result.status, result.detail) for result in checker.results] == [
        ("matching", "PASS", "All 2 expected fields match."),
        ("mismatching", "FAIL", "Values differ or are missing for: name, active"),
    ]


def test_missing_and_duplicate_pretix_teams_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    responses: dict[str, list[dict[str, Any]]] = {
        "teams": [
            {"name": "Ansible Meetup Staff"},
            {"name": "Ansible Meetup Staff"},
            {"name": CITIES[0].team_name},
        ],
        "events": [],
    }
    monkeypatch.setattr(check_setup, "pretix_list_all", lambda endpoint: responses[endpoint])
    checker = check_setup.SetupChecker()

    checker._check_pretix_teams_and_events()

    actual = statuses(checker)
    assert actual["Pretix API permission: organizer.teams:write"] == "PASS"
    assert actual["Pretix events inventory access"] == "PASS"
    assert actual["Pretix team: Ansible Meetup Staff"] == "FAIL"
    assert actual[f"Pretix team: {CITIES[0].team_name}"] == "FAIL"  # present, but its scope is wrong
    assert actual[f"Pretix team: {CITIES[1].team_name}"] == "FAIL"  # missing


def test_team_permission_read_failure_is_reported_without_false_missing_teams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def list_endpoint(endpoint: str) -> list[dict[str, Any]]:
        if endpoint == "teams":
            raise ApiError("private response text")
        return []

    monkeypatch.setattr(check_setup, "pretix_list_all", list_endpoint)
    checker = check_setup.SetupChecker()

    checker._check_pretix_teams_and_events()

    actual = statuses(checker)
    assert actual["Pretix API permission: organizer.teams:write"] == "FAIL"
    assert actual["Pretix events inventory access"] == "PASS"
    assert "Pretix team: Ansible Meetup Staff" not in actual
    assert "private response text" not in checker.results[0].detail


@pytest.mark.parametrize("properties", [[], [{"name": "forum_topic_url"}, {"name": "forum_topic_url"}]])
def test_missing_or_duplicate_meta_property_fails(
    monkeypatch: pytest.MonkeyPatch, properties: list[dict[str, Any]]
) -> None:
    monkeypatch.setattr(check_setup, "pretix_list_all", lambda _endpoint: properties)
    checker = check_setup.SetupChecker()

    checker._check_pretix_meta_property()

    assert checker.results[0].status == "FAIL"
    assert "found" in checker.results[0].detail


def test_forum_user_identity_and_city_group_membership(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []

    def request(method: str, endpoint: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        calls.append((method, endpoint))
        if endpoint == "groups.json?page=0":
            return {"groups": [{"name": city.organiser_group} for city in CITIES]}
        if endpoint == "groups.json?page=1":
            return {"groups": []}
        if endpoint == "u/gundalow.json":
            return {"user": {"id": 42, "username": "gundalow"}}
        if endpoint == "admin/users/42.json":
            return {"id": 42, "username": "gundalow", "email": "gundalow@example.com"}
        if endpoint.startswith("groups/"):
            return {"members": [{"username": "gundalow"}]}
        raise AssertionError(f"Unexpected endpoint: {endpoint}")

    monkeypatch.setattr(check_setup, "discourse_req", request)
    checker = check_setup.SetupChecker()
    checker.forum_available = True
    checker.pretix_teams_readable = True
    checker.pretix_teams = [{"name": city.team_name} for city in CITIES]

    checker.check_forum()

    actual = statuses(checker)
    assert actual["Forum API access and user profile"] == "PASS"
    assert actual["Forum Admin API identity: gundalow"] == "PASS"
    for city in CITIES:
        assert actual[f"Forum/Pretix mapping: {city.city}"] == "PASS"
        assert actual[f"Forum group membership: {city.organiser_group}"] == "PASS"
    assert calls and all(method == "GET" for method, _endpoint in calls)


def test_forum_identity_mismatch_and_missing_membership_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    def request(_method: str, endpoint: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        if endpoint == "groups.json?page=0":
            return {"groups": [{"name": city.organiser_group} for city in CITIES]}
        if endpoint == "groups.json?page=1":
            return {"groups": []}
        if endpoint == "u/gundalow.json":
            return {"user": {"id": 42, "username": "gundalow"}}
        if endpoint == "admin/users/42.json":
            return {"id": 84, "username": "someone-else", "email": "hidden@anonymized.invalid"}
        if endpoint.startswith("groups/"):
            return {"members": []}
        raise AssertionError(f"Unexpected endpoint: {endpoint}")

    monkeypatch.setattr(check_setup, "discourse_req", request)
    checker = check_setup.SetupChecker()
    checker.forum_available = True
    checker.pretix_teams_readable = True

    checker.check_forum()

    actual = statuses(checker)
    assert actual["Forum Admin API identity: gundalow"] == "FAIL"
    assert actual[f"Forum group membership: {CITIES[0].organiser_group}"] == "FAIL"


def test_omitted_forum_email_is_manual_not_a_claim_that_email_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        check_setup,
        "discourse_req",
        lambda *_args, **_kwargs: {"id": 42, "username": "gundalow"},
    )
    checker = check_setup.SetupChecker()
    checker.forum_user = {"id": 42, "username": "gundalow"}

    checker._check_forum_user_admin_record()

    assert checker.results[0].status == "MANUAL"
    assert "omitted the email field" in checker.results[0].detail


def test_api_failures_are_sanitized_and_do_not_stop_other_manual_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_method: str, endpoint: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise ApiError(f"token=super-secret-value at {endpoint}")

    monkeypatch.setattr(check_setup, "pretix_req", fail)
    checker = check_setup.SetupChecker()
    checker.pretix_available = True

    checker._check_pretix_settings()
    checker.add_manual_checks()

    assert checker.results[0].status == "FAIL"
    assert "super-secret-value" not in checker.results[0].detail
    assert all(result.status == "MANUAL" for result in checker.results[1:])
    assert any("Pretix auth plugin installed" in result.name for result in checker.results)


def test_required_write_permissions_are_named_and_manual() -> None:
    checker = check_setup.SetupChecker()

    checker.add_manual_checks()

    manual_names = {result.name for result in checker.results if result.status == "MANUAL"}
    assert "Pretix API permission: organizer.settings.general:write" in manual_names
    assert "Pretix API permission: organizer.events:create" in manual_names
    assert "Pretix API permission: event.settings.general:write" in manual_names
    assert "Pretix API permission: event.items:write" in manual_names
    assert "Forum API write permissions" in manual_names


def test_local_configuration_never_displays_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_setup.api, "PRETIX_API_TOKEN", "pretix-secret")
    monkeypatch.setattr(check_setup.api, "DISCOURSE_API_KEY", "forum-secret")
    monkeypatch.setattr(check_setup.api, "PRETIX_URL", "https://rsvp.example")
    checker = check_setup.SetupChecker()

    checker.check_local_configuration()

    assert checker.results[0].status == "PASS"
    assert "pretix-secret" not in checker.results[0].detail
    assert "forum-secret" not in checker.results[0].detail


def test_print_results_fails_only_for_fail_status(capsys: pytest.CaptureFixture[str]) -> None:
    manual = check_setup.CheckResult("MANUAL", "server check", "operator", "unavailable", "inspect")
    failure = check_setup.CheckResult("FAIL", "resource", "GET settings", "missing", "reconcile")

    assert check_setup.print_results([manual]) is False
    manual_output = capsys.readouterr().out
    assert "1 MANUAL" in manual_output
    assert "🔴" not in manual_output
    assert check_setup.print_results([manual, failure]) is True
    failed_output = capsys.readouterr().out
    assert "🔴 FAIL: resource" in failed_output
    assert "1 FAIL" in failed_output
