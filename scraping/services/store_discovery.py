"""Find supermarket chains in a region that the database does not have yet.

Reads the supermarkets and wholesalers OpenStreetMap lists for one or more cities (Overpass API), drops those
that match a chain we already scrape, groups the rest by fuzzy name and keeps the result in ``candidate_chains``
(models/candidate_chain.py), ranked by number of branches. It finds *where* a chain is, not its prices: each
candidate still needs its own scraper, and the list is for a person to review (OpenStreetMap is volunteer data).

    python -m services.store_discovery                           # Fortaleza, CE
    python -m services.store_discovery --state PE --city Recife   # another region
    python -m services.store_discovery --city Fortaleza Caucaia --include-convenience
    python -m services.store_discovery --dry-run                  # print, save nothing

To decide on a candidate: ``update candidate_chains set status = 'planned' where key = '...'`` (or ``ignored``).
"""

import argparse
import difflib
import logging
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import requests

from models import CandidateChain, SessionLocal, Store, init_db

logger = logging.getLogger(__name__)

OVERPASS_URLS = ("https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter")
USER_AGENT = "mercado-em-dia-store-discovery"
SIMILAR = 0.88  # how alike two names must be (difflib ratio) to count as the same chain

# Words that say what a place is, not which chain it is: "Super Lagoa" and "Supermercado Lagoa" are one chain.
_NOISE = re.compile(
    r"\b(supermercados?|supermercadinhos?|mercadinhos?|mercados?|mercadao|hipermercados?|super|atacadista|atacado|"
    r"loja|filial|unidade|express|ltda|eireli|sa|e|do|da|de|dos|das)\b"
)


@dataclass
class Place:
    name: str
    key: str
    city: str
    address: str
    lat: float
    lon: float


def key_of(name: str) -> str:
    """The part of a name that identifies the chain: no accents, case, noise words or branch suffix."""
    text = name.replace("–", "-").replace("—", "-")  # before the accents go, which would drop them
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\([^)]*\)", " ", text)  # "(José Walter)"
    text = re.sub(r"\s-\s.*$", "", text)  # " - Loja Centro"
    text = re.sub(r"['’`]", "", text)  # "Sam's" -> "sams"
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(_NOISE.sub(" ", text).split())


def same_chain(a: str, b: str) -> bool:
    """Equal keys, one being the other plus more words ("atacadao" / "atacadao lag"), or a near-typo."""
    if not a or not b:
        return False
    if a == b or a.startswith(b + " ") or b.startswith(a + " "):
        return True
    return min(len(a), len(b)) >= 5 and difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR


def overpass_query(state: str, cities: Sequence[str], include_convenience: bool) -> str:
    for city in cities:
        if not re.fullmatch(r"[\w '\-]+", city):
            raise ValueError(f"not a city name: {city!r}")
    if not re.fullmatch(r"[A-Z]{2}", state):
        raise ValueError(f"not a state code: {state!r}")
    shops = "supermarket|wholesale" + ("|convenience" if include_convenience else "")
    names = "|".join(cities)
    return (
        "[out:json][timeout:120];"
        f'area["ISO3166-2"="BR-{state}"]->.s;'
        f'area["boundary"="administrative"]["name"~"^({names})$"](area.s)->.a;'
        f'nwr["shop"~"^({shops})$"](area.a);'
        "out center tags;"
    )


def fetch_elements(query: str, urls: Sequence[str] = OVERPASS_URLS, tries: int = 2) -> List[dict]:
    """The query's elements. Overpass is shared and sometimes busy (429/504), so wait and try the next mirror."""
    last: Optional[Exception] = None
    for attempt in range(tries):
        for url in urls:
            try:
                response = requests.post(url, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=150)
                response.raise_for_status()
                return response.json()["elements"]
            except (requests.RequestException, ValueError, KeyError) as exc:
                last = exc
                logger.warning("Overpass %s failed: %s", url, exc)
        time.sleep(30 * (attempt + 1))
    raise RuntimeError(f"Overpass did not answer: {last}")


def to_places(elements: Iterable[dict], default_city: str = "") -> Tuple[List[Place], int]:
    """The named places with coordinates, and how many were left out for having no name."""
    places: List[Place] = []
    unnamed = 0
    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("brand") or tags.get("name") or tags.get("operator")
        point = element if "lat" in element else element.get("center", {})
        if not name or "lat" not in point:
            unnamed += 1
            continue
        key = key_of(name)
        if not key:
            unnamed += 1
            continue
        street = " ".join(filter(None, [tags.get("addr:street"), tags.get("addr:housenumber")]))
        address = ", ".join(filter(None, [street, tags.get("addr:suburb")]))
        places.append(Place(name, key, tags.get("addr:city") or default_city, address, point["lat"], point["lon"]))
    return places, unnamed


def known_keys(chain_names: Iterable[str]) -> List[str]:
    return [k for k in map(key_of, chain_names) if k]


def candidates(places: Iterable[Place], known: Sequence[str]) -> List[List[Place]]:
    """Places not belonging to a known chain, grouped into chains, the biggest first."""
    groups: Dict[str, List[Place]] = {}
    # most frequent keys first, so a rare variant ("super do povo patio arvoredo") joins the common one
    pending = [p for p in places if not any(same_chain(p.key, k) for k in known)]
    counts = Counter(p.key for p in pending)
    for place in sorted(pending, key=lambda p: (-counts[p.key], len(p.key))):
        head = next((h for h in groups if same_chain(place.key, h)), place.key)
        groups.setdefault(head, []).append(place)
    return sorted(groups.values(), key=lambda g: (-len(g), g[0].key))


def _spelling(group: List[Place]) -> str:
    return Counter(p.name for p in group).most_common(1)[0][0]


def save(groups: List[List[Place]], state: str, session, now: datetime) -> List[CandidateChain]:
    """Insert or update one row per group; returns the rows that are new in this run."""
    new: List[CandidateChain] = []
    for group in groups:
        key = Counter(p.key for p in group).most_common(1)[0][0]
        cities = ", ".join(sorted({p.city for p in group if p.city}))
        sample = group[0]
        row = session.query(CandidateChain).filter_by(key=key, state=state).one_or_none()
        if row is None:
            row = CandidateChain(key=key, state=state, status="new", first_seen=now)
            session.add(row)
            new.append(row)
        row.name, row.branches, row.cities = _spelling(group), len(group), cities
        row.example_address, row.lat, row.lon, row.last_seen = sample.address, sample.lat, sample.lon, now
    session.commit()
    return new


def run(state: str, cities: Sequence[str], include_convenience: bool = False, dry_run: bool = False,
        out=print) -> int:
    init_db()
    query = overpass_query(state, cities, include_convenience)
    elements = fetch_elements(query)
    places, unnamed = to_places(elements, cities[0] if len(cities) == 1 else "")
    with SessionLocal() as session:
        known = known_keys(s.name for s in session.query(Store))
        groups = candidates(places, known)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        new_keys = set()
        if not dry_run:
            new_keys = {row.key for row in save(groups, state, session, now)}
        ignored = {r.key for r in session.query(CandidateChain).filter_by(state=state, status="ignored")}
    matched = len(places) - sum(len(g) for g in groups)
    out(f"{len(elements)} places on the map in {', '.join(cities)}/{state}: {matched} belong to chains we have, "
        f"{unnamed} have no name, {sum(len(g) for g in groups)} are in {len(groups)} candidate chain(s).")
    out(f"{'branches':>8}  {'chain':<34} {'cities':<28} example")
    for group in groups:
        key = Counter(p.key for p in group).most_common(1)[0][0]
        if key in ignored:
            continue
        mark = " NEW" if key in new_keys else ""
        cities_text = ", ".join(sorted({p.city for p in group if p.city}))[:28]
        out(f"{len(group):>8}  {_spelling(group)[:34]:<34} {cities_text:<28} {group[0].address}{mark}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Find supermarket chains in a region that we do not have yet.")
    parser.add_argument("--state", default="CE", help="two-letter state code (default CE)")
    parser.add_argument("--city", nargs="+", default=["Fortaleza"], help="city names (default Fortaleza)")
    parser.add_argument("--include-convenience", action="store_true",
                        help="also list small shops tagged convenience (many more, noisier)")
    parser.add_argument("--dry-run", action="store_true", help="print the candidates, save nothing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    return run(args.state.upper(), args.city, args.include_convenience, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
