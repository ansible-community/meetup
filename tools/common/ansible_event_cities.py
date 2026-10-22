"""Canonical locations used by Ansible meetup tooling.

Keep this registry grouped by source so current Meetup Pro locations can be
maintained independently from historic city locations.
"""

from __future__ import annotations

import dataclasses
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tools.common.ansible_events_lib import (
    CITY_SLUG_RE,
    EVENT_NAME_PREFIX,
    ORGANISERS_GROUP_PREFIX,
    ORGANISER_TEAM_PREFIX,
)

ATTENDEE_GROUP_PREFIX = "meetup-attendee"


@dataclasses.dataclass(frozen=True, slots=True)
class CityInfo:
    """A meetup city with its geographic and timezone metadata."""

    region: str
    country: str
    slug: str
    city: str
    timezone: str

    def __post_init__(self) -> None:
        """Validate the city slug, labels, and IANA timezone."""
        if not CITY_SLUG_RE.fullmatch(self.slug):
            raise ValueError(f"City slug must contain lowercase ASCII letters only: {self.slug!r}")
        if not self.city.strip() or not self.region.strip() or not self.country.strip():
            raise ValueError("City display name, region, and country must not be empty")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Invalid IANA timezone: {self.timezone!r}") from exc

    @property
    def field_value(self) -> str:
        """Format as 'region:country:city' for Discourse user fields."""
        return f"{self.region}:{self.country}:{self.city}"

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


# Current cities
# ==============
# Existing city groups from Meetup Pro (tmp/meetup-groups.csv), sorted by
# region, country, and city. The separate country-level group is below.
MEETUP_PRO_CITIES: tuple[CityInfo, ...] = (
    CityInfo("Americas", "Argentina", "buenosaires", "Buenos Aires", "America/Argentina/Buenos_Aires"),
    CityInfo("Americas", "Brazil", "saopaulo", "São Paulo", "America/Sao_Paulo"),
    CityInfo("Americas", "Canada", "montreal", "Montréal", "America/Toronto"),
    CityInfo("Americas", "Canada", "toronto", "Toronto", "America/Toronto"),
    CityInfo("Americas", "Colombia", "medellin", "Medellín", "America/Bogota"),
    CityInfo("Americas", "Mexico", "mexicocity", "Mexico City", "America/Mexico_City"),
    CityInfo("Americas", "USA", "atlanta", "Atlanta", "America/New_York"),
    CityInfo("Americas", "USA", "boston", "Boston", "America/New_York"),
    CityInfo("Americas", "USA", "denver", "Denver", "America/Denver"),
    CityInfo("Americas", "USA", "durham", "Durham", "America/New_York"),
    CityInfo("Americas", "USA", "mclean", "McLean", "America/New_York"),
    CityInfo("Americas", "USA", "minneapolis", "Minneapolis", "America/Chicago"),
    CityInfo("Americas", "USA", "omaha", "Omaha", "America/Chicago"),
    CityInfo("Americas", "USA", "saintlouis", "Saint Louis", "America/Chicago"),
    CityInfo("Americas", "USA", "sanfrancisco", "San Francisco", "America/Los_Angeles"),
    CityInfo("Asia Pacific", "Australia", "sydney", "Sydney", "Australia/Sydney"),
    CityInfo("Asia Pacific", "New Zealand", "auckland", "Auckland", "Pacific/Auckland"),
    CityInfo("Asia Pacific", "New Zealand", "wellington", "Wellington", "Pacific/Auckland"),
    CityInfo("Asia Pacific", "Singapore", "singapore", "Singapore", "Asia/Singapore"),
    CityInfo("Europe", "Czech Republic", "brno", "Brno", "Europe/Prague"),
    CityInfo("Europe", "Denmark", "copenhagen", "Copenhagen", "Europe/Copenhagen"),
    CityInfo("Europe", "Finland", "helsinki", "Helsinki", "Europe/Helsinki"),
    CityInfo("Europe", "France", "paris", "Paris", "Europe/Paris"),
    CityInfo("Europe", "Germany", "berlin", "Berlin", "Europe/Berlin"),
    CityInfo("Europe", "Germany", "hamburg", "Hamburg", "Europe/Berlin"),
    CityInfo("Europe", "Germany", "munchen", "München", "Europe/Berlin"),
    CityInfo("Europe", "Germany", "stuttgart", "Stuttgart", "Europe/Berlin"),
    CityInfo("Europe", "Ireland", "dublin", "Dublin", "Europe/Dublin"),
    CityInfo("Europe", "Italy", "roma", "Roma", "Europe/Rome"),
    CityInfo("Europe", "Netherlands", "amsterdam", "Amsterdam", "Europe/Amsterdam"),
    CityInfo("Europe", "Spain", "barcelona", "Barcelona", "Europe/Madrid"),
    CityInfo("Europe", "Spain", "madrid", "Madrid", "Europe/Madrid"),
    CityInfo("Europe", "Sweden", "stockholm", "Stockholm", "Europe/Stockholm"),
    CityInfo("Europe", "UK", "london", "London", "Europe/London"),
    CityInfo("Europe", "UK", "manchester", "Manchester", "Europe/London"),
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
    CityInfo("APAC", "Australia", "brisbane", "Brisbane", "Australia/Brisbane"),
    CityInfo("APAC", "Australia", "canberra", "Canberra", "Australia/Sydney"),
    CityInfo("APAC", "Australia", "melbourne", "Melbourne", "Australia/Melbourne"),
    CityInfo("APAC", "Australia", "perth", "Perth", "Australia/Perth"),
    CityInfo("APAC", "China", "beijing", "Beijing", "Asia/Shanghai"),
    CityInfo("APAC", "China", "hangzhou", "Hangzhou", "Asia/Shanghai"),
    CityInfo("APAC", "China", "shanghai", "Shanghai", "Asia/Shanghai"),
    CityInfo("APAC", "Hong Kong", "hongkong", "Hong Kong", "Asia/Hong_Kong"),
    CityInfo("APAC", "India", "ahmedabad", "Ahmedabad", "Asia/Kolkata"),
    CityInfo("APAC", "India", "aurangabad", "Aurangabad", "Asia/Kolkata"),
    CityInfo("APAC", "India", "bangalore", "Bangalore", "Asia/Kolkata"),
    CityInfo("APAC", "India", "belgaum", "Belgaum", "Asia/Kolkata"),
    CityInfo("APAC", "India", "chennai", "Chennai", "Asia/Kolkata"),
    CityInfo("APAC", "India", "delhi", "Delhi", "Asia/Kolkata"),
    CityInfo("APAC", "India", "hyderabad", "Hyderabad", "Asia/Kolkata"),
    CityInfo("APAC", "India", "jalandhar", "Jalandhar", "Asia/Kolkata"),
    CityInfo("APAC", "India", "kolkata", "Kolkata", "Asia/Kolkata"),
    CityInfo("APAC", "India", "mumbai", "Mumbai", "Asia/Kolkata"),
    CityInfo("APAC", "India", "pune", "Pune", "Asia/Kolkata"),
    CityInfo("APAC", "Indonesia", "jakarta", "Jakarta", "Asia/Jakarta"),
    CityInfo("APAC", "Japan", "tokyo", "Tokyo", "Asia/Tokyo"),
    CityInfo("APAC", "Saudi Arabia", "dhahran", "Dhahran", "Asia/Riyadh"),
    CityInfo("APAC", "South Korea", "seoul", "Seoul", "Asia/Seoul"),
    CityInfo("APAC", "Taiwan", "taipei", "Taipei", "Asia/Taipei"),
    CityInfo("APAC", "Thailand", "bangkok", "Bangkok", "Asia/Bangkok"),
    CityInfo("APAC", "Vietnam", "hanoi", "Hà Nội", "Asia/Ho_Chi_Minh"),
    CityInfo("EMEA", "Bulgaria", "sofia", "Sofia", "Europe/Sofia"),
    CityInfo("EMEA", "Czech Republic", "prague", "Prague", "Europe/Prague"),
    CityInfo("EMEA", "France", "bordeaux", "Bordeaux", "Europe/Paris"),
    CityInfo("EMEA", "France", "lyon", "Lyon", "Europe/Paris"),
    CityInfo("EMEA", "France", "rennes", "Rennes", "Europe/Paris"),
    CityInfo("EMEA", "Germany", "dresden", "Dresden", "Europe/Berlin"),
    CityInfo("EMEA", "Germany", "frankfurt", "Frankfurt", "Europe/Berlin"),
    CityInfo("EMEA", "Germany", "karlsruhe", "Karlsruhe", "Europe/Berlin"),
    CityInfo("EMEA", "Greece", "athens", "Athens", "Europe/Athens"),
    CityInfo("EMEA", "Greece", "crete", "Crete", "Europe/Athens"),
    CityInfo("EMEA", "Ireland", "cork", "Cork", "Europe/Dublin"),
    CityInfo("EMEA", "Ireland", "waterford", "Waterford", "Europe/Dublin"),
    CityInfo("EMEA", "Israel", "telaviv", "Tel Aviv", "Asia/Jerusalem"),
    CityInfo("EMEA", "Italy", "catania", "Catania", "Europe/Rome"),
    CityInfo("EMEA", "Italy", "milan", "Milan", "Europe/Rome"),
    CityInfo("EMEA", "Italy", "pisa", "Pisa", "Europe/Rome"),
    CityInfo("EMEA", "Italy", "reggioemilia", "Reggio Emilia", "Europe/Rome"),
    CityInfo("EMEA", "Kenya", "nairobi", "Nairobi", "Africa/Nairobi"),
    CityInfo("EMEA", "Latvia", "riga", "Riga", "Europe/Riga"),
    CityInfo("EMEA", "Lebanon", "beirut", "Beirut", "Asia/Beirut"),
    CityInfo("EMEA", "Poland", "krakow", "Kraków", "Europe/Warsaw"),
    CityInfo("EMEA", "Poland", "szczecin", "Szczecin", "Europe/Warsaw"),
    CityInfo("EMEA", "Poland", "torun", "Toruń", "Europe/Warsaw"),
    CityInfo("EMEA", "Poland", "warsaw", "Warsaw", "Europe/Warsaw"),
    CityInfo("EMEA", "Portugal", "lisbon", "Lisbon", "Europe/Lisbon"),
    CityInfo("EMEA", "Romania", "bucharest", "Bucharest", "Europe/Bucharest"),
    CityInfo("EMEA", "Russia", "moscow", "Moscow", "Europe/Moscow"),
    CityInfo("EMEA", "Russia", "saintpetersburg", "Saint Petersburg", "Europe/Moscow"),
    CityInfo("EMEA", "South Africa", "johannesburg", "Johannesburg", "Africa/Johannesburg"),
    CityInfo("EMEA", "Switzerland", "geneva", "Geneva", "Europe/Zurich"),
    CityInfo("EMEA", "Switzerland", "zurich", "Zürich", "Europe/Zurich"),
    CityInfo("EMEA", "UK", "edinburgh", "Edinburgh", "Europe/London"),
    CityInfo("EMEA", "UK", "leeds", "Leeds", "Europe/London"),
    CityInfo("EMEA", "UK", "oxford", "Oxford", "Europe/London"),
    CityInfo("LATAM", "Brazil", "brasilia", "Brasília", "America/Sao_Paulo"),
    CityInfo("LATAM", "Brazil", "riodejaneiro", "Rio de Janeiro", "America/Sao_Paulo"),
    CityInfo("LATAM", "Colombia", "barranquilla", "Barranquilla", "America/Bogota"),
    CityInfo("LATAM", "Colombia", "bogota", "Bogotá", "America/Bogota"),
    CityInfo("LATAM", "Peru", "lima", "Lima", "America/Lima"),
    CityInfo("NA", "Canada", "quebeccity", "Quebec City", "America/Toronto"),
    CityInfo("NA", "Canada", "vancouver", "Vancouver", "America/Vancouver"),
    CityInfo("NA", "Mexico", "guadalajara", "Guadalajara", "America/Mexico_City"),
    CityInfo("NA", "USA", "austin", "Austin", "America/Chicago"),
    CityInfo("NA", "USA", "baltimore", "Baltimore", "America/New_York"),
    CityInfo("NA", "USA", "boise", "Boise", "America/Boise"),
    CityInfo("NA", "USA", "boulder", "Boulder", "America/Denver"),
    CityInfo("NA", "USA", "champaign", "Champaign", "America/Chicago"),
    CityInfo("NA", "USA", "charlotte", "Charlotte", "America/New_York"),
    CityInfo("NA", "USA", "chicago", "Chicago", "America/Chicago"),
    CityInfo("NA", "USA", "cincinnati", "Cincinnati", "America/New_York"),
    CityInfo("NA", "USA", "cleveland", "Cleveland", "America/New_York"),
    CityInfo("NA", "USA", "dallas", "Dallas", "America/Chicago"),
    CityInfo("NA", "USA", "detroit", "Detroit", "America/Detroit"),
    CityInfo("NA", "USA", "fortworth", "Fort Worth", "America/Chicago"),
    CityInfo("NA", "USA", "honolulu", "Honolulu", "Pacific/Honolulu"),
    CityInfo("NA", "USA", "houston", "Houston", "America/Chicago"),
    CityInfo("NA", "USA", "indianapolis", "Indianapolis", "America/Indiana/Indianapolis"),
    CityInfo("NA", "USA", "kansascity", "Kansas City", "America/Chicago"),
    CityInfo("NA", "USA", "lasvegas", "Las Vegas", "America/Los_Angeles"),
    CityInfo("NA", "USA", "losangeles", "Los Angeles", "America/Los_Angeles"),
    CityInfo("NA", "USA", "melbournefl", "Melbourne, Florida", "America/New_York"),
    CityInfo("NA", "USA", "miami", "Miami", "America/New_York"),
    CityInfo("NA", "USA", "newyork", "New York", "America/New_York"),
    CityInfo("NA", "USA", "nova", "NOVA", "America/New_York"),
    CityInfo("NA", "USA", "philadelphia", "Philadelphia", "America/New_York"),
    CityInfo("NA", "USA", "phoenix", "Phoenix", "America/Phoenix"),
    CityInfo("NA", "USA", "pittsburgh", "Pittsburgh", "America/New_York"),
    CityInfo("NA", "USA", "portland", "Portland", "America/Los_Angeles"),
    CityInfo("NA", "USA", "richmond", "Richmond", "America/New_York"),
    CityInfo("NA", "USA", "saltlakecity", "Salt Lake City", "America/Denver"),
    CityInfo("NA", "USA", "sandiego", "San Diego", "America/Los_Angeles"),
    CityInfo("NA", "USA", "seattle", "Seattle", "America/Los_Angeles"),
    CityInfo("NA", "USA", "sfbay", "SF Bay", "America/Los_Angeles"),
    CityInfo("NA", "USA", "tampa", "Tampa", "America/New_York"),
    CityInfo("NA", "USA", "washingtondc", "Washington DC", "America/New_York"),
)

# Comments about typos and spelling
# =================================
# - Accepted local spellings/diacritics are used for Brasília, Hà Nội, Kraków,
#   Medellín, München, Montréal, São Paulo, Toruń, and Zürich. "Mexico City"
#   uses the accepted English spelling.

CITIES: tuple[CityInfo, ...] = MEETUP_PRO_CITIES + PREVIOUS_CITIES

if len({city.slug for city in CITIES}) != len(CITIES):
    raise ValueError("City slugs in CITIES must be unique")
if len({city.city.casefold() for city in CITIES}) != len(CITIES):
    raise ValueError("City display names in CITIES must be unique")
