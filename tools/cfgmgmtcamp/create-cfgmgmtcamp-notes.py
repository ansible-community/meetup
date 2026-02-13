#!/usr/bin/env python3
"""Generate CfgMgmtCamp notes, check for slides, or list talks.

This script downloads the conference schedule and provides three modes:
1. Generates a HackMD-ready markdown file for note-taking during talks
2. Checks which talks have slides/resources available
3. Lists all talks sorted by speaker name with summary statistics
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, cast
from urllib.error import URLError
from urllib.request import urlopen

from jinja2 import Template

# Constants
CFP_BASE_URL = "https://cfp.cfgmgmtcamp.org"
MAIN_DAYS = ["Monday", "Tuesday"]
CONTRIBUTOR_SUMMIT_TALKS = 3

# HackMD notes template (Jinja2)
NOTES_TEMPLATE = """###### tags: `CfgMgmtCamp {{ year }}`

# {{ track }} talks CfgMgmtCamp {{ year }}

- Short link to this HackMD: <https://red.ht/ghent{{ year }}> (ENSURE this is created)
- [Contributor Summit agenda in the forum](https://forum.ansible.com/FIXME) (ENSURE this is created)
- [Ansible Code of Conduct](https://docs.ansible.com/projects/ansible/latest/community/code_of_conduct.html)
- Live stream:
{%- for day in main_days %}
{%- for room in rooms_by_day.get(day, []) %}
    - {{ day }}: Room [{{ room }}](https://www.youtube.com/watch?v=FIXME) UPDATE THIS
{%- endfor %}
{%- endfor %}
    - Wednesday:  [Contributors Summit](https://www.youtube.com/watch?v=FIXME) UPDATE THIS

## Overview

Everybody is welcome to make notes on the talks, especially any ideas, actions and offers to get involved.

{%- for day, talks_for_day in talks_by_day.items() %}

# {{ day }}
{%- for talk in talks_for_day %}

### Talk: {{ talk.title }}

by {{ talk.speakers_str }}

* Slides:{% if talk.resources %}{% for resource in talk.resources %} [{{ resource.description }}]({{ resource.url }}){% if not loop.last %},{% endif %}{% endfor %}{% endif %}
* Video:

#### Abstract

{{ talk.abstract }}

#### Talk summary

#### Ideas & followups

#### Questions
{%- endfor %}
{%- endfor %}

# Contributors Summit
{%- for i in range(1, contributor_summit_talks + 1) %}

### Contributor Summit: Talk {{ i }}

by AUTHOR

* Slides:
* Video:
* ➡️  Forum Posts
    * Post 1
    * Post 2

#### Abstract

#### Talk summary

#### Ideas & followups

#### Questions
{%- endfor %}
{%- if related_talks %}

# Related Talks

The following talks from other tracks also mention {{ track }} in their title or abstract.
{%- for talk in related_talks %}

### Talk: {{ talk.title }}

**Track**: {{ talk.track }}

by {{ talk.speakers_str }}

* Slides:{% if talk.resources %}{% for resource in talk.resources %} [{{ resource.description }}]({{ resource.url }}){% if not loop.last %},{% endif %}{% endfor %}{% endif %}
* Video:

#### Abstract

{{ talk.abstract }}

#### Talk summary

#### Ideas & followups

#### Questions
{%- endfor %}
{%- endif %}
"""


@dataclass(frozen=True)
class Resource:
    """Talk resource (slides, handouts, etc)."""

    url: str
    description: str


@dataclass(frozen=True)
class TalkMetadata:
    """Complete metadata for a conference talk."""

    title: str
    speakers: tuple[str, ...]
    abstract: str
    start_time: str
    url: str
    talk_code: str
    resources: tuple[Resource, ...]
    room: str
    date: str
    day_name: str
    track: str

    @property
    def speakers_str(self) -> str:
        """Get formatted speaker names as a comma-separated string."""
        return ", ".join(self.speakers) if self.speakers else "Unknown"


def get_available_tracks(schedule: dict[str, Any]) -> list[str]:
    """Extract list of available tracks from schedule.

    Args:
        schedule: Parsed schedule JSON

    Returns:
        Sorted list of unique track names
    """
    tracks = set()
    for day in schedule.get("schedule", {}).get("conference", {}).get("days", []):
        for room_data in day.get("rooms", {}).values():
            for talk in room_data:
                if track := talk.get("track"):
                    tracks.add(track)
    return sorted(tracks)


def download_schedule(year: int, location: str = "ghent") -> dict[str, Any]:
    """Download schedule JSON from CFP website.

    Args:
        year: Conference year (e.g., 2026)
        location: Conference location (default: ghent)

    Returns:
        Parsed schedule data as dictionary
    """
    print(f"Downloading schedule for {location}{year}...")
    url = f"{CFP_BASE_URL}/{location}{year}/schedule/export/schedule.json"

    try:
        with urlopen(url) as response:
            data = response.read().decode("utf-8")
            return cast(dict[str, Any], json.loads(data))
    except (URLError, IOError, json.JSONDecodeError) as e:
        print(f"ERROR: Failed to download schedule from {url}: {e}")
        sys.exit(1)


def fetch_talk_resources(
    talk_code: str, year: int, location: str = "ghent"
) -> tuple[Resource, ...]:
    """Fetch resources for a talk from the API.

    Args:
        talk_code: Talk code (e.g., "KU78JX")
        year: Conference year
        location: Conference location (default: ghent)

    Returns:
        List of Resource objects
    """
    resources = []

    try:
        api_url = f"{CFP_BASE_URL}/api/events/{location}{year}/talks/{talk_code}/"
        with urlopen(api_url) as response:
            data = json.loads(response.read().decode("utf-8"))

            for resource_data in data.get("resources", []):
                resource_path = resource_data.get("resource", "")
                description = resource_data.get("description", "")

                if resource_path:
                    full_url = f"{CFP_BASE_URL}{resource_path}"
                    resources.append(Resource(url=full_url, description=description))

    except (URLError, IOError, json.JSONDecodeError):
        # API fetch failed, continuing without resources
        # This is expected for talks that don't have uploaded resources
        pass

    return tuple(resources)


def _extract_talks(
    schedule: dict[str, Any],
    filter_func: Callable[[dict[str, Any]], bool],
    year: int,
    location: str = "ghent",
) -> list[TalkMetadata]:
    """Extract talks from schedule using provided filter function.

    Args:
        schedule: Parsed schedule JSON
        filter_func: Function that takes talk_data dict and returns True to include talk
        year: Conference year
        location: Conference location (default: ghent)

    Returns:
        List of TalkMetadata objects for Monday and Tuesday only
    """
    talks = []

    conference_days = schedule.get("schedule", {}).get("conference", {}).get("days", [])

    # Build date to day name mapping more safely
    date_to_day = {}
    for idx, day in enumerate(conference_days):
        if idx < len(MAIN_DAYS) and "date" in day:
            date_to_day[day["date"]] = MAIN_DAYS[idx]

    # Extract talks from each day/room
    for day in conference_days:
        date = day.get("date", "")
        day_name = date_to_day.get(date, "Unknown")

        # Only process Monday and Tuesday (Wednesday is Contributor Summit)
        if day_name not in MAIN_DAYS:
            continue

        for room_name, room_data in day.get("rooms", {}).items():
            for talk_data in room_data:
                # Apply filter function to determine if talk should be included
                if not filter_func(talk_data):
                    continue

                # Extract speaker names (filter empty strings)
                speakers = tuple(
                    speaker
                    for person in talk_data.get("persons", [])
                    if (speaker := person.get("public_name", ""))
                )

                # Extract talk code from URL
                talk_code = ""
                talk_url = talk_data.get("url", "")
                if "/talk/" in talk_url:
                    parts = talk_url.split("/talk/")
                    if len(parts) > 1 and parts[1]:
                        talk_code = parts[1].rstrip("/")

                # Fetch resources from API
                resources = (
                    fetch_talk_resources(talk_code, year, location=location)
                    if talk_code
                    else ()
                )

                talks.append(
                    TalkMetadata(
                        title=talk_data.get("title", ""),
                        speakers=speakers,
                        abstract=talk_data.get("abstract", ""),
                        start_time=talk_data.get("start", ""),
                        url=talk_data.get("url", ""),
                        talk_code=talk_code,
                        resources=resources,
                        room=room_name,
                        date=date,
                        day_name=day_name,
                        track=talk_data.get("track", ""),
                    )
                )

    return talks


def extract_talks_for_track(
    schedule: dict[str, Any], track: str, year: int, location: str = "ghent"
) -> list[TalkMetadata]:
    """Extract all talks for specified track from schedule.

    Args:
        schedule: Parsed schedule JSON
        track: Track name to filter (e.g., "Ansible")
        year: Conference year
        location: Conference location (default: ghent)

    Returns:
        List of TalkMetadata objects for Monday and Tuesday only
    """
    def filter_func(talk_data: dict[str, Any]) -> bool:
        return talk_data.get("track") == track

    return _extract_talks(schedule, filter_func, year, location)


def extract_related_talks(
    schedule: dict[str, Any],
    track: str,
    track_keyword: str,
    year: int,
    location: str = "ghent",
) -> list[TalkMetadata]:
    """Extract talks from OTHER tracks that mention the track keyword.

    Args:
        schedule: Parsed schedule JSON
        track: Track name to exclude (e.g., "Ansible")
        track_keyword: Keyword to search for in title/abstract (case-insensitive)
        year: Conference year
        location: Conference location (default: ghent)

    Returns:
        List of TalkMetadata objects from other tracks that mention the keyword
    """
    def filter_func(talk_data: dict[str, Any]) -> bool:
        # Exclude talks from the main track
        if talk_data.get("track") == track:
            return False

        # Only include if keyword appears in title or abstract (case-insensitive)
        title = talk_data.get("title", "")
        abstract = talk_data.get("abstract", "")
        keyword_lower = track_keyword.lower()

        return keyword_lower in title.lower() or keyword_lower in abstract.lower()

    return _extract_talks(schedule, filter_func, year, location)


def list_talks(talks: list[TalkMetadata]) -> None:
    """List all talks with speaker names and titles, sorted by speaker name.

    Args:
        talks: List of talk metadata
    """
    print("\nTalk List")
    print("=" * 80)

    # Sort talks by first speaker name (or "Unknown" if no speakers)
    sorted_talks = sorted(
        talks, key=lambda t: t.speakers[0] if t.speakers else "Unknown"
    )

    # Calculate unique speakers
    unique_speakers = {speaker for talk in talks for speaker in talk.speakers}

    for talk in sorted_talks:
        print(f"{talk.speakers_str}, {talk.title}")

    # Print summary
    print("=" * 80)
    print(f"Total: {len(unique_speakers)} unique speakers, {len(talks)} talks")


def check_for_slides(talks: list[TalkMetadata]) -> None:
    """Print slide availability for all talks.

    Args:
        talks: List of talk metadata
    """
    print("\nSlide Availability Report")
    print("=" * 80)

    for talk in talks:
        print(f"\n{talk.day_name} | {talk.start_time}")
        print(f"  Title: {talk.title}")
        print(f"  Presenter: {talk.speakers_str}")

        if talk.resources:
            print("  Resources:")
            for resource in talk.resources:
                print(f"    - ✅ [{resource.description}]({resource.url})")
        else:
            print("  Resources: ❌ No resources")


def generate_notes(
    talks: list[TalkMetadata], related_talks: list[TalkMetadata], year: int, track: str
) -> str:
    """Generate HackMD-ready markdown for conference notes.

    Args:
        talks: List of talk metadata (main conference days only)
        related_talks: List of related talks from other tracks
        year: Conference year
        track: Track name for title

    Returns:
        Markdown content
    """
    # Extract unique rooms by day
    rooms_by_day_sorted = {
        day: sorted({talk.room for talk in talks if talk.day_name == day})
        for day in MAIN_DAYS
    }

    # Group talks by day for day-level headings
    talks_by_day: dict[str, list[dict[str, Any]]] = {day: [] for day in MAIN_DAYS}
    for talk in talks:
        talk_data = {
            "title": talk.title,
            "speakers_str": talk.speakers_str,
            "abstract": "\n".join(line.rstrip() for line in talk.abstract.split("\n")),
            "resources": [
                {"description": r.description, "url": r.url} for r in talk.resources
            ],
        }
        talks_by_day[talk.day_name].append(talk_data)

    # Transform related talks data for template
    related_talks_data = []
    for talk in related_talks:
        talk_dict = {
            "title": talk.title,
            "track": talk.track,
            "speakers_str": talk.speakers_str,
            "abstract": "\n".join(line.rstrip() for line in talk.abstract.split("\n")),
            "resources": [
                {"description": r.description, "url": r.url} for r in talk.resources
            ],
        }
        related_talks_data.append(talk_dict)

    template = Template(NOTES_TEMPLATE)
    return template.render(
        year=year,
        track=track,
        main_days=MAIN_DAYS,
        rooms_by_day=rooms_by_day_sorted,
        talks_by_day=talks_by_day,
        contributor_summit_talks=CONTRIBUTOR_SUMMIT_TALKS,
        related_talks=related_talks_data,
    )


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate CfgMgmtCamp notes, check for slides, or list talks"
    )
    parser.add_argument(
        "--year", type=int, required=True, help="Conference year (e.g., 2026)"
    )
    parser.add_argument(
        "--track",
        type=str,
        default="ansible",
        help="Track name to filter talks (e.g., Ansible, Foreman, Pulp). Case-insensitive, converted to title case. Default: ansible",
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--generate-notes",
        action="store_true",
        help="Generate HackMD-ready notes file",
    )
    mode_group.add_argument(
        "--check-for-slides", action="store_true", help="Check slide availability"
    )
    mode_group.add_argument(
        "--list-talks", action="store_true", help="List speaker names and talk titles"
    )

    args = parser.parse_args()

    # Normalize track name to title case (ansible → Ansible)
    track = args.track.strip().title()

    print(f"CfgMgmtCamp {args.year}")
    print(f"Track: {track}")

    # Download schedule
    schedule = download_schedule(args.year)

    # Extract talks (Monday & Tuesday only)
    print("\nExtracting talks...")
    talks = extract_talks_for_track(schedule, track, args.year, location="ghent")

    if not talks:
        available = get_available_tracks(schedule)
        print(f"ERROR: No talks found for track '{track}'")
        print(f"Available tracks: {', '.join(available)}")
        sys.exit(1)

    # Sort by date and start time
    talks.sort(key=lambda t: (t.date, t.start_time))

    print(f"Found {len(talks)} talks")

    # Execute requested mode
    if args.list_talks:
        list_talks(talks)
    elif args.check_for_slides:
        check_for_slides(talks)
    else:
        # Generate notes
        print("\nExtracting related talks...")
        track_keyword = track
        related_talks = extract_related_talks(
            schedule, track, track_keyword, args.year, location="ghent"
        )
        print(f"Found {len(related_talks)} related talks from other tracks")
        related_talks.sort(key=lambda t: (t.date, t.start_time))

        markdown = generate_notes(talks, related_talks, args.year, track)
        safe_track = track.lower().replace("/", "_").replace("\\", "_")
        output_path = Path(f"cfgmgmtcamp{args.year}_{safe_track}_notes.md")
        try:
            output_path.write_text(markdown)
            print(f"\nGenerated: {output_path.absolute()}")
            print("Ready to upload to HackMD!")
        except IOError as e:
            print(f"ERROR: Failed to write {output_path}: {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
