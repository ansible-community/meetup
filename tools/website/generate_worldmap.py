#!/usr/bin/env python3
"""Generate the public Ansible meetup locations map."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/meetup-worldmap.html"
MAP_MARKER_COLOR = "#5bbdbf"
LOGGER = logging.getLogger("meetup_worldmap")


def normalise_region(region: str) -> str:
    """Map historical registry labels onto current broad regions."""
    return {
        "APAC": "Asia Pacific",
        "EMEA": "Europe, Middle East and Africa",
        "Europe": "Europe, Middle East and Africa",
        "LATAM": "Latin America",
        "NA": "Americas",
    }.get(region, region)


def render_page(locations: list[dict[str, object]], generated_at: str) -> str:
    """Render a self-contained interactive meetup-location map and directory."""
    payload = json.dumps({"locations": locations, "generated_at": generated_at}, ensure_ascii=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    safe_json = payload
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Ansible Meetup locations</title>
<link rel="icon" type="image/png" href="https://raw.githubusercontent.com/ansible/logos/refs/heads/main/community-marks/Ansible-Community-Mark-Pool.png">
<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Red+Hat+Display:300,300i,400,400i,700,700i%7CRed+Hat+Mono:400,400i,700,700i&display=fallback">
<link rel="stylesheet" href="assets/stylesheets/ansible.css">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@^5/dist/maplibre-gl.css">
<style>
:root {{
  color-scheme: light dark;
  --brand: #5bbdbf;
  --ink: #000000de;
  --muted: #52606d;
  --line: #d7dde2;
  --surface: #fff;
  --soft: #f4f6f8;
  --link: #2980b9;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; color: var(--ink); font: 16px/1.55 "Red Hat Display", -apple-system, BlinkMacSystemFont, Helvetica, Arial, sans-serif; background: var(--surface); }}
main {{ max-width: 1440px; margin: auto; padding: 24px clamp(16px, 3vw, 40px) 48px; }}
h1 {{ font-size: clamp(2rem, 3vw, 2.7rem); line-height: 1.15; margin: .3em 0; }}
h2 {{ font-size: 1.55rem; margin: 1.4em 0 .5em; }}
p {{ color: var(--muted); }}
a {{ color: var(--link); }}
.brand-label, .subtle {{ font-size: .86rem; }}
.intro {{ max-width: 850px; margin-bottom: 1.25rem; }}
.controls {{ display: flex; gap: 10px; flex-wrap: wrap; margin: 18px 0; }}
input, select {{ font: inherit; padding: 10px 12px; border: 1px solid #9aa4ae; border-radius: 4px; color: var(--ink); background: var(--surface); }}
input {{ min-width: 230px; flex: 1; }}
button, .subscribe {{ font: inherit; display: inline-block; padding: 7px 11px; border-radius: 4px; border: 1px solid var(--brand); background: color-mix(in srgb, var(--brand) 12%, var(--surface)); color: var(--ink); text-decoration: none; cursor: pointer; white-space: nowrap; }}
button:hover, .subscribe:hover {{ background: color-mix(in srgb, var(--brand) 24%, var(--surface)); }}
button:focus-visible, a:focus-visible, input:focus-visible, select:focus-visible {{ outline: 3px solid var(--link); outline-offset: 2px; }}
.map-wrap {{ position: relative; }}
#map {{ height: min(65vh, 650px); min-height: 390px; border: 1px solid var(--line); border-radius: 4px; z-index: 0; }}
.map-note {{ font-size: .85rem; margin: .45em 0; }}
.marker-count {{ font-weight: 700; align-self: center; }}
.region {{ border-top: 1px solid var(--line); padding: 10px 0; }}
.region summary {{ font-weight: 700; cursor: pointer; font-size: 1.1rem; }}
.country {{ margin: 14px 0 7px; font-size: .96rem; color: var(--muted); }}
.location-list {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr)); gap: 10px; margin-top: 8px; }}
.location {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; width: min(100%, 430px); min-height: 64px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 4px; background: var(--surface); }}
.location h3 {{ font-size: 1rem; line-height: 1.3; margin: 0; }}
.subscribe {{ font-size: .86rem; padding: 6px 9px; }}
.maplibregl-popup-content {{ color: var(--ink); font: inherit; }}
.maplibregl-popup-content .subscribe {{ margin-top: 8px; }}
.maplibregl-ctrl-group {{ border-radius: 4px !important; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --ink: #f1f3f4; --muted: #c4c9ce; --line: #4b5258; --surface: #202428; --soft: #2b3035; --link: #8ab4f8; }}
}}
@media (max-width: 600px) {{
  #map {{ height: 55vh; min-height: 330px; }}
  .location {{ align-items: flex-start; flex-direction: column; gap: 8px; }}
}}
</style>
</head>
<body>
<main>
  <p class="brand-label">Ansible Community Meetups</p>
  <h1>Find your local Ansible meetup</h1>
  <p class="intro">Explore meetup communities around the world. Search by city or browse locations by region, then select a map circle or city to find its community link.</p>
  <div class="controls">
    <input id="search" type="search" placeholder="Search city or country" aria-label="Search locations">
    <select id="region-filter" aria-label="Filter by region"><option value="">All regions</option></select>
    <span id="location-count" class="marker-count" aria-live="polite"></span>
  </div>
  <div class="map-wrap">
    <div id="map" role="application" aria-label="Interactive map of Ansible meetup locations"></div>
  </div>
  <p class="map-note"><span id="map-status" aria-live="polite"></span> Map style <a href="https://openfreemap.org/">OpenFreeMap</a> © <a href="https://openmaptiles.org/">OpenMapTiles</a>; data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>.</p>
  <h2>Meetup locations by region</h2>
  <div id="regions"></div>
  <p class="subtle">Page data generated {html.escape(generated_at)}. Questions? Visit the <a href="https://forum.ansible.com/c/ansible-community/">Ansible Community Forum</a>.</p>
</main>
<script id="meetup-data" type="application/json">{safe_json}</script>
<script src="https://unpkg.com/maplibre-gl@^5/dist/maplibre-gl.js"></script>
<script>
const locations = JSON.parse(document.getElementById('meetup-data').textContent).locations;
const regions = [...new Set(locations.map(location => location.region))].sort();
const map = new maplibregl.Map({{container: 'map', style: 'https://tiles.openfreemap.org/styles/liberty', center: [0, 20], zoom: 1.2}});
map.addControl(new maplibregl.NavigationControl(), 'top-right');
map.addControl(new maplibregl.FullscreenControl(), 'top-right');
const regionSelect = document.getElementById('region-filter');
regions.forEach(region => {{
  const option = document.createElement('option');
  option.value = region;
  option.textContent = region;
  regionSelect.append(option);
}});
function esc(value) {{
  return String(value).replace(/[&<>"']/g, character => ({{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}}[character]));
}}
function featureCollection(rows) {{
  return {{
    type: 'FeatureCollection',
    features: rows.map(location => ({{
      type: 'Feature',
      geometry: {{type: 'Point', coordinates: [location.lon, location.lat]}},
      properties: {{slug: location.slug, city: location.city, country: location.country}}
    }}))
  }};
}}
function renderLocations() {{
  const query = document.getElementById('search').value.trim().toLowerCase();
  const selectedRegion = regionSelect.value;
  const shown = locations.filter(location =>
    (!selectedRegion || location.region === selectedRegion) &&
    (!query || `${{location.city}} ${{location.country}}`.toLowerCase().includes(query))
  );
  document.getElementById('location-count').textContent = `${{shown.length}} of ${{locations.length}} locations`;
  const source = map.getSource('meetup-locations');
  if (source) source.setData(featureCollection(shown));
  document.getElementById('map-status').textContent = `${{shown.length}} locations shown. Click a circle to zoom in, or a pin for details.`;

  const host = document.getElementById('regions');
  host.replaceChildren();
  regions.filter(region => !selectedRegion || region === selectedRegion).forEach(region => {{
    const regionRows = shown.filter(location => location.region === region);
    if (!regionRows.length) return;
    const details = document.createElement('details');
    details.className = 'region';
    details.open = Boolean(query || selectedRegion);
    const summary = document.createElement('summary');
    summary.textContent = `${{region}} · ${{regionRows.length}} locations`;
    details.append(summary);

    [...new Set(regionRows.map(location => location.country))].sort().forEach(country => {{
      const countryRows = regionRows
        .filter(location => location.country === country)
        .sort((first, second) => first.city.localeCompare(second.city));
      const heading = document.createElement('h3');
      heading.className = 'country';
      heading.textContent = `${{country}} · ${{countryRows.length}}`;
      details.append(heading);
      const grid = document.createElement('div');
      grid.className = 'location-list';
      countryRows.forEach(location => {{
        const card = document.createElement('article');
        card.className = 'location';
        card.innerHTML = `<h3>${{esc(location.city)}}</h3><a class="subscribe" href="https://forum.ansible.com/my/preferences/profile#user_event_cities">Get event notices</a>`;
        grid.append(card);
      }});
      details.append(grid);
    }});
    host.append(details);
  }});
}}
function expandCluster(event) {{
  const feature = event.features?.[0];
  if (!feature) return;
  map.getSource('meetup-locations').getClusterExpansionZoom(feature.properties.cluster_id, (error, zoom) => {{
    if (!error) map.easeTo({{center: feature.geometry.coordinates, zoom}});
  }});
}}
map.on('load', () => {{
  map.addSource('meetup-locations', {{
    type: 'geojson', data: featureCollection(locations), cluster: true, clusterMaxZoom: 5, clusterRadius: 48
  }});
  map.addLayer({{
    id: 'meetup-clusters', type: 'circle', source: 'meetup-locations', filter: ['has', 'point_count'],
    paint: {{'circle-color': '{MAP_MARKER_COLOR}', 'circle-radius': ['step', ['get', 'point_count'], 15, 10, 19, 50, 24], 'circle-stroke-width': 2, 'circle-stroke-color': '#fff'}}
  }});
  map.addLayer({{
    id: 'meetup-cluster-count', type: 'symbol', source: 'meetup-locations', filter: ['has', 'point_count'],
    layout: {{'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12}},
    paint: {{'text-color': '#fff'}}
  }});
  map.addLayer({{
    id: 'meetup-points', type: 'circle', source: 'meetup-locations', filter: ['!', ['has', 'point_count']],
    paint: {{'circle-color': '{MAP_MARKER_COLOR}', 'circle-radius': 7, 'circle-stroke-width': 2, 'circle-stroke-color': '#fff'}}
  }});

  const bounds = new maplibregl.LngLatBounds();
  locations.forEach(location => bounds.extend([location.lon, location.lat]));
  map.fitBounds(bounds, {{padding: 24, maxZoom: 1.6, duration: 0}});
  map.on('click', 'meetup-clusters', expandCluster);
  map.on('click', 'meetup-cluster-count', expandCluster);
  map.on('click', 'meetup-points', event => {{
    const location = event.features[0].properties;
    const popup = `<strong>${{esc(location.city)}}</strong><br>${{esc(location.country)}}<br><a class="subscribe" href="https://forum.ansible.com/my/preferences/profile#user_event_cities">Get event notices</a>`;
    new maplibregl.Popup({{offset: 12}}).setLngLat(event.features[0].geometry.coordinates).setHTML(popup).addTo(map);
  }});
  ['meetup-clusters', 'meetup-cluster-count', 'meetup-points'].forEach(layer => {{
    map.on('mouseenter', layer, () => map.getCanvas().style.cursor = 'pointer');
    map.on('mouseleave', layer, () => map.getCanvas().style.cursor = '');
  }});
  renderLocations();
}});
document.getElementById('search').addEventListener('input', renderLocations);
regionSelect.addEventListener('change', renderLocations);
renderLocations();
</script>
</body>
</html>"""


def main() -> None:
    """Build the generated HTML page from the canonical location registry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="HTML output path (default: docs/meetup-worldmap.html)",
    )
    parser.add_argument("-v", action="store_true", help="show timestamped progress logs")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s" if args.v else "%(levelname)s: %(message)s",
    )
    sys.path.insert(0, str(ROOT))
    from tools.common.ansible_event_cities import CITIES

    locations = [
        {
            "slug": city.slug,
            "city": city.city,
            "country": city.country,
            "region": normalise_region(city.region),
            "lat": city.latitude,
            "lon": city.longitude,
        }
        for city in CITIES
    ]
    LOGGER.info("Loaded canonical coordinates for %s locations", len(locations))
    started_at = time.monotonic()
    generated_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_page(locations, generated_at), encoding="utf-8")
    LOGGER.info(
        "Generated %s (%s locations) in %.1f seconds",
        args.output,
        len(locations),
        time.monotonic() - started_at,
    )


if __name__ == "__main__":
    main()
