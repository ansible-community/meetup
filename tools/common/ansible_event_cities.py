"""Canonical locations used by Ansible meetup tooling.

Keep this registry grouped by source so current Meetup Pro locations can be
maintained independently from historic city locations.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tools.common.ansible_events_lib import (
    CITY_SLUG_RE,
    EVENT_NAME_PREFIX,
    ORGANISERS_GROUP_PREFIX,
    ORGANISER_TEAM_PREFIX,
)

ATTENDEE_GROUP_PREFIX = "meetup-attendee"
LATITUDE_RANGE = (-90.0, 90.0)
LONGITUDE_RANGE = (-180.0, 180.0)


def _validate_coordinate(value: float | None, name: str, city: str, bounds: tuple[float, float]) -> None:
    if value is not None and (not math.isfinite(value) or not bounds[0] <= value <= bounds[1]):
        raise ValueError(f"Invalid {name} for {city!r}: {value!r}")


@dataclasses.dataclass(frozen=True, slots=True)
class CityInfo:
    """A meetup city with its geographic and timezone metadata."""

    region: str
    country: str
    slug: str
    city: str
    timezone: str
    latitude: float | None = None
    longitude: float | None = None

    def __post_init__(self) -> None:
        """Validate the city slug, labels, and IANA timezone."""
        if not CITY_SLUG_RE.fullmatch(self.slug):
            raise ValueError(f"City slug must contain lowercase ASCII letters only: {self.slug!r}")
        if not self.city.strip() or not self.region.strip() or not self.country.strip():
            raise ValueError("City display name, region, and country must not be empty")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("City coordinates must include both latitude and longitude")
        _validate_coordinate(self.latitude, "latitude", self.city, LATITUDE_RANGE)
        _validate_coordinate(self.longitude, "longitude", self.city, LONGITUDE_RANGE)
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Invalid IANA timezone: {self.timezone!r}") from exc

    @property
    def event_name(self) -> str:
        """Return the canonical event name for this city."""
        return f"{EVENT_NAME_PREFIX} {self.city}"

    @property
    def team_name(self) -> str:
        """Return the canonical Pretix organiser team name for this city."""
        return f"{ORGANISER_TEAM_PREFIX} - {self.city}"

    @property
    def organiser_group(self) -> str:
        """Return the canonical Discourse organiser group name."""
        return f"{ORGANISERS_GROUP_PREFIX}-{self.slug}"

    @property
    def attendee_group(self) -> str:
        """Return the canonical Discourse attendee group name."""
        return f"{ATTENDEE_GROUP_PREFIX}-{self.slug}"


def sort_cities(cities: Iterable[CityInfo]) -> list[CityInfo]:
    """Return cities in stable alphabetical display-name order."""
    return sorted(cities, key=lambda city: city.city.casefold())


# Current cities
# ==============
# Existing city groups from Meetup Pro (tmp/meetup-groups.csv), sorted by
# region, country, and city. The separate country-level group is below.
MEETUP_PRO_CITIES: tuple[CityInfo, ...] = (
    CityInfo(
        "Americas", "Argentina", "buenosaires", "Buenos Aires", "America/Argentina/Buenos_Aires", -34.609558, -58.38879
    ),
    CityInfo("Americas", "Brazil", "saopaulo", "São Paulo", "America/Sao_Paulo", -23.550651, -46.633382),
    CityInfo("Americas", "Canada", "montreal", "Montréal", "America/Toronto", 45.503182, -73.569806),
    CityInfo("Americas", "Canada", "toronto", "Toronto", "America/Toronto", 43.653482, -79.383935),
    CityInfo("Americas", "Colombia", "medellin", "Medellín", "America/Bogota", 6.269732, -75.60256),
    CityInfo("Americas", "Mexico", "mexicocity", "Mexico City", "America/Mexico_City", 19.320772, -99.151468),
    CityInfo("Americas", "USA", "atlanta", "Atlanta", "America/New_York", 33.754466, -84.389815),
    CityInfo("Americas", "USA", "boston", "Boston", "America/New_York", 42.358834, -71.05783),
    CityInfo("Americas", "USA", "denver", "Denver", "America/Denver", 39.739236, -104.984862),
    CityInfo("Americas", "USA", "durham", "Durham", "America/New_York", 35.996653, -78.901805),
    CityInfo("Americas", "USA", "mclean", "McLean", "America/New_York", 38.936685, -77.185843),
    CityInfo("Americas", "USA", "minneapolis", "Minneapolis", "America/Chicago", 44.9773, -93.265469),
    CityInfo("Americas", "USA", "omaha", "Omaha", "America/Chicago", 41.258746, -95.938376),
    CityInfo("Americas", "USA", "saintlouis", "Saint Louis", "America/Chicago", 38.625406, -90.190009),
    CityInfo("Americas", "USA", "sanfrancisco", "San Francisco", "America/Los_Angeles", 37.787936, -122.40752),
    CityInfo("Asia Pacific", "Australia", "sydney", "Sydney", "Australia/Sydney", -33.869844, 151.208285),
    CityInfo("Asia Pacific", "New Zealand", "auckland", "Auckland", "Pacific/Auckland", -36.852095, 174.76318),
    CityInfo("Asia Pacific", "New Zealand", "wellington", "Wellington", "Pacific/Auckland", -41.288795, 174.777211),
    CityInfo("Asia Pacific", "Singapore", "singapore", "Singapore", "Asia/Singapore", 1.289918, 103.851907),
    CityInfo("Europe", "Czech Republic", "brno", "Brno", "Europe/Prague", 49.192244, 16.611338),
    CityInfo("Europe", "Denmark", "copenhagen", "Copenhagen", "Europe/Copenhagen", 55.686724, 12.570072),
    CityInfo("Europe", "Finland", "helsinki", "Helsinki", "Europe/Helsinki", 60.16662, 24.943541),
    CityInfo("Europe", "France", "paris", "Paris", "Europe/Paris", 48.85889, 2.320041),
    CityInfo("Europe", "Germany", "berlin", "Berlin", "Europe/Berlin", 52.517389, 13.395131),
    CityInfo("Europe", "Germany", "hamburg", "Hamburg", "Europe/Berlin", 53.550172, 10.001316),
    CityInfo("Europe", "Germany", "munchen", "München", "Europe/Berlin", 48.137108, 11.575382),
    CityInfo("Europe", "Germany", "stuttgart", "Stuttgart", "Europe/Berlin", 48.778449, 9.180013),
    CityInfo("Europe", "Ireland", "dublin", "Dublin", "Europe/Dublin", 53.349379, -6.260559),
    CityInfo("Europe", "Italy", "roma", "Roma", "Europe/Rome", 41.89332, 12.482932),
    # Ansible Benelux meets in Amsterdam and Nieuwegein; use Amsterdam as the
    # representative map point.
    CityInfo("Europe", "Netherlands", "benelux", "Ansible Benelux", "Europe/Amsterdam", 52.37308, 4.892453),
    CityInfo("Europe", "Spain", "barcelona", "Barcelona", "Europe/Madrid", 41.38258, 2.177073),
    CityInfo("Europe", "Spain", "madrid", "Madrid", "Europe/Madrid", 40.416782, -3.703507),
    CityInfo("Europe", "Sweden", "stockholm", "Stockholm", "Europe/Stockholm", 59.325117, 18.071093),
    CityInfo("Europe", "UK", "london", "London", "Europe/London", 51.507446, -0.127765),
    CityInfo("Europe", "UK", "manchester", "Manchester", "Europe/London", 53.442462, -2.232455),
)

# Country-level Meetup Pro groups from tmp/meetup-groups.csv. Keep these
# commented while city-level locations are available instead.
MEETUP_PRO_COUNTRY_GROUPS: tuple[str, ...] = (
    # "Ansible India",  # Use the city locations below instead.
    # "Ansible Ireland",  # Current CSV row is Dublin; use city locations instead.
)

# Previous cities
# ===============
# Historic meetup locations not represented by the current Meetup Pro city
# groups above. Sorted by source region, country, and canonical city name.
PREVIOUS_CITIES: tuple[CityInfo, ...] = (
    CityInfo("APAC", "Australia", "brisbane", "Brisbane", "Australia/Brisbane", -27.468962, 153.023501),
    CityInfo("APAC", "Australia", "canberra", "Canberra", "Australia/Sydney", -35.297591, 149.101268),
    CityInfo("APAC", "Australia", "melbourne", "Melbourne", "Australia/Melbourne", -37.814245, 144.963173),
    CityInfo("APAC", "Australia", "perth", "Perth", "Australia/Perth", -31.955897, 115.860578),
    CityInfo("APAC", "China", "beijing", "Beijing", "Asia/Shanghai", 39.905714, 116.391297),
    CityInfo("APAC", "China", "hangzhou", "Hangzhou", "Asia/Shanghai", 30.248963, 120.205234),
    CityInfo("APAC", "China", "shanghai", "Shanghai", "Asia/Shanghai", 31.231271, 121.470015),
    CityInfo("APAC", "Hong Kong", "hongkong", "Hong Kong", "Asia/Hong_Kong", 22.281833, 114.158283),
    CityInfo("APAC", "India", "ahmedabad", "Ahmedabad", "Asia/Kolkata", 23.021537, 72.580057),
    CityInfo("APAC", "India", "aurangabad", "Aurangabad", "Asia/Kolkata", 19.877263, 75.339024),
    CityInfo("APAC", "India", "bangalore", "Bangalore", "Asia/Kolkata", 12.976794, 77.590082),
    CityInfo("APAC", "India", "belgaum", "Belgaum", "Asia/Kolkata", 15.857267, 74.506934),
    CityInfo("APAC", "India", "chennai", "Chennai", "Asia/Kolkata", 13.080091, 80.280798),
    CityInfo("APAC", "India", "delhi", "Delhi", "Asia/Kolkata", 28.632803, 77.219771),
    CityInfo("APAC", "India", "hyderabad", "Hyderabad", "Asia/Kolkata", 17.360589, 78.474061),
    CityInfo("APAC", "India", "jalandhar", "Jalandhar", "Asia/Kolkata", 31.292231, 75.567888),
    CityInfo("APAC", "India", "kolkata", "Kolkata", "Asia/Kolkata", 22.572646, 88.363895),
    CityInfo("APAC", "India", "mumbai", "Mumbai", "Asia/Kolkata", 19.054999, 72.869203),
    CityInfo("APAC", "India", "pune", "Pune", "Asia/Kolkata", 18.521374, 73.854507),
    CityInfo("APAC", "Indonesia", "jakarta", "Jakarta", "Asia/Jakarta", -6.175405, 106.827168),
    CityInfo("APAC", "Japan", "tokyo", "Tokyo", "Asia/Tokyo", 35.67686, 139.763895),
    CityInfo("APAC", "Saudi Arabia", "dhahran", "Dhahran", "Asia/Riyadh", 26.296653, 50.120215),
    CityInfo("APAC", "South Korea", "seoul", "Seoul", "Asia/Seoul", 37.566679, 126.978291),
    CityInfo("APAC", "Taiwan", "taipei", "Taipei", "Asia/Taipei", 25.03752, 121.56368),
    CityInfo("APAC", "Thailand", "bangkok", "Bangkok", "Asia/Bangkok", 13.752494, 100.493509),
    CityInfo("APAC", "Vietnam", "hanoi", "Hà Nội", "Asia/Ho_Chi_Minh", 21.028333, 105.854041),
    CityInfo("EMEA", "Bulgaria", "sofia", "Sofia", "Europe/Sofia", 42.697703, 23.321736),
    CityInfo("EMEA", "Czech Republic", "prague", "Prague", "Europe/Prague", 50.087465, 14.421254),
    CityInfo("EMEA", "France", "bordeaux", "Bordeaux", "Europe/Paris", 44.841225, -0.580036),
    CityInfo("EMEA", "France", "lyon", "Lyon", "Europe/Paris", 45.757814, 4.832011),
    CityInfo("EMEA", "France", "rennes", "Rennes", "Europe/Paris", 48.111339, -1.68002),
    CityInfo("EMEA", "Germany", "dresden", "Dresden", "Europe/Berlin", 51.049329, 13.738144),
    CityInfo("EMEA", "Germany", "frankfurt", "Frankfurt", "Europe/Berlin", 50.110644, 8.682092),
    CityInfo("EMEA", "Germany", "karlsruhe", "Karlsruhe", "Europe/Berlin", 49.00687, 8.40342),
    CityInfo("EMEA", "Greece", "athens", "Athens", "Europe/Athens", 37.975565, 23.734832),
    CityInfo("EMEA", "Greece", "crete", "Crete", "Europe/Athens", 35.308495, 24.463342),
    CityInfo("EMEA", "Ireland", "cork", "Cork", "Europe/Dublin", 51.898514, -8.472642),
    CityInfo("EMEA", "Ireland", "waterford", "Waterford", "Europe/Dublin", 52.261, -7.111908),
    CityInfo("EMEA", "Israel", "telaviv", "Tel Aviv", "Asia/Jerusalem", 32.0853, 34.781806),
    CityInfo("EMEA", "Italy", "catania", "Catania", "Europe/Rome", 37.502361, 15.087372),
    CityInfo("EMEA", "Italy", "milan", "Milan", "Europe/Rome", 45.464194, 9.189635),
    CityInfo("EMEA", "Italy", "pisa", "Pisa", "Europe/Rome", 43.715939, 10.401862),
    CityInfo("EMEA", "Italy", "reggioemilia", "Reggio Emilia", "Europe/Rome", 44.608667, 10.594067),
    CityInfo("EMEA", "Kenya", "nairobi", "Nairobi", "Africa/Nairobi", -1.289001, 36.817281),
    CityInfo("EMEA", "Latvia", "riga", "Riga", "Europe/Riga", 56.949398, 24.105185),
    CityInfo("EMEA", "Lebanon", "beirut", "Beirut", "Asia/Beirut", 33.889226, 35.502558),
    CityInfo("EMEA", "Poland", "krakow", "Kraków", "Europe/Warsaw", 50.046943, 19.997153),
    CityInfo("EMEA", "Poland", "szczecin", "Szczecin", "Europe/Warsaw", 53.429811, 14.592868),
    CityInfo("EMEA", "Poland", "torun", "Toruń", "Europe/Warsaw", 53.010272, 18.604809),
    CityInfo("EMEA", "Poland", "warsaw", "Warsaw", "Europe/Warsaw", 52.233374, 21.071149),
    CityInfo("EMEA", "Portugal", "lisbon", "Lisbon", "Europe/Lisbon", 38.707751, -9.136592),
    CityInfo("EMEA", "Romania", "bucharest", "Bucharest", "Europe/Bucharest", 44.436141, 26.102684),
    CityInfo("EMEA", "Russia", "moscow", "Moscow", "Europe/Moscow", 55.625578, 37.606392),
    CityInfo("EMEA", "Russia", "saintpetersburg", "Saint Petersburg", "Europe/Moscow", 59.960674, 30.158655),
    CityInfo("EMEA", "South Africa", "johannesburg", "Johannesburg", "Africa/Johannesburg", -26.205, 28.049722),
    CityInfo("EMEA", "Switzerland", "geneva", "Geneva", "Europe/Zurich", 46.201756, 6.146601),
    CityInfo("EMEA", "Switzerland", "zurich", "Zürich", "Europe/Zurich", 47.374449, 8.541042),
    CityInfo("EMEA", "UK", "edinburgh", "Edinburgh", "Europe/London", 55.953346, -3.188375),
    CityInfo("EMEA", "UK", "leeds", "Leeds", "Europe/London", 53.797418, -1.543794),
    CityInfo("EMEA", "UK", "oxford", "Oxford", "Europe/London", 51.752013, -1.25785),
    CityInfo("LATAM", "Brazil", "brasilia", "Brasília", "America/Sao_Paulo", -15.793987, -47.8828),
    CityInfo("LATAM", "Brazil", "riodejaneiro", "Rio de Janeiro", "America/Sao_Paulo", -22.911014, -43.209373),
    CityInfo("LATAM", "Colombia", "barranquilla", "Barranquilla", "America/Bogota", 11.010192, -74.823179),
    CityInfo("LATAM", "Colombia", "bogota", "Bogotá", "America/Bogota", 4.653382, -74.083633),
    CityInfo("LATAM", "Peru", "lima", "Lima", "America/Lima", -12.045981, -77.030591),
    CityInfo("NA", "Canada", "quebeccity", "Quebec City", "America/Toronto", 46.813743, -71.208406),
    CityInfo("NA", "Canada", "vancouver", "Vancouver", "America/Vancouver", 49.260872, -123.113952),
    CityInfo("NA", "Mexico", "guadalajara", "Guadalajara", "America/Mexico_City", 20.678445, -103.335694),
    CityInfo("NA", "USA", "austin", "Austin", "America/Chicago", 30.264926, -97.747409),
    CityInfo("NA", "USA", "baltimore", "Baltimore", "America/New_York", 39.290882, -76.610759),
    CityInfo("NA", "USA", "boise", "Boise", "America/Boise", 43.616616, -116.200886),
    CityInfo("NA", "USA", "boulder", "Boulder", "America/Denver", 40.014986, -105.270545),
    CityInfo("NA", "USA", "champaign", "Champaign", "America/Chicago", 40.116484, -88.243093),
    CityInfo("NA", "USA", "charlotte", "Charlotte", "America/New_York", 35.227209, -80.843083),
    CityInfo("NA", "USA", "chicago", "Chicago", "America/Chicago", 41.875562, -87.624421),
    CityInfo("NA", "USA", "cincinnati", "Cincinnati", "America/New_York", 39.101281, -84.512741),
    CityInfo("NA", "USA", "cleveland", "Cleveland", "America/New_York", 41.499657, -81.693677),
    CityInfo("NA", "USA", "dallas", "Dallas", "America/Chicago", 32.776272, -96.796856),
    CityInfo("NA", "USA", "detroit", "Detroit", "America/Detroit", 42.331551, -83.04664),
    CityInfo("NA", "USA", "fortworth", "Fort Worth", "America/Chicago", 32.753177, -97.332746),
    CityInfo("NA", "USA", "honolulu", "Honolulu", "Pacific/Honolulu", 21.304547, -157.855676),
    CityInfo("NA", "USA", "houston", "Houston", "America/Chicago", 29.758938, -95.367697),
    CityInfo("NA", "USA", "indianapolis", "Indianapolis", "America/Indiana/Indianapolis", 39.768333, -86.15835),
    CityInfo("NA", "USA", "kansascity", "Kansas City", "America/Chicago", 39.100105, -94.578142),
    CityInfo("NA", "USA", "lasvegas", "Las Vegas", "America/Los_Angeles", 36.167426, -115.148413),
    CityInfo("NA", "USA", "losangeles", "Los Angeles", "America/Los_Angeles", 34.053692, -118.242768),
    CityInfo("NA", "USA", "melbournefl", "Melbourne, Florida", "America/New_York", 28.078503, -80.607791),
    CityInfo("NA", "USA", "miami", "Miami", "America/New_York", 25.774157, -80.193597),
    CityInfo("NA", "USA", "newyork", "New York", "America/New_York", 40.712728, -74.006015),
    # Regional group markers use the Fairfax County centroid for NOVA and the
    # San Francisco Bay Area centroid for SF Bay; neither label is one city.
    CityInfo("NA", "USA", "nova", "NOVA", "America/New_York", 38.815636, -77.283685),
    CityInfo("NA", "USA", "philadelphia", "Philadelphia", "America/New_York", 39.952724, -75.163526),
    CityInfo("NA", "USA", "phoenix", "Phoenix", "America/Phoenix", 33.448437, -112.074141),
    CityInfo("NA", "USA", "pittsburgh", "Pittsburgh", "America/New_York", 40.440697, -80.002567),
    CityInfo("NA", "USA", "portland", "Portland", "America/Los_Angeles", 45.520247, -122.674194),
    CityInfo("NA", "USA", "richmond", "Richmond", "America/New_York", 37.538509, -77.43428),
    CityInfo("NA", "USA", "saltlakecity", "Salt Lake City", "America/Denver", 40.75962, -111.886797),
    CityInfo("NA", "USA", "sandiego", "San Diego", "America/Los_Angeles", 32.715706, -117.163828),
    CityInfo("NA", "USA", "seattle", "Seattle", "America/Los_Angeles", 47.603832, -122.330062),
    CityInfo("NA", "USA", "sfbay", "SF Bay", "America/Los_Angeles", 37.788497, -122.355847),
    CityInfo("NA", "USA", "tampa", "Tampa", "America/New_York", 27.944985, -82.458311),
    CityInfo("NA", "USA", "washingtondc", "Washington DC", "America/New_York", 38.895098, -77.036385),
)

# Comments about typos and spelling
# =================================
# - Accepted local spellings/diacritics are used for Brasília, Hà Nội, Kraków,
#   Medellín, München, Montréal, São Paulo, Toruń, and Zürich. "Mexico City"
#   uses the accepted English spelling.

CITIES: tuple[CityInfo, ...] = MEETUP_PRO_CITIES + PREVIOUS_CITIES

if any(city.latitude is None or city.longitude is None for city in CITIES):
    raise ValueError("Every city in CITIES must have latitude and longitude coordinates")
if len({city.slug for city in CITIES}) != len(CITIES):
    raise ValueError("City slugs in CITIES must be unique")
if len({city.city.casefold() for city in CITIES}) != len(CITIES):
    raise ValueError("City display names in CITIES must be unique")
