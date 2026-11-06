# Meetup locations and events

Explore Ansible meetup locations on the interactive map or browse them by region. The page also lists upcoming events from the [Forum Events category](https://forum.ansible.com/c/events/8), including their date, attendance format, and whether they repeat when that information is available.

Set your [Forum event locations](https://forum.ansible.com/my/preferences/profile#user_event_cities) to get notices for meetups near you.

<a class="md-button md-button--primary" href="../meetup-worldmap.html">Open the interactive meetup map</a>

<iframe src="../meetup-worldmap.html" title="Interactive Ansible meetup map" style="width:100%;height:82vh;min-height:700px;border:1px solid #d7dde2;border-radius:8px" loading="lazy"></iframe>

## Regenerate the page

The committed HTML page is generated from the canonical location list in `tools/common/ansible_event_cities.py` and the public Discourse event feed. After adding or changing meetup locations, run this command from the repository root:

```bash
uv run python tools/website/generate_worldmap.py
```

Add `-v` to see timestamped progress and the generation runtime:

```bash
uv run python tools/website/generate_worldmap.py -v
```

The generator reads city coordinates from `CityInfo` in `tools/common/ansible_event_cities.py` and updates `docs/meetup-worldmap.html`. It fetches upcoming topics from `https://forum.ansible.com/c/events/8.json`; it no longer geocodes cities during generation. Review and commit the location registry and generated HTML when locations change, and regenerate when the event snapshot needs refreshing.

If event data cannot be fetched, the generator still writes the locations page and shows the Forum Events link in place of event cards. For local preview, run `uv run python -m http.server 8000 --directory docs` from the repository root, then open `http://localhost:8000/meetup-worldmap.html`. Serving it over HTTP avoids browser restrictions that can affect JavaScript modules and map requests opened with `file://`.
