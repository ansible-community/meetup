# Meetup locations

Explore Ansible meetup locations on the interactive map or browse them by region and country.

<a class="md-button md-button--primary" href="../meetup-worldmap.html">Open the interactive meetup map</a>

<iframe src="../meetup-worldmap.html" title="Interactive Ansible meetup map" style="width:100%;height:82vh;min-height:700px;border:1px solid #d7dde2;border-radius:8px" loading="lazy" allowfullscreen></iframe>

## Regenerate the page

The committed HTML page is generated from the canonical location list in `tools/common/ansible_event_cities.py`. After adding or changing meetup locations, run this command from the repository root:

```bash
uv run python tools/website/generate_worldmap.py
```

Add `-v` to see timestamped progress and the generation runtime:

```bash
uv run python tools/website/generate_worldmap.py -v
```

The generator reads city coordinates from `CityInfo` in `tools/common/ansible_event_cities.py` and updates `docs/meetup-worldmap.html`. It does not look up or geocode locations. Review and commit the location registry and generated HTML when locations change.

For local preview, run `uv run python -m http.server 8000 --directory docs` from the repository root, then open `http://localhost:8000/meetup-worldmap.html`. Serving it over HTTP avoids browser restrictions that can affect JavaScript modules and map requests opened with `file://`.
