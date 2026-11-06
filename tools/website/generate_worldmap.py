#!/usr/bin/env python3
"""Generate the public meetup map and upcoming events page."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/meetup-worldmap.html"
EVENTS_URL = "https://forum.ansible.com/c/events/8.json"
DISCOURSE_URL = "https://forum.ansible.com"
USER_AGENT = "AnsibleCommunityMeetupMap/1.0 (https://github.com/ansible-community/meetup)"
MAP_MARKER_COLOR = "#5BBCBF"
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


def attendance_format(event: dict[str, Any], raw: str, title: str, location: str) -> str:
    """Prefer explicit event attendance metadata, then use clear fallback signals."""
    jsonld: dict[str, Any] = {}
    match = re.search(r"<script\s+type=[\"']application/ld\+json[\"']\s*>(.*?)</script>", raw, re.I | re.S)
    if match:
        try:
            parsed = json.loads(match.group(1))
            jsonld = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass

    mode = str(event.get("eventAttendanceMode") or jsonld.get("eventAttendanceMode") or "").casefold()
    if "mixed" in mode or "hybrid" in mode:
        return "Hybrid"
    if "online" in mode:
        return "Online"
    if "offline" in mode or "inperson" in mode:
        return "In person"
    if event.get("livestream") or event.get("is_zoom_livestream"):
        return "Online"
    if re.search(r"online|virtual|remote|webinar|zoom|meet\.google", f"{title} {location}", re.I):
        return "Online"
    if location and not location.startswith(("http://", "https://")):
        return "In person"
    return "Format not specified"


def fetch_topic_event(topic: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Fetch the topic's first post, where Discourse serializes event details."""
    url = f"{DISCOURSE_URL}/t/{topic.get('slug', '')}/{topic.get('id', '')}.json"
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    posts = payload.get("post_stream", {}).get("posts", []) if isinstance(payload, dict) else []
    if not isinstance(posts, list):
        return {}, ""
    for post in posts:
        if isinstance(post, dict):
            event = post.get("event")
            if isinstance(event, dict):
                return event, str(post.get("raw", ""))
    return {}, ""


def fetch_events() -> list[dict[str, Any]]:
    """Fetch upcoming event summaries and details from the public Forum API."""
    response = requests.get(EVENTS_URL, headers={"User-Agent": USER_AGENT}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    topic_list = payload.get("topic_list") if isinstance(payload, dict) else None
    topics = topic_list.get("topics") if isinstance(topic_list, dict) else None
    if not isinstance(topics, list):
        raise ValueError("Discourse Events response is missing topic_list.topics")

    now = dt.datetime.now(dt.UTC)
    events: list[dict[str, Any]] = []
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        start = topic.get("event_starts_at")
        if not isinstance(start, str):
            continue
        try:
            starts_at = dt.datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            continue
        if starts_at.tzinfo is None:
            starts_at = starts_at.replace(tzinfo=dt.UTC)
        if starts_at < now:
            continue

        title = str(topic.get("title", "Community event"))
        try:
            event, raw = fetch_topic_event(topic)
        except (requests.RequestException, ValueError) as exc:
            LOGGER.warning("Could not load event details for %s: %s", title, exc)
            event, raw = {}, ""
        location_value = event.get("location")
        if isinstance(location_value, dict):
            location = str(location_value.get("name") or location_value.get("addressLocality") or "")
        else:
            location = str(location_value or "")
        recurrence = event.get("recurrence") or event.get("recurrence_rule")
        events.append(
            {
                "title": title,
                "url": f"{DISCOURSE_URL}/t/{topic.get('slug', '')}/{topic.get('id', '')}",
                "start": starts_at.isoformat(),
                "timezone": event.get("timezone") or topic.get("event_timezone") or "UTC",
                "location": location,
                "format": attendance_format(event, raw, title, location),
                "repeating": bool(recurrence),
            }
        )
    return sorted(events, key=lambda row: row["start"])


def render_page(locations: list[dict[str, Any]], events: list[dict[str, Any]], generated_at: str) -> str:
    """Render a self-contained page with an interactive OpenFreeMap map and event list."""
    payload = json.dumps({"locations": locations, "events": events, "generated_at": generated_at}, ensure_ascii=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    safe_json = payload
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ansible Meetup locations and events</title>
<link rel="icon" type="image/png" href="https://raw.githubusercontent.com/ansible/logos/refs/heads/main/community-marks/Ansible-Community-Mark-Pool.png">
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@^5/dist/maplibre-gl.css">
<style>
:root{{--red:#ee0000;--ink:#17202a;--muted:#56616d;--line:#d7dde2;--soft:#f4f6f8}}
*{{box-sizing:border-box}}body{{margin:0;color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;background:#fff}}
main{{max-width:1440px;margin:auto;padding:24px clamp(16px,3vw,40px) 48px}}h1{{font-size:clamp(1.8rem,3vw,2.7rem);line-height:1.15;margin:.3em 0}}h2{{font-size:1.55rem;margin:1.4em 0 .5em}}p{{color:var(--muted)}}a{{color:#a30000}}.intro{{max-width:850px}}.controls{{display:flex;gap:10px;flex-wrap:wrap;margin:20px 0}}input,select{{font:inherit;padding:10px 12px;border:1px solid #9aa4ae;border-radius:6px;background:white}}input{{min-width:230px;flex:1}}button,.subscribe{{font:inherit;display:inline-block;padding:9px 13px;border-radius:6px;border:1px solid #a30000;background:#fff;color:#8a0000;text-decoration:none;cursor:pointer}}button:hover,.subscribe:hover{{background:#fff2f2}}.layout{{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(300px,.85fr);gap:22px;align-items:start}}#map{{height:min(66vh,650px);min-height:390px;border:1px solid var(--line);border-radius:10px;z-index:0}}.map-note{{font-size:.85rem;margin:.4em 0}}.region{{border-top:1px solid var(--line);padding:8px 0}}.region summary{{font-weight:700;cursor:pointer;font-size:1.1rem}}.location-list{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0 18px;margin-top:6px}}.location{{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:2px 10px;padding:8px 4px;border:0;border-bottom:1px solid var(--line);border-radius:0;background:transparent}}.country{{margin:12px 0 4px;font-size:.94rem;color:var(--muted)}}.location h3{{font-size:.98rem;margin:0}}.location p{{grid-column:1;font-size:.86rem;margin:0}}.location .subscribe{{grid-column:2;grid-row:1/3;font-size:.82rem;padding:5px 8px;white-space:nowrap}}.pill{{display:inline-block;font-size:.76rem;background:#e8edf1;border-radius:99px;padding:2px 8px;margin:0 5px 5px 0;color:#263746}}.event-list{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}}.event{{border:1px solid var(--line);border-left:4px solid var(--red);padding:14px;border-radius:7px}}.event h3{{font-size:1rem;line-height:1.3;margin:0 0 8px}}.event p{{margin:5px 0;font-size:.91rem}}.subtle{{font-size:.86rem}}.empty{{padding:18px;background:var(--soft);border-radius:8px}}.marker-count{{font-weight:600}}
@media(max-width:850px){{.layout{{grid-template-columns:1fr}}#map{{height:55vh;min-height:350px}}}}
</style></head><body><main>
<p class="subtle">Ansible Community Meetups</p><h1>Find your local Ansible meetup</h1>
<p class="intro">Explore meetup communities around the world, browse locations by region, and find upcoming events. Select a map pin or location to see its community links. Set your <a href="https://forum.ansible.com/my/preferences/profile#user_event_cities">Forum event locations</a> to receive notices for places near you.</p>
<div class="controls"><input id="search" type="search" placeholder="Search city or country" aria-label="Search locations"><select id="region-filter" aria-label="Filter by region"><option value="">All regions</option></select><span id="location-count" class="marker-count" aria-live="polite"></span></div>
<section class="layout"><div><div id="map" role="application" aria-label="Interactive map of Ansible meetup locations"></div><p class="map-note"><span id="map-status" aria-live="polite"></span> Map style <a href="https://openfreemap.org/">OpenFreeMap</a> © <a href="https://openmaptiles.org/">OpenMapTiles</a>; data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>.</p></div><div><h2>Upcoming events</h2><div class="controls"><select id="event-filter" aria-label="Filter events"><option value="">All upcoming events</option><option value="In person">In person</option><option value="Online">Online</option><option value="Repeating">Repeating</option><option value="Hybrid">Hybrid</option></select></div><div id="events" class="event-list"></div><p class="subtle">Event information is refreshed when this page is generated. See the <a href="https://forum.ansible.com/c/events/8">Forum Events category</a> for the latest details and RSVP links.</p></div></section>
<h2>Meetup locations by region</h2><div id="regions"></div><p class="subtle">Location subscriptions are managed in your <a href="https://forum.ansible.com/my/preferences/profile#user_event_cities">Forum profile preferences</a>.</p>
<p class="subtle">Page data generated {html.escape(generated_at)}. Questions? Visit the <a href="https://forum.ansible.com/c/ansible-community/">Ansible Community Forum</a>.</p>
</main><script id="meetup-data" type="application/json">{safe_json}</script>
<script src="https://unpkg.com/maplibre-gl@^5/dist/maplibre-gl.js"></script>
<script>
const data=JSON.parse(document.getElementById('meetup-data').textContent);const locations=data.locations;const regions=[...new Set(locations.map(x=>x.region))].sort();
const map=new maplibregl.Map({{container:'map',style:'https://tiles.openfreemap.org/styles/liberty',center:[0,20],zoom:1.2}});map.addControl(new maplibregl.NavigationControl(), 'top-right');
const regionSelect=document.getElementById('region-filter');regions.forEach(r=>{{const o=document.createElement('option');o.value=r;o.textContent=r;regionSelect.append(o)}});
function esc(s){{return String(s).replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
function featureCollection(rows){{return{{type:'FeatureCollection',features:rows.map(x=>({{type:'Feature',geometry:{{type:'Point',coordinates:[x.lon,x.lat]}},properties:{{slug:x.slug,city:x.city,country:x.country,region:x.region,timezone:x.timezone}}}}))}}}}
function renderLocations(){{const q=document.getElementById('search').value.trim().toLowerCase(),r=regionSelect.value;const shown=locations.filter(x=>(!r||x.region===r)&&(!q||`${{x.city}} ${{x.country}}`.toLowerCase().includes(q)));document.getElementById('location-count').textContent=`${{shown.length}} of ${{locations.length}} locations`;const source=map.getSource('meetup-locations');if(source)source.setData(featureCollection(shown));document.getElementById('map-status').textContent=`${{shown.length}} locations shown. Click clusters to zoom, or a point for details.`;const host=document.getElementById('regions');host.replaceChildren();regions.filter(x=>!r||x===r).forEach(region=>{{const rows=shown.filter(x=>x.region===region);if(!rows.length)return;const details=document.createElement('details');details.className='region';details.open=Boolean(q||r);const summary=document.createElement('summary');summary.textContent=`${{region}} · ${{rows.length}} locations`;details.append(summary);[...new Set(rows.map(x=>x.country))].sort().forEach(country=>{{const countryRows=rows.filter(x=>x.country===country);const heading=document.createElement('h3');heading.className='country';heading.textContent=`${{country}} · ${{countryRows.length}}`;details.append(heading);const grid=document.createElement('div');grid.className='location-list';countryRows.sort((a,b)=>a.city.localeCompare(b.city)).forEach(x=>{{const card=document.createElement('article');card.className='location';card.innerHTML=`<h3>${{esc(x.city)}}</h3><p>${{esc(x.timezone)}}</p><a class="subscribe" href="https://forum.ansible.com/my/preferences/profile#user_event_cities">Get event notices</a>`;grid.append(card)}});details.append(grid)}});host.append(details)}})}}
map.on('load',()=>{{map.addSource('meetup-locations',{{type:'geojson',data:featureCollection(locations),cluster:true,clusterMaxZoom:5,clusterRadius:48}});map.addLayer({{id:'meetup-clusters',type:'circle',source:'meetup-locations',filter:['has','point_count'],paint:{{'circle-color':'{MAP_MARKER_COLOR}','circle-radius':['step',['get','point_count'],15,10,19,50,24],'circle-stroke-width':2,'circle-stroke-color':'#fff'}}}});map.addLayer({{id:'meetup-cluster-count',type:'symbol',source:'meetup-locations',filter:['has','point_count'],layout:{{'text-field':['get','point_count_abbreviated'],'text-size':12}},paint:{{'text-color':'#fff'}}}});map.addLayer({{id:'meetup-points',type:'circle',source:'meetup-locations',filter:['!', ['has','point_count']],paint:{{'circle-color':'{MAP_MARKER_COLOR}','circle-radius':7,'circle-stroke-width':2,'circle-stroke-color':'#fff'}}}});const bounds=new maplibregl.LngLatBounds();locations.forEach(x=>bounds.extend([x.lon,x.lat]));map.fitBounds(bounds,{{padding:24,maxZoom:1.6,duration:0}});map.on('click','meetup-clusters',event=>{{const feature=map.queryRenderedFeatures(event.point,{{layers:['meetup-clusters']}})[0],clusterId=feature.properties.cluster_id;map.getSource('meetup-locations').getClusterExpansionZoom(clusterId,(error,zoom)=>{{if(!error)map.easeTo({{center:feature.geometry.coordinates,zoom}})}})}});map.on('click','meetup-points',event=>{{const feature=event.features[0],x=feature.properties;new maplibregl.Popup({{offset:12}}).setLngLat(feature.geometry.coordinates).setHTML(`<strong>${{esc(x.city)}}</strong><br>${{esc(x.country)}}<br><span>${{esc(x.region)}}</span><br><a href="https://forum.ansible.com/my/preferences/profile#user_event_cities">Get event notices</a>`).addTo(map)}});map.on('mouseenter','meetup-clusters',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','meetup-clusters',()=>map.getCanvas().style.cursor='');map.on('mouseenter','meetup-points',()=>map.getCanvas().style.cursor='pointer');map.on('mouseleave','meetup-points',()=>map.getCanvas().style.cursor='');renderLocations()}});
function renderEvents(){{const filter=document.getElementById('event-filter').value;const shown=data.events.filter(e=>!filter||((filter==='Repeating')?e.repeating:(e.format===filter)));const host=document.getElementById('events');host.replaceChildren();if(!shown.length){{host.innerHTML='<div class="empty">No upcoming events found. Browse the <a href="https://forum.ansible.com/c/events/8">Forum Events category</a>.</div>';return}}shown.forEach(e=>{{const card=document.createElement('article');card.className='event';const date=new Date(e.start);card.innerHTML=`<h3><a href="${{esc(e.url)}}">${{esc(e.title)}}</a></h3><span class="pill">${{esc(e.format)}}</span>${{e.repeating?'<span class="pill">Repeating</span>':''}}<p>${{date.toLocaleString(undefined,{{dateStyle:'medium',timeStyle:'short',timeZone:e.timezone||undefined}})}} (${{esc(e.timezone||'UTC')}})</p>${{e.location?`<p>${{esc(e.location)}}</p>`:''}}`;host.append(card)}})}}
document.getElementById('search').addEventListener('input',renderLocations);regionSelect.addEventListener('change',renderLocations);document.getElementById('event-filter').addEventListener('change',renderEvents);renderLocations();renderEvents();
</script></body></html>"""


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
            "timezone": city.timezone,
            "lat": city.latitude,
            "lon": city.longitude,
        }
        for city in CITIES
    ]
    LOGGER.info("Loaded canonical coordinates for %s locations", len(locations))
    started_at = time.monotonic()
    try:
        LOGGER.info("Fetching upcoming events from %s", EVENTS_URL)
        events = fetch_events()
    except (requests.RequestException, ValueError, AttributeError) as exc:
        LOGGER.warning("Could not refresh Forum events: %s", exc)
        events = []
    generated_at = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_page(locations, events, generated_at), encoding="utf-8")
    LOGGER.info(
        "Generated %s (%s locations, %s upcoming events) in %.1f seconds",
        args.output,
        len(locations),
        len(events),
        time.monotonic() - started_at,
    )


if __name__ == "__main__":
    main()
