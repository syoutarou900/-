# -*- coding: utf-8 -*-
"""Country / city master data for GlobalHours.

Each country entry:
  code     ISO 3166-1 alpha-2 (also the `holidays` library code)
  name     English display name
  lang     default proposal-template language (one of the 13 UI
           languages; falls back to "en")
  weekend  tuple of Python weekday numbers (Mon=0 .. Sun=6) that are
           non-working weekend days in that country
  cities   list of (city name, IANA timezone name)

The list covers the major business countries. All timezone maths is
done with zoneinfo + tzdata and all holiday lookups with the bundled
`holidays` data, so everything works fully offline.
"""

WEEKEND_SAT_SUN = (5, 6)
WEEKEND_FRI_SAT = (4, 5)

COUNTRIES = [
    # --- Asia-Pacific ---
    {"code": "JP", "name": "Japan", "lang": "ja", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Tokyo", "Asia/Tokyo"), ("Osaka", "Asia/Tokyo")]},
    {"code": "KR", "name": "South Korea", "lang": "ko", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Seoul", "Asia/Seoul")]},
    {"code": "CN", "name": "China", "lang": "zh", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Shanghai", "Asia/Shanghai"), ("Beijing", "Asia/Shanghai"),
                ("Shenzhen", "Asia/Shanghai")]},
    {"code": "HK", "name": "Hong Kong", "lang": "zh", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Hong Kong", "Asia/Hong_Kong")]},
    {"code": "TW", "name": "Taiwan", "lang": "zh", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Taipei", "Asia/Taipei")]},
    {"code": "SG", "name": "Singapore", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Singapore", "Asia/Singapore")]},
    {"code": "MY", "name": "Malaysia", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Kuala Lumpur", "Asia/Kuala_Lumpur")]},
    {"code": "ID", "name": "Indonesia", "lang": "id", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Jakarta", "Asia/Jakarta"), ("Denpasar (Bali)", "Asia/Makassar"),
                ("Surabaya", "Asia/Jakarta")]},
    {"code": "TH", "name": "Thailand", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Bangkok", "Asia/Bangkok")]},
    {"code": "VN", "name": "Vietnam", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Ho Chi Minh City", "Asia/Ho_Chi_Minh"), ("Hanoi", "Asia/Ho_Chi_Minh")]},
    {"code": "PH", "name": "Philippines", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Manila", "Asia/Manila")]},
    {"code": "IN", "name": "India", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Mumbai", "Asia/Kolkata"), ("Delhi", "Asia/Kolkata"),
                ("Bengaluru", "Asia/Kolkata")]},
    {"code": "PK", "name": "Pakistan", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Karachi", "Asia/Karachi")]},
    {"code": "BD", "name": "Bangladesh", "lang": "en", "weekend": WEEKEND_FRI_SAT,
     "cities": [("Dhaka", "Asia/Dhaka")]},
    {"code": "NP", "name": "Nepal", "lang": "en", "weekend": (5,),
     "cities": [("Kathmandu", "Asia/Kathmandu")]},
    {"code": "IR", "name": "Iran", "lang": "en", "weekend": (4,),
     "cities": [("Tehran", "Asia/Tehran")]},
    {"code": "AU", "name": "Australia", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Sydney", "Australia/Sydney"), ("Melbourne", "Australia/Melbourne"),
                ("Brisbane", "Australia/Brisbane"), ("Perth", "Australia/Perth"),
                ("Adelaide", "Australia/Adelaide")]},
    {"code": "NZ", "name": "New Zealand", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Auckland", "Pacific/Auckland"), ("Wellington", "Pacific/Auckland")]},
    # --- Europe ---
    {"code": "GB", "name": "United Kingdom", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("London", "Europe/London"), ("Edinburgh", "Europe/London")]},
    {"code": "IE", "name": "Ireland", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Dublin", "Europe/Dublin")]},
    {"code": "FR", "name": "France", "lang": "fr", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Paris", "Europe/Paris"), ("Lyon", "Europe/Paris")]},
    {"code": "DE", "name": "Germany", "lang": "de", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Berlin", "Europe/Berlin"), ("Munich", "Europe/Berlin"),
                ("Frankfurt", "Europe/Berlin"), ("Hamburg", "Europe/Berlin")]},
    {"code": "IT", "name": "Italy", "lang": "it", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Rome", "Europe/Rome"), ("Milan", "Europe/Rome")]},
    {"code": "ES", "name": "Spain", "lang": "es", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Madrid", "Europe/Madrid"), ("Barcelona", "Europe/Madrid")]},
    {"code": "PT", "name": "Portugal", "lang": "pt", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Lisbon", "Europe/Lisbon"), ("Porto", "Europe/Lisbon")]},
    {"code": "NL", "name": "Netherlands", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Amsterdam", "Europe/Amsterdam"), ("Rotterdam", "Europe/Amsterdam")]},
    {"code": "BE", "name": "Belgium", "lang": "fr", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Brussels", "Europe/Brussels")]},
    {"code": "CH", "name": "Switzerland", "lang": "de", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Zurich", "Europe/Zurich"), ("Geneva", "Europe/Zurich")]},
    {"code": "AT", "name": "Austria", "lang": "de", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Vienna", "Europe/Vienna")]},
    {"code": "PL", "name": "Poland", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Warsaw", "Europe/Warsaw"), ("Krakow", "Europe/Warsaw")]},
    {"code": "CZ", "name": "Czechia", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Prague", "Europe/Prague")]},
    {"code": "HU", "name": "Hungary", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Budapest", "Europe/Budapest")]},
    {"code": "SE", "name": "Sweden", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Stockholm", "Europe/Stockholm")]},
    {"code": "NO", "name": "Norway", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Oslo", "Europe/Oslo")]},
    {"code": "DK", "name": "Denmark", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Copenhagen", "Europe/Copenhagen")]},
    {"code": "FI", "name": "Finland", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Helsinki", "Europe/Helsinki")]},
    {"code": "GR", "name": "Greece", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Athens", "Europe/Athens")]},
    {"code": "TR", "name": "Turkiye", "lang": "tr", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Istanbul", "Europe/Istanbul"), ("Ankara", "Europe/Istanbul")]},
    {"code": "RU", "name": "Russia", "lang": "ru", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Moscow", "Europe/Moscow"), ("Yekaterinburg", "Asia/Yekaterinburg"),
                ("Novosibirsk", "Asia/Novosibirsk"), ("Vladivostok", "Asia/Vladivostok")]},
    {"code": "UA", "name": "Ukraine", "lang": "ru", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Kyiv", "Europe/Kyiv")]},
    # --- Middle East & Africa ---
    {"code": "IL", "name": "Israel", "lang": "en", "weekend": WEEKEND_FRI_SAT,
     "cities": [("Tel Aviv", "Asia/Jerusalem")]},
    {"code": "AE", "name": "United Arab Emirates", "lang": "ar", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Dubai", "Asia/Dubai"), ("Abu Dhabi", "Asia/Dubai")]},
    {"code": "SA", "name": "Saudi Arabia", "lang": "ar", "weekend": WEEKEND_FRI_SAT,
     "cities": [("Riyadh", "Asia/Riyadh")]},
    {"code": "EG", "name": "Egypt", "lang": "ar", "weekend": WEEKEND_FRI_SAT,
     "cities": [("Cairo", "Africa/Cairo")]},
    {"code": "ZA", "name": "South Africa", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Johannesburg", "Africa/Johannesburg"), ("Cape Town", "Africa/Johannesburg")]},
    {"code": "NG", "name": "Nigeria", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Lagos", "Africa/Lagos")]},
    {"code": "KE", "name": "Kenya", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Nairobi", "Africa/Nairobi")]},
    # --- Americas ---
    {"code": "US", "name": "United States", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("New York", "America/New_York"), ("Chicago", "America/Chicago"),
                ("Denver", "America/Denver"), ("Los Angeles", "America/Los_Angeles"),
                ("San Francisco", "America/Los_Angeles"), ("Seattle", "America/Los_Angeles"),
                ("Anchorage", "America/Anchorage"), ("Honolulu", "Pacific/Honolulu")]},
    {"code": "CA", "name": "Canada", "lang": "en", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Toronto", "America/Toronto"), ("Montreal", "America/Toronto"),
                ("Vancouver", "America/Vancouver"), ("Calgary", "America/Edmonton")]},
    {"code": "MX", "name": "Mexico", "lang": "es", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Mexico City", "America/Mexico_City"), ("Cancun", "America/Cancun"),
                ("Monterrey", "America/Monterrey")]},
    {"code": "BR", "name": "Brazil", "lang": "pt", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Sao Paulo", "America/Sao_Paulo"), ("Rio de Janeiro", "America/Sao_Paulo"),
                ("Manaus", "America/Manaus")]},
    {"code": "AR", "name": "Argentina", "lang": "es", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Buenos Aires", "America/Argentina/Buenos_Aires")]},
    {"code": "CL", "name": "Chile", "lang": "es", "weekend": WEEKEND_SAT_SUN,
     "cities": [("Santiago", "America/Santiago")]},
]

_BY_CODE = {c["code"]: c for c in COUNTRIES}


def country_by_code(code: str):
    return _BY_CODE.get(code)


def country_for_zone(zone_name: str):
    """Best-effort country lookup for an IANA zone (used for the
    user's own location defaults)."""
    for c in COUNTRIES:
        for _city, zone in c["cities"]:
            if zone == zone_name:
                return c
    return None
