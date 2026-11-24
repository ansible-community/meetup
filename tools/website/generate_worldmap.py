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
OUTPUT = ROOT / "docs/map.html"
MAP_MARKER_COLOR = "#5bbdbf"
LOGGER = logging.getLogger(__name__)


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
    from tools.common.ansible_events_lib import DISCOURSE_URL

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
  --brand: {MAP_MARKER_COLOR};
  --ink: #000000de;
  --muted: #52606d;
  --line: #d7dde2;
  --surface: #fff;
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
.controls label {{ display: flex; align-items: center; gap: 8px; }}
.discovery-grid {{ display: flex; flex-direction: column; gap: 20px; }}
.results-panel, .map-panel {{ min-width: 0; }}
.results-panel h2 {{ margin-top: 0; }}
#results {{ max-height: min(72vh, 780px); overflow: auto; border: 1px solid var(--line); border-radius: 4px; padding: 8px 12px; }}
.region {{ border-bottom: 1px solid var(--line); padding: 8px 0; }}
.region:last-child {{ border-bottom: 0; }}
.region summary {{ font-weight: 700; cursor: pointer; font-size: 1.05rem; }}
.country {{ margin: 12px 0 5px; font-size: .9rem; color: var(--muted); }}
.location-list {{ display: grid; gap: 7px; }}
.location {{ display: flex; align-items: center; gap: 10px; width: 100%; min-height: 62px; padding: 8px; border: 1px solid var(--line); border-radius: 4px; background: var(--surface); }}
.location.is-selected {{ border-color: var(--brand); box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand) 28%, transparent); }}
.location-select {{ flex: 1; min-width: 0; padding: 3px; border: 0; background: transparent; text-align: left; white-space: normal; }}
.location-select:hover {{ background: transparent; }}
.location-select strong, .location-select span, .location-select small {{ display: block; }}
.location-select strong {{ font-size: 1rem; }}
.location-select span {{ color: var(--muted); }}
.location-select small {{ color: var(--muted); font-family: "Red Hat Mono", monospace; font-size: .78rem; }}
.subscribe {{ font-size: .8rem; padding: 6px 8px; }}
.luma-subscribe-btn {{ display: inline-flex; align-items: center; gap: 6px; padding: 10px 18px; border: 0; border-radius: 8px; background: #c4121a; color: #fff; font-size: 15px; font-weight: 600; text-decoration: none; transition: background-color .2s ease, transform .1s ease; }}
.luma-subscribe-btn:hover {{ background: #a80f16; color: #fff; transform: translateY(-1px); }}
.community-links {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 250px), 1fr)); gap: 12px; margin: 24px 0; }}
.community-link {{ min-width: 0; padding: 16px; border: 1px solid var(--line); border-radius: 6px; background: color-mix(in srgb, var(--surface) 96%, var(--brand)); }}
.community-link p {{ margin: 8px 0 0; font-size: .9rem; }}
#map {{ height: min(72vh, 780px); min-height: 430px; border: 1px solid var(--line); border-radius: 4px; z-index: 0; }}
.map-panel h2 {{ margin-top: 0; }}
.map-note {{ font-size: .85rem; margin: .45em 0; }}
.marker-count {{ font-weight: 700; align-self: center; }}
.maplibregl-popup-content {{ color: var(--ink) !important; background: var(--surface) !important; font: inherit; }}
.maplibregl-popup-content .subscribe {{ display: inline-block; margin-top: 8px; }}
.maplibregl-popup-close-button {{ color: var(--ink); background: transparent; font-size: 1.25rem; }}
.maplibregl-popup-close-button:hover {{ background: transparent; }}
.maplibregl-popup-anchor-bottom .maplibregl-popup-tip {{ border-top-color: var(--surface); }}
.maplibregl-popup-anchor-top .maplibregl-popup-tip {{ border-bottom-color: var(--surface); }}
.maplibregl-popup-anchor-left .maplibregl-popup-tip {{ border-right-color: var(--surface); }}
.maplibregl-popup-anchor-right .maplibregl-popup-tip {{ border-left-color: var(--surface); }}
.maplibregl-ctrl-group {{ border-radius: 4px !important; background: var(--surface) !important; border: 1px solid var(--line) !important; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --ink: #f1f3f4; --muted: #c4c9ce; --line: #4b5258; --surface: #202428; --link: #8ab4f8; }}
  .maplibregl-ctrl button {{ filter: invert(1); }}
}}
@media (max-width: 760px) {{
  #results {{ max-height: none; }}
  #map {{ height: 62vh; min-height: 340px; }}
}}
@media (max-width: 480px) {{
  .controls {{ display: grid; }}
  .controls input {{ min-width: 0; }}
  .location {{ align-items: flex-start; }}
  .subscribe {{ white-space: normal; }}
}}
</style>
</head>
<body>
<main>
  <h1>Find your local Ansible meetup</h1>
  <p class="intro">Search by city, country, or region to find a nearby Ansible meetup. Choose a location to see it on the map.</p>
  <div class="controls">
    <input id="search" type="search" placeholder="Search city, country, or region" aria-label="Search city, country, or region">
    <label>Browse by region
      <select id="region-filter" aria-label="Browse by region"><option value="">All regions</option></select>
    </label>
    <span id="location-count" class="marker-count" aria-live="polite"></span>
  </div>
  <div class="discovery-grid">
    <section class="map-panel" aria-labelledby="map-heading">
      <h2 id="map-heading">Meetup map</h2>
      <div id="map" role="application" aria-label="Interactive map of Ansible meetup locations"></div>
      <p class="map-note"><span id="map-status" aria-live="polite"></span> Map style <a href="https://openfreemap.org/">OpenFreeMap</a> © <a href="https://openmaptiles.org/">OpenMapTiles</a>; data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>.</p>
    </section>
    <section class="results-panel" aria-labelledby="results-heading">
      <h2 id="results-heading">Meetup locations</h2>
      <div id="results" aria-live="polite"></div>
    </section>
  </div>
  <section aria-labelledby="community-links-heading">
    <h2 id="community-links-heading">Stay connected</h2>
    <div class="community-links">
      <article class="community-link">
        <a class="subscribe" href="https://forum.ansible.com/c/news/bullhorn/17" target="_blank" rel="noopener noreferrer">Subscribe to the Ansible Bullhorn</a>
        <p>Open the Bullhorn category, select the bell, then choose Watching.</p>
      </article>
      <article class="community-link">
        <a class="luma-subscribe-btn" href="https://luma.com/ansible-community" target="_blank" rel="noopener noreferrer"><svg aria-hidden="true" focusable="false" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2z"/></svg>Follow on Luma</a>
        <p>The Ansible Community calendar shares some, but not all, Ansible events.</p>
      </article>
      <article class="community-link">
        <a class="subscribe" href="https://forum.ansible.com/discourse-post-event/events.ics" target="_blank" rel="noopener noreferrer">Subscribe to all Forum events (ICS)</a>
        <p>Add the Forum's all-events calendar feed to your calendar app.</p>
      </article>
    </div>
  </section>
  <p class="subtle">Page data generated {html.escape(generated_at)}. Questions? Visit the <a href="{DISCOURSE_URL}/c/ansible-community/">Ansible Community Forum</a>.</p>
</main>
<script id="meetup-data" type="application/json">{safe_json}</script>
<script src="https://unpkg.com/maplibre-gl@^5/dist/maplibre-gl.js"></script>
<script>
const locations = JSON.parse(document.getElementById('meetup-data').textContent).locations;
const regions = [...new Set(locations.map(location => location.region))].sort();
const colorScheme = window.matchMedia('(prefers-color-scheme: dark)');
const styleFor = isDark => `https://tiles.openfreemap.org/styles/${{isDark ? 'dark' : 'liberty'}}`;
let activeStyle = styleFor(colorScheme.matches);
const map = new maplibregl.Map({{container: 'map', style: activeStyle, center: [0, 20], zoom: 1.2}});
map.addControl(new maplibregl.NavigationControl(), 'top-right');
map.addControl(new maplibregl.FullscreenControl(), 'top-right');
const regionSelect = document.getElementById('region-filter');
const searchInput = document.getElementById('search');
const results = document.getElementById('results');
let selectedSlug = null;
let mapReady = false;
let initialViewSet = false;
regions.forEach(region => {{
  const option = document.createElement('option');
  option.value = region;
  option.textContent = region;
  regionSelect.append(option);
}});
function esc(value) {{
  return String(value).replace(/[&<>"']/g, character => ({{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}}[character]));
}}
function normaliseSearch(value) {{
  return value.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLocaleLowerCase();
}}
function searchMatches(location, query) {{
  if (!query) return true;
  const fields = [location.city, location.slug, location.country, location.region, location.timezone]
    .map(normaliseSearch);
  const compactQuery = query.replace(/[^\\p{{L}}\\p{{N}}]/gu, '');
  if (!compactQuery) return false;
  return fields.some(field => field.includes(query) || field.replace(/[^\\p{{L}}\\p{{N}}]/gu, '').includes(compactQuery));
}}
function formatTimezone(timezone) {{
  const now = new Date();
  const name = new Intl.DateTimeFormat(undefined, {{timeZone: timezone, timeZoneName: 'longGeneric'}})
    .formatToParts(now).find(part => part.type === 'timeZoneName')?.value;
  const offset = new Intl.DateTimeFormat(undefined, {{timeZone: timezone, timeZoneName: 'shortOffset'}})
    .formatToParts(now).find(part => part.type === 'timeZoneName')?.value.replace('GMT', 'UTC');
  return offset ? `${{name}} · ${{offset}}` : (name || timezone);
}}
function featureCollection(rows) {{
  return {{
    type: 'FeatureCollection',
    features: rows.map(location => ({{
      type: 'Feature',
      geometry: {{type: 'Point', coordinates: [location.lon, location.lat]}},
      properties: {{slug: location.slug, city: location.city, country: location.country, selected: location.slug === selectedSlug}}
    }}))
  }};
}}
function renderLocations() {{
  const query = normaliseSearch(searchInput.value.trim());
  const selectedRegion = regionSelect.value;
  const shown = locations.filter(location =>
    (!selectedRegion || location.region === selectedRegion) &&
    searchMatches(location, query)
  ).sort((first, second) => first.city.localeCompare(second.city));
  document.getElementById('location-count').textContent = `${{shown.length}} of ${{locations.length}} locations`;
  const source = map.getSource('meetup-locations');
  if (source) source.setData(featureCollection(shown));
  document.getElementById('map-status').textContent = `${{shown.length}} locations shown. Click a circle to zoom in, or a pin for details.`;

  results.replaceChildren();
  if (!shown.length) {{
    const empty = document.createElement('p');
    empty.textContent = 'No meetup locations match that search.';
    results.append(empty);
    return;
  }}
  regions.filter(region => !selectedRegion || region === selectedRegion).forEach(region => {{
    const regionRows = shown.filter(location => location.region === region);
    if (!regionRows.length) return;
    const details = document.createElement('details');
    details.className = 'region';
    details.open = true;
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
        card.className = `location${{location.slug === selectedSlug ? ' is-selected' : ''}}`;
        card.id = `location-${{location.slug}}`;
        const select = document.createElement('button');
        select.type = 'button';
        select.className = 'location-select';
        select.setAttribute('aria-pressed', String(location.slug === selectedSlug));
        const city = document.createElement('strong');
        city.textContent = location.city;
        const country = document.createElement('span');
        country.textContent = location.country;
        const timezone = document.createElement('small');
        timezone.textContent = formatTimezone(location.timezone);
        select.append(city, country, timezone);
        select.addEventListener('click', () => selectLocation(location.slug));
        card.append(select);
        grid.append(card);
      }});
      details.append(grid);
    }});
    results.append(details);
  }});
}}
function selectLocation(slug, fromMap = false) {{
  const location = locations.find(candidate => candidate.slug === slug);
  if (!location) return;
  selectedSlug = slug;
  renderLocations();
  if (mapReady && !fromMap) map.flyTo({{center: [location.lon, location.lat], zoom: 8}});
  requestAnimationFrame(() => document.getElementById(`location-${{slug}}`)?.scrollIntoView({{block: 'nearest', behavior: 'smooth'}}));
}}
async function expandCluster(event) {{
  const feature = event.features?.[0];
  if (!feature) return;
  const zoom = await map.getSource('meetup-locations').getClusterExpansionZoom(feature.properties.cluster_id);
  map.easeTo({{center: feature.geometry.coordinates, zoom}});
}}
function addMeetupLayers() {{
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
    paint: {{'text-color': '#102326'}}
  }});
  map.addLayer({{
    id: 'meetup-points', type: 'circle', source: 'meetup-locations', filter: ['!', ['has', 'point_count']],
    paint: {{'circle-color': '{MAP_MARKER_COLOR}', 'circle-radius': ['case', ['get', 'selected'], 11, 7], 'circle-stroke-width': ['case', ['get', 'selected'], 3, 2], 'circle-stroke-color': '#fff'}}
  }});

  if (!initialViewSet) {{
    const bounds = new maplibregl.LngLatBounds();
    locations.forEach(location => bounds.extend([location.lon, location.lat]));
    map.fitBounds(bounds, {{padding: 24, maxZoom: 1.6, duration: 0}});
    initialViewSet = true;
    if (selectedSlug) {{
      const selected = locations.find(location => location.slug === selectedSlug);
      if (selected) map.flyTo({{center: [selected.lon, selected.lat], zoom: 8}});
    }}
  }}
  mapReady = true;
  renderLocations();
}}
map.on('style.load', addMeetupLayers);
map.on('click', event => {{
  const layers = ['meetup-clusters', 'meetup-cluster-count', 'meetup-points'].filter(layer => map.getLayer(layer));
  if (!layers.length) return;
  const feature = map.queryRenderedFeatures(event.point, {{layers}})[0];
  if (!feature) return;
  if (feature.layer.id === 'meetup-clusters' || feature.layer.id === 'meetup-cluster-count') {{
    expandCluster({{features: [feature]}});
    return;
  }}
  {{
    const location = feature.properties;
    selectLocation(location.slug, true);
    const popup = `<strong>${{esc(location.city)}}</strong><br>${{esc(location.country)}}`;
    new maplibregl.Popup({{offset: 12}}).setLngLat(feature.geometry.coordinates).setHTML(popup).addTo(map);
  }}
}});
map.on('mousemove', event => {{
  const layers = ['meetup-clusters', 'meetup-cluster-count', 'meetup-points'].filter(layer => map.getLayer(layer));
  if (!layers.length) return;
  map.getCanvas().style.cursor = map.queryRenderedFeatures(event.point, {{layers}}).length ? 'pointer' : '';
}});
colorScheme.addEventListener('change', event => {{
  const nextStyle = styleFor(event.matches);
  if (nextStyle !== activeStyle) {{
    activeStyle = nextStyle;
    map.setStyle(nextStyle, {{diff: false}});
  }}
}});
searchInput.addEventListener('input', renderLocations);
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
        help="HTML output path (default: docs/map.html)",
    )
    parser.add_argument("-v", action="store_true", help="show timestamped progress logs")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.v else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s" if args.v else "%(levelname)s: %(message)s",
        force=True,
    )
    sys.path.insert(0, str(ROOT))
    from tools.common.ansible_event_cities import CITIES

    locations = [
        {
            "slug": city.slug,
            "city": city.city,
            "country": city.country,
            "region": normalise_region(city.region),
            "timezone": city.timezone,
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
