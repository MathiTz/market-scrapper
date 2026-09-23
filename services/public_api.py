"""Serve ``market.db`` in the shape the Mercado em Dia UI expects (``GET /api/public``).

The contract is described in ``mercado-em-dia-ui/INTEGRACAO.md``. Prices are
integer cents, offers reference products by id, and flyers carry validity dates.

Our database is thinner than that contract, so some fields are derived:

* package size, pack count, category and subcategory come from the product *name*
  (``"Cerveja Amstel Lata 269ML"`` -> 269 ml, ``"... 12 Unidades"`` -> pack of 12;
  ``"Hidratante ..."`` -> category "Higiene e beleza", subcategory "Hidratante" - see :func:`subcategorize`);
* flyer validity comes from the flyer description ("Ofertas válidas de 20 a 22/09");
* offers are the latest price per product and store, from the store's latest complete scrape run only
  (what a store stopped listing disappears; a failed or partial run is set aside), all on the ``catalog`` channel;
  a member-only price (deal label with "Clube") becomes two offers: the regular price for
  everyone and the club price with ``conditions.club`` set;
* the same product sold by different chains is matched by name (see :func:`match_products`);
* stores share a chain name: the lowest store id is the retailer (the seed script
  was run several times, so ``stores`` holds duplicates);
* brand, GTIN and photo come from whichever source actually gives them for free (currently only the
  VTEX-backed scrapers - see :func:`_first_of`); most chains give none of these, so they stay blank.
"""

import logging
import re
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from config import SCRAPE_INTERVAL_HOURS
from models.price import Price
from models.product import Product
from models.scrape_attempt import ScrapeAttempt
from models.store import Store
from models.store_location import StoreLocation

logger = logging.getLogger(__name__)

FORTALEZA = timezone(timedelta(hours=-3))
CITY = "Fortaleza"
TTL_HOURS = SCRAPE_INTERVAL_HOURS * 3  # an offer is stale after missing ~3 scheduled scrapes
FLYER_CACHE_SECONDS = 30 * 60

_SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l)\b")
_PACK_RE = re.compile(r"(\d+)\s*(?:unidades?|unid\.?|un\.?)\b")
# Fresh meat and produce sold by weight ("Maminha Bovina Fribal Bandeja Kg", "Batata Doce Quilo") name no
# fixed pack size because there isn't one - the cut or bunch weighs whatever it weighs, and the price the
# scraper captured already *is* the per-kilo price. Without this, parse_size falls through to its (1, "un")
# default, which makes the product look like a single indivisible unit and hides the one figure ("R$/kg")
# that would let it be compared with a same-cut competitor sold in a fixed-weight tray.
_BARE_KG_RE = re.compile(r"\bkg\b|\bquilo\b")
_CLUB_RE = re.compile(r"(\w*clube\w*)", re.IGNORECASE)  # "PinClube", "Clube Tem Mais"
_VALIDITY_RE = re.compile(r"(\d{1,2})(?:/(\d{1,2}))?\s*a\s*(\d{1,2})/(\d{1,2})")

# The product's type word decides (see ``categorize``); within one word, the first group wins, so
# more specific groups come first ("agua sanitaria" before "agua").
_CATEGORIES: List[Tuple[str, Tuple[str, ...]]] = [
    ("Limpeza", ("sabao", "detergente", "lava", "desinfetante", "amaciante", "agua sanitaria",
                 "limpador", "esponja", "lixo", "multiuso", "alvejante", "inseticida", "desodorizador",
                 "tira manchas", "manchas", "limpa", "guardanapo", "saco", "vassoura", "rodo", "pano")),
    ("Higiene e beleza", ("shampoo", "condicionador", "sabonete", "creme dental", "escova dental",
                          "papel higienico", "desodorante", "absorvente", "fralda", "hidratante",
                          "creme de tratamento", "espuma de barbear", "lenco umedecido", "enxaguante",
                          "listerine", "hastes", "algodao", "fio dental", "mascara", "escova", "gel de banho",
                          "barbeador", "cotonete", "protetor solar", "perfume")),
    ("Bebidas", ("cerveja", "refrigerante", "suco", "agua", "vinho", "espumante", "whisky", "vodka",
                 "energetico", "guarana", "cha", "isotonico", "licor", "gin", "cachaca", "tequila",
                 "vermute", "rum", "champagne", "nectar", "bebida")),
    ("Carnes e peixes", ("carne", "frango", "peito", "file", "bife", "linguica", "bacon", "salmao",
                         "tilapia", "camarao", "hamburguer", "costela", "picanha", "coxa", "suino",
                         "bovino", "empanado", "salsicha", "mortadela", "filezinho", "almondega", "bisteca",
                         "lombo", "pernil", "alcatra", "patinho", "acem", "maminha", "fraldinha", "cupim",
                         "peixe", "bacalhau", "sobrecoxa", "calabresa")),
    ("Laticínios e frios", ("leite", "queijo", "iogurte", "requeijao", "manteiga", "margarina",
                            "creme de leite", "presunto", "mussarela", "nata", "bebida lactea",
                            "composto lacteo", "ovo", "ovos", "sorvete", "coalhada", "ricota", "peito de peru")),
    ("Hortifruti", ("banana", "laranja", "batata", "tomate", "cebola", "alface", "cenoura", "melancia",
                    "manga", "abacaxi", "uva", "maca", "limao", "abobora", "alho", "mamao", "melao", "pera",
                    "beterraba", "pimentao", "abacate", "ameixa", "chuchu", "goiaba", "kiwi", "maracuja",
                    "morango", "frutas", "mexerica", "tangerina", "repolho", "brocolis", "couve", "pepino")),
    ("Padaria e biscoitos", ("pao", "biscoito", "bolo", "torrada", "bolacha", "bisnaguinha", "brioche",
                            "bolinho", "croissant", "rosca", "cookie")),
    ("Mercearia", ("arroz", "feijao", "cafe", "acucar", "oleo", "azeite", "macarrao", "molho", "farinha",
                   "sal", "achocolatado", "cereal", "granola", "aveia", "maionese", "ketchup",
                   "chocolate", "bombom", "salgadinho", "tempero", "lasanha", "espaguete", "spaghetti",
                   "massa", "penne", "talharim", "nhoque", "lamen", "miojo", "pizza", "mel", "geleia",
                   "tapioca", "amendoim", "doce", "gelatina", "bala", "balas", "tortilha", "cappuccino",
                   "atum", "sardinha", "milho", "ervilha", "marshmallow", "pasta de amendoim", "ghee",
                   "vinagre", "mostarda", "sopa", "fermento", "leite condensado", "castanha")),
]


def clean(text: str) -> str:
    """Lower-case, accent-free, single-spaced (mirrors ``clean`` in the UI's lib/domain.ts)."""
    stripped = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def parse_size(name: str) -> Tuple[int, str, int]:
    """(amount, unit, pack_count) from a product name; unit is 'g', 'ml' or 'un'."""
    text = clean(name)
    pack = 1
    if pack_match := _PACK_RE.search(text):
        pack = min(int(pack_match.group(1)), 1000)
    if size_match := _SIZE_RE.search(text):
        value = float(size_match.group(1).replace(",", "."))
        unit = size_match.group(2)
        amount = round(value * (1000 if unit in ("kg", "l") else 1))
        if 0 < amount <= 1_000_000:
            return amount, {"kg": "g", "l": "ml"}.get(unit, unit), pack
    if _BARE_KG_RE.search(text):
        return 1000, "g", pack
    return 1, "un", pack


def _matches(word: str, keyword: str) -> bool:
    return word == keyword or (len(keyword) >= 5 and word.startswith(keyword))


def _category_match(text: str) -> Optional[Tuple[str, str]]:
    """(category, the specific keyword that decided it) for ``categorize()``'s own rules, or ``None`` for
    "Outros" - shared with :func:`subcategorize`, which needs not just the category but which of its
    keywords actually matched (see the note there on why "the" keyword is not always specific enough)."""
    # 1. a multi-word type at the start of the name ("papel higienico", "creme de leite")
    for category, keywords in _CATEGORIES:
        found = next((k for k in keywords if " " in k and text.strip().startswith(k)), None)
        if found:
            return category, found
    # 2. the first words, in the order they are written
    for word in re.findall(r"[a-z0-9]+", text)[:3]:  # "lava-loucas" -> lava, loucas
        for category, keywords in _CATEGORIES:
            found = next((k for k in keywords if " " not in k and _matches(word, k)), None)
            if found:
                return category, found
    # 3. any keyword anywhere
    words = re.findall(r"[a-z0-9]+", text)

    def has(keyword: str) -> bool:
        if " " in keyword:
            return keyword in text
        return any(_matches(w, keyword) for w in words)

    for category, keywords in _CATEGORIES:
        found = next((k for k in keywords if has(k)), None)
        if found:
            return category, found
    return None


def categorize(name: str) -> str:
    """The category of a product, deciding by its type word rather than by any keyword it contains.

    "Macarrão Instantâneo Nissin Lámen Picanha" is pasta, not meat, and "Molho de Tomate" is a sauce,
    not produce: the type is normally the first word, and the flavour or ingredient comes later.
    """
    text = re.sub(r"\bsabor\s+\w+", " ", clean(name))  # a flavour ("sabor picanha") says nothing about the type
    match = _category_match(text)
    return match[0] if match else "Outros"


# Keywords that name an ingredient or species rather than a specific kind of product - "bovina" alone
# tells you almost as little as "carne": a steak, a ground-beef roll and a sausage are all "bovina", so
# unlike the rest of a category's keywords these never become a *subcategory* on their own (see
# subcategorize). "Frango" is not excluded: unlike "bovina"/"carne"/"suino"/"peixe", a name that is just
# "Frango ..." with nothing more specific usually does mean the product itself is a whole/cut chicken, not
# a chicken-flavoured version of something else - the ambiguous cases ("Peito de Frango") already resolve
# to the more specific keyword ("peito") first, since that word comes before "frango" in the name.
_NOT_SUBCATEGORY = {
    "Carnes e peixes": frozenset({"carne", "bovino", "suino", "peixe"}),
    "Bebidas": frozenset({"bebida"}),
}


def subcategorize(name: str) -> str:
    """A finer type than :func:`categorize`'s ten broad buckets - "Sabonete", "Hidratante" and "Shampoo"
    instead of one shared "Higiene e beleza" - so the UI's "similar products" list can tell a body lotion
    from a diaper instead of only knowing both are somewhere in personal care. Reuses the exact keyword
    that already decided the category (the two can never disagree about what kind of product this is),
    promoted from a category-deciding vote to a label of its own. Empty when nothing specific matched, or
    when the only match was an ingredient/species word too generic to name a kind of product on its own
    (see _NOT_SUBCATEGORY) and no more specific keyword of the same category appears elsewhere in the name.
    """
    text = re.sub(r"\bsabor\s+\w+", " ", clean(name))
    match = _category_match(text)
    if not match:
        return ""
    category, keyword = match
    excluded = _NOT_SUBCATEGORY.get(category, frozenset())
    if keyword in excluded:
        words = re.findall(r"[a-z0-9]+", text)
        keywords = dict(_CATEGORIES).get(category, ())
        keyword = next(
            (k for k in keywords if k not in excluded and (
                (k in text) if " " in k else any(_matches(w, k) for w in words)
            )),
            None,
        )
        if not keyword:
            return ""
    return _keyword_label(keyword)


def _keyword_label(keyword: str) -> str:
    """A keyword as a label ("creme dental" -> "Creme Dental") - not :func:`display_name`, which only
    re-cases text that was originally ALL CAPS and leaves anything else alone, but every keyword here is
    already lower case by construction (matched against ``clean()``-normalised text). Connector words stay
    lower case past the first word, same convention as ``display_name``'s ``_SMALL_WORDS``. Accents are not
    restored (the keyword list itself is written accent-free, since matching is accent-insensitive), so a
    label like "Papel Higienico" is missing its circumflex - a cosmetic gap, not a matching one."""
    words = keyword.split(" ")
    return " ".join(w if i > 0 and w in _SMALL_WORDS else w.capitalize() for i, w in enumerate(words))


# Words kept in lower case and acronyms kept in upper case when an ALL-CAPS name is title-cased.
_SMALL_WORDS = {"de", "da", "do", "das", "dos", "e", "com", "sem", "para", "em", "ao", "aos", "a", "o",
                "no", "na", "por", "ou"}
_ACRONYMS = {"uht", "pet", "pvc", "led", "uv", "ph", "tv", "spf"}
_UNIT_TOKEN = re.compile(r"^(\d+(?:[.,]\d+)?)(kg|g|mg|l|ml|un|und|cm|m)$", re.IGNORECASE)
_PACK_TOKEN = re.compile(r"^\d+x\d+(?:[.,]\d+)?(?:kg|g|ml|l)?$", re.IGNORECASE)


def display_name(name: str) -> str:
    """A product name as shown: single-spaced, ALL CAPS title-cased, and units in lower case (600G -> 600g)."""
    text = " ".join((name or "").split())
    letters = [c for c in text if c.isalpha()]
    shouting = bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.7
    tokens = []
    for index, token in enumerate(text.split(" ")):
        lower = token.lower()
        if _UNIT_TOKEN.match(token) or _PACK_TOKEN.match(token):
            tokens.append(lower)
        elif not shouting:
            tokens.append(token)
        elif lower in _ACRONYMS:
            tokens.append(lower.upper())
        elif index > 0 and lower in _SMALL_WORDS:
            tokens.append(lower)
        else:  # capitalize each run of letters, so "japonesa/cabotia" becomes "Japonesa/Cabotia"
            tokens.append(re.sub(r"[^\W\d_]+", lambda m: m.group().capitalize(), lower))
    return " ".join(tokens)


def parse_validity(description: str, today: Optional[date] = None) -> Tuple[Optional[str], Optional[str]]:
    """Flyer validity as ISO datetimes, from "válidas de 20 a 22/09" or "de 30/09 a 05/10"."""
    match = _VALIDITY_RE.search(clean(description))
    if not match:
        return None, None
    today = today or datetime.now(FORTALEZA).date()
    start_day, start_month = int(match.group(1)), match.group(2)
    end_day, end_month = int(match.group(3)), int(match.group(4))
    start_month = int(start_month) if start_month else end_month
    end_year = today.year
    start_year = end_year - 1 if start_month > end_month else end_year
    try:
        start = datetime(start_year, start_month, start_day, tzinfo=FORTALEZA)
        end = datetime(end_year, end_month, end_day, 23, 59, 59, tzinfo=FORTALEZA)
    except ValueError:
        return None, None
    return start.isoformat(), end.isoformat()


def _iso_utc(moment: Optional[datetime]) -> str:
    """Our timestamps are naive UTC (SQLite CURRENT_TIMESTAMP / utcnow)."""
    moment = moment or datetime.utcnow()
    return moment.replace(tzinfo=timezone.utc).isoformat()


_ORDINARY_CONDITIONS = {
    "club": None, "coupon": None, "min_quantity": 1,
    "limit_per_customer": None, "payment": None, "region_note": "",
}

_flyer_cache: Tuple[float, list] = (0.0, [])


def cometa_encartes() -> list:
    """Cometa's published flyers, cached; a network failure yields the last known list."""
    global _flyer_cache
    fetched_at, cached = _flyer_cache
    if time.monotonic() - fetched_at < FLYER_CACHE_SECONDS and fetched_at:
        return cached
    try:
        from scraper.sites.cometa import CometaScraper

        scraper = CometaScraper()
        scraper.max_retries, scraper.timeout = 1, 5  # a page request must not hang on a slow site
        cached = scraper.fetch_encartes()
    except Exception as exc:
        logger.warning("Could not fetch Cometa flyers: %s", exc)
    _flyer_cache = (time.monotonic(), cached)
    return cached


def _site_keys() -> Dict[str, str]:
    from scraper.sites import ALL_SCRAPERS

    return {cls.site_name: cls.site_key for cls in ALL_SCRAPERS}


# What a store lists changes from one scrape to the next: new products appear, others stop being sold.
# So a store's list is what its latest *complete* run found, and anything older that is not in it is gone.
# A run that failed, found nothing, or found far fewer items than usual is set aside instead, so a broken
# or partial run can never wipe what is shown: the previous list stays until a good run replaces it.
MIN_SHARE_OF_USUAL = 0.25
BASELINE_RUNS = 6


def _listed_run(attempts: list) -> Optional[str]:
    """The run id of a site's newest complete-looking run. ``attempts`` are that site's, newest first."""
    for index, attempt in enumerate(attempts):
        if not attempt.run_id or not attempt.success or attempt.items_found <= 0:
            continue
        older = attempts[index + 1:index + 1 + BASELINE_RUNS]
        usual = max((a.items_found for a in older if a.success), default=0)
        if attempt.items_found < MIN_SHARE_OF_USUAL * usual:
            continue
        return attempt.run_id
    return None


def _listed_runs(db: Session, site_keys: Dict[str, str]) -> Dict[str, str]:
    """Per store name, the run whose prices make up its current list (absent when there is no tagged run)."""
    runs: Dict[str, str] = {}
    for name, key in site_keys.items():
        attempts = (db.query(ScrapeAttempt).filter(ScrapeAttempt.site_key == key)
                    .order_by(ScrapeAttempt.id.desc()).limit(BASELINE_RUNS + 24).all())
        run = _listed_run(attempts)
        if run:
            runs[name] = run
    return runs


def _last_errors(db: Session, site_keys: Dict[str, str],
                 runs: Optional[Dict[str, str]] = None) -> Dict[str, Optional[str]]:
    """Per store name: the problem with its latest scrape, or None if it looked fine."""
    errors: Dict[str, Optional[str]] = {}
    for name, key in site_keys.items():
        attempt = (db.query(ScrapeAttempt).filter(ScrapeAttempt.site_key == key)
                   .order_by(ScrapeAttempt.id.desc()).first())
        if attempt is None:
            errors[name] = None
        elif not attempt.success:
            errors[name] = attempt.error or "A última coleta falhou."
        elif attempt.items_found == 0:
            errors[name] = "A última coleta não encontrou itens."
        elif runs and attempt.run_id and name in runs and runs[name] != attempt.run_id:
            errors[name] = "A última coleta trouxe poucos itens; mostrando a anterior."
        else:
            errors[name] = None
    return errors


# Words that describe the package or the promotion, not the product.
_NOT_IDENTITY = {
    "de", "da", "do", "das", "dos", "em", "e", "com", "sem", "para", "o", "a", "ao", "por", "tipo",
    "lata", "caixa", "pacote", "pct", "frasco", "garrafa", "pote", "sache", "tp", "unidade", "unidades",
    "un", "embalagem", "pack", "bandeja", "saco", "refil", "tubo", "vidro", "long", "neck", "cada", "gratis",
}


def match_tokens(name: str) -> frozenset:
    """The words that identify a product once size, packaging and promo text are removed."""
    text = _PACK_RE.sub(" ", _SIZE_RE.sub(" ", clean(name)))
    text = re.sub(r"\d+\s*%", " ", text)
    return frozenset(w for w in re.findall(r"[a-z0-9]+", text) if w not in _NOT_IDENTITY)


def match_products(products: Iterable[Product]) -> Dict[int, List[Product]]:
    """Group products that are the same item sold by different chains.

    Precision over recall: a false match would show a wrong "cheapest", a missed
    one only hides a comparison. Two names match when their identifying words are
    identical and their sizes agree. A name without a size (flyer names are often
    cut short) joins a group only if the group has exactly one size, so it can
    never bridge two different sizes. Returns {lowest product id: members} for
    groups of two or more.
    """
    buckets: Dict[frozenset, List[Product]] = {}
    for product in products:
        tokens = match_tokens(product.name)
        if len(tokens) >= 2:  # a lone word ("Arroz") is too generic to identify anything
            buckets.setdefault(tokens, []).append(product)

    groups: Dict[int, List[Product]] = {}
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        by_size: Dict[tuple, List[Product]] = {}
        unsized: List[Product] = []
        for product in bucket:
            size = parse_size(product.name)
            if size[:2] == (1, "un"):
                unsized.append(product)
            else:
                by_size.setdefault(size, []).append(product)
        for product in unsized:
            pack = parse_size(product.name)[2]
            candidates = [size for size in by_size if size[2] == pack]
            key = candidates[0] if len(candidates) == 1 else (0, "?", pack)
            by_size.setdefault(key, []).append(product)
        for members in by_size.values():
            if len(members) > 1:
                groups[min(m.id for m in members)] = members
    return groups


def _display_product(members: List[Product]) -> Product:
    """The member whose name reads best: sized first, then not ALL CAPS, then most detailed."""
    return max(members, key=lambda m: (parse_size(m.name)[:2] != (1, "un"), not m.name.isupper(), len(m.name)))


def _first_of(members: List[Product], attr: str) -> Optional[str]:
    """The first non-empty value of `attr` among a matched group's members - a chain whose source gives a
    real brand/GTIN/photo (currently only the VTEX-backed ones) may not be the member `_display_product`
    picked for its name, so every member is checked rather than just the displayed one."""
    return next((value for m in members if (value := getattr(m, attr, None))), None)


def build_public(db: Session, q: str = "", network: str = "", channel: str = "",
                 category: str = "", product: str = "", encartes: Optional[list] = None) -> dict:
    """The payload for ``GET /api/public``; parameters filter as the UI's search does."""
    now = datetime.now(timezone.utc).isoformat()

    # One retailer per chain name: the lowest store id.
    canonical: Dict[str, Store] = {}
    for store in db.query(Store).order_by(Store.id).all():
        canonical.setdefault(store.name, store)
    retailer_of = {s.id: canonical[s.name] for s in db.query(Store).all()}  # any store id -> its retailer

    # Latest price per product and retailer, from the store's current list only (see _listed_runs).
    site_keys = _site_keys()
    runs = _listed_runs(db, site_keys)
    latest: Dict[Tuple[int, int], Price] = {}
    for price in db.query(Price).order_by(Price.id).all():
        retailer = retailer_of.get(price.store_id)
        if retailer is None:
            continue
        listed = runs.get(retailer.name)
        if listed is not None and price.run_id != listed:
            continue  # seen in an earlier run but not in the latest one: no longer on the store's list
        latest[(price.product_id, retailer.id)] = price

    products_by_id = {p.id: p for p in db.query(Product).all()}
    usable = {key: price for key, price in latest.items()
              if key[0] in products_by_id and price.price and price.price > 0}
    groups = match_products(products_by_id[pid] for pid in {pid for pid, _ in usable})
    rep_of = {m.id: rep for rep, members in groups.items() for m in members}

    # One offer per matched product and retailer: the most recent price.
    merged: Dict[Tuple[int, int], Price] = {}
    for (product_id, retailer_id), price in usable.items():
        key = (rep_of.get(product_id, product_id), retailer_id)
        if key not in merged or price.id > merged[key].id:
            merged[key] = price

    wanted = clean(q)
    offers: List[dict] = []
    products: Dict[int, dict] = {}
    for (rep, retailer_id), price in merged.items():
        members = groups.get(rep) or [products_by_id[rep]]
        if channel not in ("", "catalog") or (network and network != str(retailer_id)):
            continue
        if product and product not in {str(m.id) for m in members}:
            continue
        source = _display_product(members)
        amount, unit, pack = parse_size(source.name)
        cat = source.category or categorize(source.name)
        if category and category != cat:
            continue
        if wanted and not any(wanted in clean(f"{m.name} {amount} {unit}") for m in members):
            continue
        store = retailer_of[retailer_id]
        gtin = _first_of(members, "gtin")
        products.setdefault(rep, {
            "id": str(rep), "name": display_name(source.name), "brand": _first_of(members, "brand") or "",
            "category": cat, "subcategory": subcategorize(source.name),
            "variant": "", "amount": amount, "unit": unit, "pack_count": pack,
            "gtin": gtin, "gtin_evidence": "Código de barras (EAN) informado pela loja." if gtin else None,
            "image_url": _first_of(members, "image_url"), "image_source_url": None,
        })
        observed = _iso_utc(price.scraped_at)
        cents = round(price.price * 100)
        regular_cents = round(price.regular_price * 100) if price.regular_price else None
        # (offer id, price, conditions, regular price, deal label) for each price a shopper can get
        # Built from the product and the chain, not the price row: every scrape adds new rows, and a
        # shared link (?oferta=...) must keep finding its offer afterwards.
        offer_key = f"{rep}-{retailer_id}"
        variants = [(offer_key, cents, dict(_ORDINARY_CONDITIONS), regular_cents, price.offer or None)]
        club = _CLUB_RE.search(price.offer or "")
        if club and regular_cents:
            # A club price is not what everyone pays: also offer the regular price without conditions.
            variants = [
                (offer_key, regular_cents, dict(_ORDINARY_CONDITIONS), None, None),
                (f"{offer_key}-club", cents, {**_ORDINARY_CONDITIONS, "club": club.group(1)}, regular_cents, price.offer),
            ]
        elif club:
            variants[0][2]["club"] = club.group(1)
        for offer_id, offer_cents, conditions, offer_regular, label in variants:
            offers.append({
                "id": offer_id, "product_id": str(rep),
                "retailer_id": str(store.id), "retailer_name": store.name,
                "context_id": str(store.id), "context_label": f"{store.name} · {store.city or CITY}",
                "store_phone": None,
                "channel": "catalog", "price_cents": offer_cents, "currency": "BRL",
                "regular_price_cents": offer_regular, "deal_label": label,
                "conditions": conditions,
                "stock": price.stock, "availability": "available" if price.stock else "unknown",
                "price_observed_at": observed, "source_checked_at": observed,
                "valid_from": None, "valid_until": None, "collected_at": observed,
                "source_url": price.url or store.website or "", "method": "automatic",
                "published": 1, "ttl_hours": TTL_HOURS, "collection_error": None,
            })

    errors = _last_errors(db, site_keys, runs)
    flyers = _flyers(canonical, encartes if encartes is not None else cometa_encartes(), now)
    with_data = {o["retailer_id"] for o in offers} | {f["retailer_id"] for f in flyers}
    retailers = [
        {"id": str(s.id), "name": s.name, "official_url": s.website or "",
         "audit_status": "Coleta automática", "enabled": 1, "last_error": errors.get(s.name)}
        for s in canonical.values() if str(s.id) in with_data
    ]
    stores_per_product: Dict[str, set] = {}
    for o in offers:
        stores_per_product.setdefault(o["product_id"], set()).add(o["retailer_id"])

    return {
        "products": sorted(products.values(), key=lambda p: clean(p["name"])),
        "offers": offers,
        "flyers": flyers,
        "retailers": retailers,
        "retailer_locations": _retailer_locations(db, canonical),
        "regions": [CITY],
        "categories": sorted({c for c, _ in _CATEGORIES} | {"Outros"}),
        "coverage": {
            "networks": len(retailers),
            "products": len(products),
            "offers": len(offers),
            "exact_pairs": sum(1 for s in stores_per_product.values() if len(s) > 1),
        },
        "generated_at": now,
    }


def _retailer_locations(db: Session, canonical: Dict[str, Store]) -> List[dict]:
    """Each canonical retailer's real, physical branches (see models/store_location.py and
    services/store_locations.py). A chain we have not found real branch data for yet has none here - the
    UI treats that as "location unknown", not as a guess (see the note on Store.address in models/store.py)."""
    ids = {s.id for s in canonical.values()}
    if not ids:
        return []
    rows = db.query(StoreLocation).filter(StoreLocation.store_id.in_(ids)).order_by(StoreLocation.id).all()
    return [
        {"id": str(row.id), "retailer_id": str(row.store_id), "name": row.name,
         "address": row.address, "latitude": row.lat, "longitude": row.lon}
        for row in rows
    ]


def _flyers(canonical: Dict[str, Store], encartes: list, now: str) -> List[dict]:
    cometa = canonical.get("Cometa")
    if cometa is None:
        return []
    flyers = []
    for e in encartes:
        valid_from, valid_until = parse_validity(e.description)
        title = e.name.title() if e.name.isupper() else e.name
        flyers.append({
            "id": f"cometa-{e.id}", "retailer_id": str(cometa.id), "retailer_name": cometa.name,
            "title": title, "source_url": "https://cometasupermercados.com.br/encartes",
            "media_url": e.cover_url, "media_type": "image", "media_pages": [e.cover_url],
            "valid_from": valid_from, "valid_until": valid_until, "scope": e.description,
            "version_hash": str(e.id), "collected_at": now, "source_checked_at": now,
            "method": "automatic", "status": "published", "published": 1,
        })
    return flyers
