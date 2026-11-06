# Generate the meetup map

## Regenerate the page

The public map is generated from the canonical location list in `tools/common/ansible_event_cities.py`. After adding or changing meetup locations, run this command from the repository root:

```bash
uv run python tools/website/generate_worldmap.py
```

Add `-v` to see timestamped progress and the generation runtime:

```bash
uv run python tools/website/generate_worldmap.py -v
```

The generator reads city names, regions, timezones, and coordinates from `CityInfo` in `tools/common/ansible_event_cities.py` and updates `docs/map.html`. It does not look up or geocode locations. Review and commit the location registry and generated HTML when locations change.

For local preview, run `uv run python -m http.server 8000 --directory docs` from the repository root, then open `http://localhost:8000/map.html`. Serving it over HTTP avoids browser restrictions that can affect map requests opened with `file://`.
