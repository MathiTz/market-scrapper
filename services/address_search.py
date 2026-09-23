"""Address search for the UI's "Perto de você" filter, backed by Photon (OpenStreetMap data).

The text a person types is sent to Photon, which the UI says before the search. Results are limited
to Fortaleza and cached, so repeating a search does not call the service again.
"""

import math
import re
import threading
import time
from collections import OrderedDict
from typing import List, Optional

import requests

PHOTON_URL = "https://photon.komoot.io/api/"
PHOTON_REVERSE_URL = "https://photon.komoot.io/reverse"
USER_AGENT = "mercado-em-dia/0.1 (price comparison for Fortaleza)"
CENTER = (-3.7319, -38.5267)  # latitude, longitude: results near it rank first
BBOX = (-38.65, -3.95, -38.35, -3.65)  # west, south, east, north: only Fortaleza and its surroundings
# geocode_address has no bbox (a chain's real branches are not all inside Fortaleza's), so a vague or
# ambiguous address ("Av. Nossa Sra. de Lurdes, 77 - Centro", no city) can rank a same-named street on
# the other side of the world over anything in Brazil; every chain we know of is in Ceará, so a candidate
# this far from its centre is a wrong match, not a distant real branch, and is discarded.
MAX_GEOCODE_KM = 600
MIN_QUERY, MAX_QUERY = 3, 120
LIMIT = 6
TIMEOUT_SECONDS = 8
CACHE_SECONDS = 24 * 60 * 60
CACHE_MAX_ENTRIES = 256

_cache: "OrderedDict[str, tuple[float, List[dict]]]" = OrderedDict()
_cache_lock = threading.Lock()


class AddressSearchError(Exception):
    """The address service could not be reached or answered badly."""


def normalize(query: str) -> str:
    return " ".join((query or "").split())


def _label(props: dict) -> str:
    street, number = props.get("street"), props.get("housenumber")
    parts = []
    if props.get("name") and props["name"] != street:
        parts.append(props["name"])
    if street:
        parts.append(f"{street}, {number}" if number else street)
    parts.append(props.get("district") or props.get("locality") or "")
    parts.append(props.get("city") or "")
    return " · ".join(dict.fromkeys(p for p in parts if p))[:240]


def _km_from_center(latitude: float, longitude: float) -> float:
    phi1, phi2 = math.radians(CENTER[0]), math.radians(latitude)
    dphi, dlambda = math.radians(latitude - CENTER[0]), math.radians(longitude - CENTER[1])
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(a))


def _place(feature: dict) -> Optional[dict]:
    props, geometry = feature.get("properties") or {}, feature.get("geometry") or {}
    coords = geometry.get("coordinates")
    if geometry.get("type") != "Point" or not coords or len(coords) < 2:
        return None
    label = _label(props)
    if not label or props.get("osm_id") is None:
        return None
    return {
        "id": f"{props.get('osm_type', '')}{props['osm_id']}",
        "label": label,
        "latitude": coords[1],
        "longitude": coords[0],
    }


def search_addresses(query: str) -> List[dict]:
    """Places matching ``query`` in Fortaleza, as ``{id, label, latitude, longitude}``."""
    query = normalize(query)
    key = query.casefold()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
    try:
        response = requests.get(
            PHOTON_URL,
            params={
                "q": query,
                "limit": LIMIT,
                "lat": CENTER[0],
                "lon": CENTER[1],
                "bbox": ",".join(str(v) for v in BBOX),
            },
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        features = response.json().get("features") or []
    except (requests.RequestException, ValueError) as exc:
        raise AddressSearchError(str(exc)) from exc
    places, seen = [], set()
    for feature in features:
        place = _place(feature)
        if place and place["label"] not in seen:
            seen.add(place["label"])
            places.append(place)
    with _cache_lock:
        _cache[key] = (time.monotonic(), places)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX_ENTRIES:
            _cache.popitem(last=False)
    return places


# A Brazilian commercial address's complement ("LOJA 01", "S/N", "KM 19", a shopping centre repeated as
# both the building and the neighbourhood) reads as noise to Photon's parser and can zero out an otherwise
# resolvable address; stripping it first resolved 4 of 5 branch addresses that failed on the raw text.
_COMPLEMENT_RE = re.compile(
    r"\b(loja[\s-]*[\w\d]*|s\s*/\s*n|km\s*\d+|bloco\s*[\w\d]*|sala\s*[\w\d]*)\b", re.IGNORECASE,
)


def _photon_search(query: str, bias: bool) -> List[dict]:
    params = {"q": query, "limit": 1}
    if bias:
        params.update(lat=CENTER[0], lon=CENTER[1])
    try:
        response = requests.get(
            PHOTON_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json().get("features") or []
    except (requests.RequestException, ValueError) as exc:
        raise AddressSearchError(str(exc)) from exc


def geocode_address(address: str) -> Optional[dict]:
    """The best match for a full, structured address (e.g. a chain's own branch address), or None.

    Unlike :func:`search_addresses`, this is not a person typing as they go: it is used once per real store
    branch (see ``services.store_locations``), so there is no Fortaleza-only bbox - a chain's branches are
    not all inside it (Mercadinho São Luiz has branches as far as Sobral and Juazeiro do Norte) - and no
    result-count cap; the single best-ranked match is what is wanted.

    Three attempts, each less specific than the last, so a resolvable address is not lost to one confusing
    detail: the address as given; with unit/complement noise like "LOJA 01" or "S/N" stripped; and, only if
    that still fails, its last two comma-separated segments (usually "city, state") as a last resort - a
    coarse but real point, rather than no location at all.
    """
    address = normalize(address)
    if not address:
        return None
    attempts = [address]
    cleaned = normalize(_COMPLEMENT_RE.sub(" ", address).replace(" ,", ","))
    if cleaned and cleaned.casefold() != address.casefold():
        attempts.append(cleaned)
    segments = [s.strip() for s in cleaned.split(",") if s.strip()]
    if len(segments) > 2:
        attempts.append(", ".join(segments[-2:]))
    for attempt in attempts:
        for feature in _photon_search(attempt, bias=(attempt is attempts[0])):
            place = _place(feature)
            if place and _km_from_center(place["latitude"], place["longitude"]) <= MAX_GEOCODE_KM:
                return place
    return None


def reverse_address(latitude: float, longitude: float) -> Optional[dict]:
    """The address at a coordinate (rounded to about 11 m before it leaves), or None when there is none."""
    try:
        response = requests.get(
            PHOTON_REVERSE_URL,
            params={"lat": f"{latitude:.4f}", "lon": f"{longitude:.4f}", "limit": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        features = response.json().get("features") or []
    except (requests.RequestException, ValueError) as exc:
        raise AddressSearchError(str(exc)) from exc
    for feature in features:
        found = _place(feature)
        if found:
            return found
    return None
