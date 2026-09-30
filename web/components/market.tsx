import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ShoppingBasket,
  Search,
  BookOpen,
  ClipboardList,
  MapPin,
  ArrowUpRight,
  ArrowLeft,
  Plus,
  Minus,
  Package,
  ShieldCheck,
  SlidersHorizontal,
  WifiOff,
  ChevronRight,
  X,
  Clock,
  TriangleAlert,
  Undo2,
} from "lucide-react";
import {
  BRAND,
  money,
  rankOffers,
  isConditional,
  conditionLabel,
  type Product,
  type Offer,
  type Flyer,
} from "@/lib/domain";
import { demoData } from "@/lib/demo";
import { FlyerBrowser, FlyerCard } from "@/components/flyers";
import { ProductCard, ProductHero } from "@/components/product-card";
import { ProductRangeCard } from "@/components/product-range-card";
import { groupBySize } from "@/lib/group";
import { OfferRail } from "@/components/offer-rail";
import { LoadMore, useIncremental } from "@/components/infinite";
import { ListAdder } from "@/components/list-adder";
import { StoreEstimates } from "@/components/store-estimates";
import { storeEstimates } from "@/lib/estimates";
import { buildIndex, filterIndexed } from "@/lib/search";
import { PriceInput } from "@/components/price-input";
import {
  alternativesOf,
  filterProducts,
  noFilters,
  productsWithPrice,
  sortLabels,
  type ProductFilters,
  type SortKey,
} from "@/lib/filters";
import { useDebounced } from "@/lib/use-debounced";
import { StoreContact } from "@/components/store-contact";
import { OfferRow } from "@/components/offer-row";
import { Sources } from "@/components/sources";
import { RetryButton, StatusPanel } from "@/components/status-panel";
import { organizeFlyers } from "@/lib/flyers";
import { NearbyFilter } from "@/components/nearby-filter";
import { Button, IconButton } from "@/components/ui/button";
import { Chip, ChipCheckbox } from "@/components/ui/chip";
import { CheckboxField } from "@/components/ui/checkbox";
import { SelectField } from "@/components/ui/select";
import { Tooltip, TooltipProvider } from "@/components/ui/tooltip";
import { FlyerGridSkeleton, GridSkeleton, RailSkeleton, Skeleton } from "@/components/ui/skeleton";
import { Notifications, notify } from "@/lib/notify";
import { markHero, withViewTransition } from "@/lib/view-transition";
import { useIndicator } from "@/components/ui/use-indicator";
import { Count } from "@/components/ui/number";
import { dailyDeals } from "@/lib/deals";
import { lowestPriceLabel, outOfComparison, priceSpread, suspiciousSpread } from "@/lib/comparison";
import { count, listName, packLabel, unitPriceText, whenLabel } from "@/lib/format";
import { loadErrorMessage, loadSnapshot } from "@/lib/snapshot";
import {
  MAX_QUANTITY,
  browserStorage,
  readList,
  storageMessage,
  writeList,
  type Line,
  type StorageIssue,
} from "@/lib/list-storage";
import {
  filterNearby,
  readNearby,
  groupLocations,
  type Nearby,
  type RetailerLocation,
} from "@/lib/location";
type Retailer = {
  id: string;
  name: string;
  official_url: string;
  audit_status: string;
  enabled: number;
  last_error: string | null;
};
type Data = {
  products: Product[];
  offers: Offer[];
  flyers: Flyer[];
  retailers: Retailer[];
  retailer_locations?: RetailerLocation[];
  regions: string[];
  categories: string[];
  coverage: {
    networks: number;
    products: number;
    offers: number;
    exact_pairs: number;
  };
  generated_at: string;
};
type View = "today" | "search" | "flyers" | "list";
const views: [View, string][] = [
  ["today", "Hoje"],
  ["search", "Buscar"],
  ["flyers", "Encartes"],
  ["list", "Minha lista"],
];
const discountLabels: Record<number, string> = {
  1: "Só com desconto",
  10: "Desconto de 10% ou mais",
  20: "Desconto de 20% ou mais",
  30: "Desconto de 30% ou mais",
  50: "Desconto de 50% ou mais",
};
/** "Só para membros…" inside a sentence: only the first letter changes, proper names keep theirs. */
const lowerFirst = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);
/** A product name short enough for a toast or a notice. */
const short = (name: string) => (name.length > 42 ? `${name.slice(0, 40).trimEnd()}…` : name);

export default function Market({ demo = false }: { demo?: boolean }) {
  const [view, setView] = useState<View>("today"),
    [query, setQuery] = useState(""),
    [pf, setPf] = useState<ProductFilters>(noFilters),
    // Until the person picks an order, a typed search is ordered by relevance and browsing by discount.
    [sortChosen, setSortChosen] = useState(false),
    [channel, setChannel] = useState(""),
    [category, setCategory] = useState(""),
    [conditions, setConditions] = useState(false),
    [old, setOld] = useState(false),
    [region, setRegion] = useState("Fortaleza"),
    [active, setActive] = useState<Product | null>(null),
    [lines, setLines] = useState<Line[]>([]),
    [loaded, setLoaded] = useState(false),
    [offline, setOffline] = useState(false),
    [filters, setFilters] = useState(false),
    // The toast stack sits above the mobile dock, whose height depends on the search bar being there.
    [narrow, setNarrow] = useState(false),
    [clock, setClock] = useState(0),
    [storageIssue, setStorageIssue] = useState<StorageIssue>(null),
    // The list as it was before the last removal, until something else changes it.
    [undo, setUndo] = useState<{ lines: Line[]; message: string } | null>(null),
    // Where to scroll back to, and which card to focus, once a product page closes.
    [restore, setRestore] = useState<{ scroll: number; productId: string } | null>(null);
  const networks = pf.networks;
  const [sharedTarget, setSharedTarget] = useState<{
    productId: string;
    offerId: string;
  } | null>(null);
  const [sharedNotice, setSharedNotice] = useState("");
  const [nearby, setNearby] = useState<Nearby | null>(null);
  const nearbyKey = "med-nearby-" + (demo ? "demo" : "real");
  const basePath = demo ? "/demo" : "/";
  const sharedOpened = useRef(false);
  const sharedScrolled = useRef(false);
  const returnTo = useRef<{ scroll: number; productId: string } | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const timer = setInterval(() => setClock((v) => v + 1), 60000);
    return () => clearInterval(timer);
  }, []);
  const listKey = "med-list-" + (demo ? "demo" : "real");
  useEffect(() => {
    // A saved list that cannot be read is copied aside before anything is written over it (lib/list-storage.ts).
    const saved = readList(browserStorage(), listKey);
    setLines(saved.lines);
    setStorageIssue(saved.issue);
    try {
      setRegion(localStorage.getItem("med-region") || "Fortaleza");
    } catch {}
    const params = new URLSearchParams(window.location.search);
    const productId = params.get("produto")?.slice(0, 200);
    if (productId) {
      setSharedTarget({
        productId,
        offerId: (params.get("oferta") || "").slice(0, 200),
      });
      setRegion(params.get("regiao")?.slice(0, 200) || BRAND.city);
      setView("search");
    } else {
      try {
        setNearby(readNearby(sessionStorage.getItem(nearbyKey)));
      } catch {}
    }
    setLoaded(true);
    let wasOffline = !navigator.onLine;
    const online = () => {
      const now = !navigator.onLine;
      if (wasOffline && !now) notify("Conexão de volta. Os preços voltam a aparecer.");
      wasOffline = now;
      setOffline(now);
    };
    online();
    window.addEventListener("online", online);
    window.addEventListener("offline", online);
    if (!demo && "serviceWorker" in navigator)
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    return () => {
      window.removeEventListener("online", online);
      window.removeEventListener("offline", online);
    };
  }, [listKey, nearbyKey, demo]);
  useEffect(() => {
    if (!loaded) return;
    try {
      if (nearby) sessionStorage.setItem(nearbyKey, JSON.stringify(nearby));
      else sessionStorage.removeItem(nearbyKey);
    } catch {}
  }, [nearby, nearbyKey, loaded]);
  useEffect(() => {
    if (!loaded) return;
    const saved = writeList(browserStorage(), listKey, lines);
    // A failed save is shown in the list itself, not only in a toast that disappears.
    setStorageIssue((issue) =>
      saved ? (issue === "save-failed" ? null : issue) : issue === "blocked" ? issue : "save-failed",
    );
  }, [lines, loaded, listKey]);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 760px)");
    const update = () => setNarrow(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  // The API sends one complete snapshot (cached by the browser, the edge and React Query), so search
  // and filters run here instead of asking the server for a new list on every keystroke.
  const search = useDebounced(query, 220);
  const typed = search.trim();
  // Between a keystroke and the debounced search catching up, the current grid stays on screen, veiled.
  const searching = query.trim() !== typed;
  const result = useQuery({
    queryKey: ["public", demo],
    queryFn: ({ signal }): Promise<Data> =>
      demo ? Promise.resolve(demoData() as Data) : loadSnapshot<Data>(signal),
  });
  const loading = result.isPending;
  // No snapshot at all: every view says so instead of reading as "no offers".
  const error = result.isError && !result.data ? loadErrorMessage(result.error) : "";
  // A failed refresh keeps showing the data already loaded, and says since when.
  const refreshFailed = result.isError && !!result.data;
  const retry = () => void result.refetch();
  const priceHidden = offline
    ? "Preço oculto sem conexão"
    : error
      ? "Preço indisponível no momento"
      : undefined;
  // Only the regions the snapshot actually covers; a link cannot put another city in the header.
  const regions = result.data?.regions?.length ? result.data.regions : [BRAND.city];
  const dataRegion = regions.includes(region) ? region : regions[0];
  // Built once per snapshot load, not per keystroke - see lib/search.ts's buildIndex for why that matters.
  const searchIndex = useMemo(
    () => buildIndex(result.data?.products ?? [], (p) => `${p.name} ${p.brand}`),
    [result.data],
  );
  const data = useMemo(() => {
    const all = result.data;
    if (!all || !search.trim()) return all ?? null;
    return { ...all, products: filterIndexed(searchIndex, search) };
  }, [result.data, search, searchIndex]);
  useEffect(() => {
    const d = result.data;
    if (!d || !sharedTarget || sharedOpened.current) return;
    sharedOpened.current = true;
    const product = d.products.find((p) => p.id === sharedTarget.productId);
    if (!product) {
      setSharedNotice(
        "O produto deste link não está mais entre as ofertas monitoradas: ele pode ter saído do site da loja ou da última coleta. Busque um produto parecido.",
      );
      return;
    }
    setActive(product);
    // A link to a product page (not to one of its offers) has no offer to look for.
    if (!sharedTarget.offerId) return;
    const offer = rankOffers(d.offers, true).find(
      (o) => o.product_id === product.id && o.id === sharedTarget.offerId,
    );
    if (offer) setConditions(isConditional(offer.conditions));
    else
      setSharedNotice(
        "O preço deste link não está mais atual. Veja abaixo os preços atuais deste produto.",
      );
  }, [result.data, sharedTarget]);
  useEffect(() => {
    if (!active || loading || !sharedTarget || sharedScrolled.current) return;
    const row = document.getElementById(`offer-${sharedTarget.offerId}`);
    if (row) {
      row.scrollIntoView({ block: "center", behavior: "instant" });
      sharedScrolled.current = true;
    }
  }, [active, loading, sharedTarget, conditions]);
  // A product page is a history entry: the browser's back button (and a phone's back gesture) closes it
  // and returns to the list where it was opened, instead of leaving the site.
  useEffect(() => {
    const onPop = () => {
      const id = new URLSearchParams(window.location.search).get("produto");
      const product = id ? result.data?.products.find((p) => p.id === id) : undefined;
      if (product) {
        markHero(product.id);
        withViewTransition(() => {
          setActive(product);
          window.scrollTo({ top: 0, behavior: "instant" });
        }, "product");
        return;
      }
      withViewTransition(() => {
        setActive(null);
        setRestore(returnTo.current);
        returnTo.current = null;
      }, "product");
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [result.data]);
  // Back on the list: the same scroll position, and focus on the card that was opened.
  useLayoutEffect(() => {
    if (active || !restore) return;
    window.scrollTo({ top: restore.scroll, behavior: "instant" });
    const card = document.querySelector<HTMLElement>(`[data-product-id~="${CSS.escape(restore.productId)}"]`);
    // Inside the closing view transition (flushSync): this photo is where the hero morphs back to.
    markHero(restore.productId);
    card?.querySelector<HTMLElement>(".product-open")?.focus({ preventScroll: true });
    // A card in the horizontal rail starts scrolled out of view again: bring it back, sideways only.
    card?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
    setRestore(null);
  }, [active, restore]);
  // On a product page, focus goes to its title, so keyboard and screen reader users start there.
  useEffect(() => {
    if (active) headingRef.current?.focus({ preventScroll: true });
  }, [active?.id]);
  function resetUrl() {
    if (window.location.search) window.history.replaceState(null, "", basePath);
  }
  function clearShared() {
    if (sharedTarget) {
      setSharedTarget(null);
      setSharedNotice("");
      sharedOpened.current = false;
      sharedScrolled.current = false;
    }
    resetUrl();
  }
  const openProduct = (product: Product) => {
    if (!active) returnTo.current = { scroll: window.scrollY, productId: product.id };
    setSharedNotice("");
    window.history.pushState(
      { mdProduct: product.id },
      "",
      `${basePath}?${new URLSearchParams({ produto: product.id })}`,
    );
    // The tapped photo becomes the hero of the product page (plan 006); elsewhere the page just changes.
    markHero(product.id);
    withViewTransition(() => {
      setActive(product);
      window.scrollTo({ top: 0, behavior: "instant" });
    }, "product");
  };
  const closeProduct = () => {
    // Opened here: going back pops that entry (see the popstate handler). Opened from a shared link: close it.
    if (window.history.state?.mdProduct) {
      window.history.back();
      return;
    }
    withViewTransition(() => {
      clearShared();
      setActive(null);
      setRestore(returnTo.current);
      returnTo.current = null;
    }, "product");
  };
  // `filters` starts the destination with something other than a clean slate (the store picker below uses
  // this to land on Buscar already narrowed to one network) - set in the same update as the reset, since
  // withViewTransition's flushSync means a setPf() call made just after navigate() returns can lose a race
  // with this one and never take effect.
  const navigate = (v: View, filters?: Partial<ProductFilters>) => {
    // A cross-fade of 150 ms between views; the pill of the navigation slides on its own.
    withViewTransition(() => {
      clearShared();
      setView(v);
      setActive(null);
      returnTo.current = null;
      setPf({ ...noFilters, ...filters });
      setSortChosen(false);
      setChannel("");
      setCategory("");
      setQuery("");
      setUndo(null);
      window.scrollTo({ top: 0, behavior: "instant" });
    });
  };
  const navPill = useIndicator<HTMLElement>('button[aria-current="page"]', [view, lines.length > 0]);
  const dockMarker = useIndicator<HTMLElement>('button[aria-current="page"]', [view]);
  const add = (p: Product) => {
    const existing = lines.find((x) => x.product_id === p.id);
    if (existing && existing.quantity >= MAX_QUANTITY) {
      notify(`“${short(p.name)}” já está com a quantidade máxima`);
      return;
    }
    setLines((l) =>
      l.some((x) => x.product_id === p.id)
        ? l.map((x) =>
            x.product_id === p.id
              ? { ...x, quantity: Math.min(x.quantity + 1, MAX_QUANTITY) }
              : x,
          )
        : [...l, { product_id: p.id, name: listName(p), quantity: 1, checked: false }],
    );
    setUndo(null);
    notify(
      existing
        ? `Agora são ${existing.quantity + 1} de “${short(p.name)}” na lista`
        : `“${short(p.name)}” adicionado à lista`,
    );
  };
  // Stays on the list (a trip half done isn't lost) but drops out of the per-store estimate below and is
  // shown apart from what is still needed - see the Line type in lib/list-storage.ts.
  const toggleChecked = (id: string) =>
    setLines((l) => l.map((x) => (x.product_id === id ? { ...x, checked: !x.checked } : x)));
  const remove = (ids: string[], message: string) => {
    const previous = lines;
    setUndo({ lines: previous, message });
    setLines((l) => l.filter((x) => !ids.includes(x.product_id)));
    notify(message, {
      undo: () => {
        setLines(previous);
        setUndo(null);
        notify("Lista restaurada");
      },
    });
  };
  const setQuantity = (id: string, quantity: number) => {
    setUndo(null);
    setLines((a) =>
      a.map((x) =>
        x.product_id === id ? { ...x, quantity: Math.max(1, Math.min(MAX_QUANTITY, quantity)) } : x,
      ),
    );
  };
  const allOffers = data?.offers || [];
  const locationsByRetailer = useMemo(
    () => groupLocations(data?.retailer_locations || []),
    [data],
  );
  const offers = useMemo(
    () => filterNearby(allOffers, nearby, locationsByRetailer),
    [allOffers, nearby, locationsByRetailer],
  );
  const listQuantity = useMemo(
    () => new Map(lines.map((l) => [l.product_id, l.quantity])),
    [lines],
  );
  // This whole derived block is memoized: `data` only changes when the *debounced* `search`
  // (or the snapshot) changes, so between keystrokes these stay stable and the catalog isn't
  // re-filtered on every render — that was the source of the typing lag.
  const {
    filteredOffers,
    productOffers,
    shown,
    todayProducts,
    deal,
    offersByProduct,
    pricedIds,
    coverageNow,
  } = useMemo(() => {
    const products = (data?.products || []).filter(
      (p) =>
        (!category || p.category === category) &&
        (!nearby || offers.some((o) => o.product_id === p.id)) &&
        (!networks.length ||
          offers.some(
            (o) => o.product_id === p.id && networks.includes(o.retailer_id),
          )),
    );
    const filteredOffers = offers.filter(
      (o) =>
        (!networks.length || networks.includes(o.retailer_id)) &&
        (!channel || o.channel === channel),
    );
    const productOffers = filteredOffers.filter(
      (o) => o.product_id === active?.id,
    );
    const offersByProduct = new Map<string, Offer[]>();
    for (const o of filteredOffers) {
      const list = offersByProduct.get(o.product_id);
      if (list) list.push(o);
      else offersByProduct.set(o.product_id, [o]);
    }
    const pricedIds = new Set<string>();
    for (const [id, os] of offersByProduct) if (rankOffers(os, conditions).length) pricedIds.add(id);
    const shown = products.filter((p) =>
      view === "today" ? pricedIds.has(p.id) && !offline && !error : true,
    );
    const deal =
      !offline && !error ? dailyDeals(shown, filteredOffers)[0] : undefined;
    // "Ofertas do dia": the biggest discounts the stores themselves state (against their own regular price),
    // nearest first among equals - the same order as the search's default, not the catalog's A to Z.
    const byDiscount =
      view === "today"
        ? filterProducts(shown, offersByProduct, { ...noFilters, sort: "discount-near" }, {
            conditions,
            includeUnpriced: false,
            nearby: nearby?.point,
            locationsByRetailer,
          })
        : shown;
    const todayProducts = deal
      ? [deal.product, ...byDiscount.filter((p) => p.id !== deal.product.id)]
      : byDiscount;
    // What the coverage box counts: current prices (any condition) of the offers in reach, not the raw
    // snapshot size, which also counts club variants and prices that are no longer current.
    const currentAll = rankOffers(offers, true);
    const coverageNow = {
      networks: new Set(currentAll.map((o) => o.retailer_id)).size,
      products: new Set(currentAll.map((o) => o.product_id)).size,
      offers: currentAll.length,
    };
    return {
      filteredOffers,
      productOffers,
      shown,
      todayProducts,
      deal,
      offersByProduct,
      pricedIds,
      coverageNow,
    };
  }, [
    data,
    offers,
    offline,
    error,
    conditions,
    active,
    view,
    category,
    nearby,
    networks,
    channel,
    locationsByRetailer,
  ]);
  const listResetKey = [
    view,
    search,
    JSON.stringify(pf),
    sortChosen,
    channel,
    category,
    conditions,
    nearby
      ? `${nearby.point.latitude},${nearby.point.longitude},${nearby.radiusKm}`
      : "",
    old,
  ].join("|");
  const rail = useIncremental(todayProducts.length, 12, listResetKey);
  const effectiveSort: SortKey = sortChosen
    ? pf.sort === "relevance" && !typed
      ? "discount-near"
      : pf.sort
    : typed
      ? "relevance"
      : "discount-near";
  // Memoized on the debounced `search` (via `shown`) so the filter over the whole catalog only
  // runs after typing pauses, not on every keystroke.
  const searchResults = useMemo(
    () =>
      view === "search"
        ? filterProducts(shown, offersByProduct, { ...pf, sort: effectiveSort }, {
            conditions,
            includeUnpriced: old,
            nearby: nearby?.point,
            locationsByRetailer,
            query: typed,
          })
        : [],
    [view, shown, offersByProduct, pf, effectiveSort, conditions, old, nearby, locationsByRetailer, typed],
  );
  const hasConditional = offers.some((o) => isConditional(o.conditions));
  // Products the search found that have no current price (an outdated or expired one only, or none).
  const hasUnpriced = shown.some((p) => !pricedIds.has(p.id));
  // With no result: would the text alone have found priced products? Then the filters removed them all.
  const matchedWithoutFilters = useMemo(() => {
    if (view !== "search" || searchResults.length || !data) return 0;
    const priced = new Set(rankOffers(offers, conditions).map((o) => o.product_id));
    return data.products.filter((p) => priced.has(p.id)).length;
  }, [view, searchResults, data, offers, conditions]);
  // Several sizes of the same product line become one card with a price range (see lib/group.ts), computed
  // once over the whole sorted result set - not per page, so "load more" never regroups an already-shown
  // card into (or out of) a range card the person has already seen.
  const groupedSearchResults = useMemo(() => groupBySize(searchResults), [searchResults]);
  const grid = useIncremental(groupedSearchResults.length, 24, listResetKey);
  // The detail page's own two lists (offers for this product, alternatives in its category) can each run
  // long for a popular product or a big category, same as the search grid - paginated here the same way,
  // reset whenever the open product or a filter that reshuffles its offers changes.
  const detailResetKey = [
    active?.id ?? "",
    conditions,
    nearby ? `${nearby.point.latitude},${nearby.point.longitude},${nearby.radiusKm}` : "",
  ].join("|");
  const rankedProductOffers = useMemo(
    () => rankOffers(productOffers, conditions),
    [productOffers, conditions],
  );
  const comparison = useIncremental(rankedProductOffers.length, 10, detailResetKey);
  const comparisonFiltered = Boolean(nearby || networks.length || channel);
  const suspect = suspiciousSpread(rankedProductOffers);
  // Published offers of this product left out of the comparison, each with its reason.
  const inactiveOffers = useMemo(
    () => productOffers.filter((o) => o.published === 1 && outOfComparison(o) !== null),
    [productOffers, clock],
  );
  const conditionalCount = useMemo(
    () => rankOffers(productOffers, true).filter((o) => isConditional(o.conditions)).length,
    [productOffers],
  );
  // The whole catalog, not `products` above - that one is narrowed to whatever text is still sitting in
  // the search box (see the `data` memo's own note on why), which is exactly right for the search results
  // grid but wrong here: a product opened while "queijo" is still typed must still see every alternative,
  // not just the other ones whose name happens to contain "queijo".
  const allProducts = result.data?.products ?? [];
  const altProducts = useMemo(
    () => (active ? alternativesOf(allProducts, active, pricedIds) : []),
    [allProducts, active, pricedIds],
  );
  const alternatives = useIncremental(altProducts.length, 24, detailResetKey);
  const outsideOffers =
    nearby && active
      ? rankOffers(
          allOffers.filter(
            (o) =>
              o.product_id === active.id &&
              (!networks.length || networks.includes(o.retailer_id)) &&
              (!channel || o.channel === channel),
          ),
          conditions,
        ).filter((o) => !productOffers.some((p) => p.id === o.id)).length
      : 0;
  const unlocated = nearby
    ? rankOffers(allOffers, conditions).filter(
        (o) => !(locationsByRetailer[o.retailer_id]?.length),
      ).length
    : 0;
  const activeQuantity =
    lines.find((l) => l.product_id === active?.id)?.quantity || 0;
  const showSearch = !active && (view === "today" || view === "search");
  // An item already picked up no longer costs anything to plan for.
  const neededLines = useMemo(() => lines.filter((l) => !l.checked), [lines]);
  // Checked items sink to the bottom, in a stable order, instead of vanishing from the list entirely.
  const sortedLines = useMemo(
    () => [...lines].sort((a, b) => Number(a.checked) - Number(b.checked)),
    [lines],
  );
  const estimates = useMemo(
    () => (offline || error ? [] : storeEstimates(neededLines, offers, nearby, locationsByRetailer)),
    [neededLines, offers, offline, error, clock, nearby, locationsByRetailer],
  );
  // Cheapest current price of each product, for the suggestions of the list's add box.
  const listProducts = useMemo(
    () => (view === "list" ? productsWithPrice(data?.products ?? [], offers) : []),
    [data, offers, view],
  );
  const priceIndex = useMemo(() => {
    const cheapest = new Map<string, number>();
    if (view === "list")
      for (const o of rankOffers(offers))
        if (!cheapest.has(o.product_id)) cheapest.set(o.product_id, o.price_cents!);
    return cheapest;
  }, [offers, view]);
  const productById = useMemo(
    () => new Map((result.data?.products ?? []).map((p) => [p.id, p])),
    [result.data],
  );
  const lineName = (l: Line) => {
    const product = productById.get(l.product_id);
    return product ? listName(product) : l.name;
  };
  const retailerName = (id: string) => result.data?.retailers.find((r) => r.id === id)?.name ?? id;
  const filterChips: { key: string; label: string; clear: () => void }[] = [
    ...(category ? [{ key: "category", label: `Categoria: ${category}`, clear: () => setCategory("") }] : []),
    ...pf.networks.map((id) => ({
      key: `network-${id}`,
      label: retailerName(id),
      clear: () => setPf((f) => ({ ...f, networks: f.networks.filter((x) => x !== id) })),
    })),
    ...(pf.minDiscount
      ? [{ key: "discount", label: discountLabels[pf.minDiscount] ?? `Desconto de ${pf.minDiscount}% ou mais`, clear: () => setPf((f) => ({ ...f, minDiscount: 0 })) }]
      : []),
    ...(pf.minPrice !== null
      ? [{ key: "min", label: `A partir de ${money(pf.minPrice)}`, clear: () => setPf((f) => ({ ...f, minPrice: null })) }]
      : []),
    ...(pf.maxPrice !== null
      ? [{ key: "max", label: `Até ${money(pf.maxPrice)}`, clear: () => setPf((f) => ({ ...f, maxPrice: null })) }]
      : []),
    ...(conditions ? [{ key: "conditions", label: "Incluindo preços com condição", clear: () => setConditions(false) }] : []),
    ...(old ? [{ key: "old", label: "Incluindo sem preço atual", clear: () => setOld(false) }] : []),
  ];
  const clearFilters = () => {
    setPf(noFilters);
    setSortChosen(false);
    setCategory("");
    setConditions(false);
    setOld(false);
  };
  const unpricedLines = neededLines.filter((l) => !priceIndex.has(l.product_id));
  function SearchBox(className = "") {
    return (
      <form
        // Chrome iOS annotates forms/fields with __gCrUniqueID before React loads.
        suppressHydrationWarning
        className={`searchbar ${className}`}
        role="search"
        onSubmit={(e) => {
          e.preventDefault();
          setView("search");
          setActive(null);
          clearShared();
          window.scrollTo({ top: 0, behavior: "instant" });
        }}
      >
        <Search size={22} aria-hidden="true" />
        <input
          suppressHydrationWarning
          aria-label="Buscar produtos"
          enterKeyHint="search"
          disabled={!loaded}
          placeholder="Buscar produtos"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            clearShared();
            setView("search");
            setActive(null);
          }}
        />
        {query && (
          <Tooltip label="Limpar busca">
            <button
              type="button"
              className="searchbar-clear"
              aria-label="Limpar busca"
              onClick={() => setQuery("")}
            >
              <X size={18} aria-hidden="true" />
            </button>
          </Tooltip>
        )}
        <button type="submit">
          Buscar <span aria-hidden="true">→</span>
        </button>
      </form>
    );
  }
  const retryButton = <RetryButton onRetry={retry} busy={result.isFetching} />;
  const listButton = (
    <Button variant="secondary" icon={<ClipboardList size={17} aria-hidden="true" />} onClick={() => navigate("list")}>
      Abrir minha lista
    </Button>
  );
  const errorPanel = (
    <StatusPanel kind="error" title="Não foi possível carregar as ofertas">
      <p>
        {error} Nada foi perdido: sua lista continua salva neste aparelho.
      </p>
      <div className="status-actions">
        {retryButton}
        {listButton}
      </div>
    </StatusPanel>
  );
  const offlinePanel = (
    <StatusPanel kind="offline" title="Você está sem conexão">
      <p>
        Os preços ficam ocultos até a conexão voltar, para não mostrar valores
        que podem ter mudado. Sua lista continua salva neste aparelho.
      </p>
      <div className="status-actions">{listButton}</div>
    </StatusPanel>
  );
  const best = rankedProductOffers[0];
  return (
    <TooltipProvider>
    <div className={`app-shell${showSearch ? " has-mobile-search" : ""}`}>
      <a className="skip-link" href="#conteudo">
        Ir para o conteúdo
      </a>
      {demo && (
        <div className="demo-banner">
          MODO DEMONSTRATIVO · dados fictícios{" "}
          <a href="/">Voltar aos dados reais</a>
        </div>
      )}
      <header className="header">
        <a className="brand" href={demo ? "/demo" : "/"}>
          <span className="brand-icon">
            <ShoppingBasket size={25} aria-hidden="true" />
          </span>
          <span>
            {BRAND.name.split(" ")[0].toLowerCase()}
            <span className="brand-second">
              {BRAND.name.split(" ").slice(1).join(" ").toLowerCase()}
              <span className="brand-dot">.</span>
            </span>
          </span>
        </a>
        <nav
          className="desktop-nav"
          aria-label="Navegação principal"
          ref={navPill.ref}
          style={navPill.style}
          data-ready={navPill.ready ? "" : undefined}
        >
          <span className="nav-pill" aria-hidden="true" />
          {views.map(([v, t]) => (
            <button
              key={v}
              className={view === v ? "selected" : ""}
              aria-current={view === v ? "page" : undefined}
              onClick={() => navigate(v)}
            >
              {t}
              {v === "list" && lines.length > 0 && (
                <span className="count" aria-label={`, ${lines.length} ${lines.length === 1 ? "item" : "itens"}`}>
                  <Count value={lines.length} />
                </span>
              )}
            </button>
          ))}
        </nav>
        {regions.length > 1 ? (
          <div className="region">
            <MapPin size={18} aria-hidden="true" />
            <SelectField
              label="Região"
              hideLabel
              value={dataRegion}
              onChange={(next) => {
                setRegion(next);
                setNearby(null);
                try {
                  localStorage.setItem("med-region", next);
                } catch {}
              }}
              options={regions.map((r) => ({ value: r, label: r }))}
            />
            <span className="region-state">CE</span>
          </div>
        ) : (
          // One covered city only: a label, not a selector with a single option.
          <p className="region region-static">
            <MapPin size={18} aria-hidden="true" />
            <span>
              <span className="sr-only">Cobertura: </span>
              {dataRegion}
              <span className="region-state"> CE</span>
            </span>
          </p>
        )}
      </header>
      <main className="main" id="conteudo" tabIndex={-1}>
        {offline && !active && view !== "today" && (
          <div className="notice amber" role="status">
            <WifiOff size={19} aria-hidden="true" />
            <span>
              Você está sem conexão. Os preços ficam ocultos até a conexão
              voltar; sua lista continua salva neste aparelho.
            </span>
          </div>
        )}
        {error && view === "list" && !active && (
          <div className="notice amber" role="alert">
            <TriangleAlert size={19} aria-hidden="true" />
            <span>{error}</span>
            <Button variant="ghost" size="sm" onClick={retry} loading={result.isFetching}>
              {result.isFetching ? "Tentando…" : "Tentar novamente"}
            </Button>
          </div>
        )}
        {refreshFailed && !offline && (
          <div className="notice" role="status">
            <Clock size={19} aria-hidden="true" />
            <span>
              Não foi possível atualizar os preços agora. Você está vendo os
              dados carregados {whenLabel(new Date(result.dataUpdatedAt).toISOString())}.
            </span>
            <Button variant="ghost" size="sm" onClick={retry} loading={result.isFetching}>
              {result.isFetching ? "Tentando…" : "Tentar novamente"}
            </Button>
          </div>
        )}
        {sharedNotice && (
          <p className="notice" role="status">
            {sharedNotice}
          </p>
        )}
        {view !== "flyers" && (
          <NearbyFilter value={nearby} onChange={setNearby} demo={demo} />
        )}
        {active ? (
          <>
            <button className="back" onClick={closeProduct}>
              <ArrowLeft size={18} aria-hidden="true" />{" "}
              {view === "today" ? "Voltar para Hoje" : "Voltar à busca"}
            </button>
            <div className="product-heading">
              <ProductHero product={active} />
              <div>
                {active.brand && <p className="overline">{active.brand}</p>}
                <h1 ref={headingRef} tabIndex={-1}>
                  {active.name}
                </h1>
                <p>{packLabel(active)}</p>
                <p className="product-summary-line">
                  {offline ? (
                    "Preços ocultos sem conexão."
                  ) : error ? (
                    "Preços indisponíveis no momento."
                  ) : best && suspect ? (
                    <>
                      {rankedProductOffers.length} preços com diferença incomum entre redes: confira
                      a embalagem antes de decidir.{" "}
                      <a href="#comparacao" className="text-link">
                        Ver comparação
                      </a>
                    </>
                  ) : best ? (
                    <>
                      {rankedProductOffers.length === 1 ? "Único preço atual" : "Menor preço atual"}:{" "}
                      <strong>{money(best.price_cents!)}</strong> no {best.retailer_name}
                      {isConditional(best.conditions) && ` (${lowerFirst(conditionLabel(best.conditions))})`} ·{" "}
                      {rankedProductOffers.length} {rankedProductOffers.length === 1 ? "preço" : "preços"}{" "}
                      <a href="#comparacao" className="text-link">
                        Ver comparação
                      </a>
                    </>
                  ) : (
                    "Sem preço atual nas lojas monitoradas."
                  )}
                </p>
                <div className="product-list-actions">
                  <p className="product-list-status" aria-live="polite">
                    {activeQuantity > 0
                      ? `${activeQuantity} ${activeQuantity === 1 ? "unidade" : "unidades"} na sua lista`
                      : "Salve na lista para planejar suas quantidades."}
                  </p>
                  <div>
                    <Button
                      variant="primary"
                      size="lg"
                      disabled={activeQuantity >= MAX_QUANTITY}
                      icon={<Plus size={18} aria-hidden="true" />}
                      onClick={() => add(active)}
                    >
                      {activeQuantity
                        ? "Adicionar mais 1"
                        : "Adicionar à lista"}
                    </Button>
                    {activeQuantity > 0 && (
                      <Button
                        variant="ghost"
                        trailing
                        icon={<ChevronRight size={17} aria-hidden="true" />}
                        onClick={() => navigate("list")}
                      >
                        Ver minha lista
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </div>
            <div className="section-heading" id="comparacao">
              <div>
                <h2>Mesmo produto, preços encontrados</h2>
                <p>
                  Mesmo nome e tamanho de embalagem em cada rede monitorada.
                  {nearby
                    ? ` Lojas até ${nearby.radiusKm} km da sua referência.`
                    : ""}
                </p>
              </div>
            </div>
            {(conditionalCount > 0 || conditions) && (
              <CheckboxField
                className="detail-conditions"
                checked={conditions}
                onChange={setConditions}
                label={
                  <>
                    Incluir preços de clube, cupom e outras condições
                    {conditionalCount > 0 &&
                      ` (${conditionalCount} ${conditionalCount === 1 ? "disponível" : "disponíveis"})`}
                  </>
                }
              />
            )}
            {offline ? (
              offlinePanel
            ) : error ? (
              errorPanel
            ) : (
              <>
                {suspect && (
                  <div className="notice amber suspect-warning" role="note">
                    <TriangleAlert size={19} aria-hidden="true" />
                    <span>
                      Os preços deste produto variam{" "}
                      {new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(
                        priceSpread(rankedProductOffers),
                      )}{" "}
                      vezes entre as redes. Isso costuma indicar embalagem ou
                      unidade de venda diferente (por quilo, por unidade, caixa).
                      Confira no site da loja antes de decidir; o preço por kg/L
                      não é mostrado.
                    </span>
                  </div>
                )}
                <div className="comparison-list">
                  {rankedProductOffers.slice(0, comparison.count).map((o, i) => (
                    <OfferRow
                      key={o.id}
                      offer={o}
                      product={active}
                      // A 3x gap means the rows may not be the same pack: no "lowest" claim on any of them.
                      note={suspect ? null : lowestPriceLabel(rankedProductOffers, i, comparisonFiltered)}
                      shared={sharedTarget?.offerId === o.id}
                      demo={demo}
                      region={dataRegion}
                      nearby={nearby}
                      locationsByRetailer={locationsByRetailer}
                      hideUnitPrice={suspect}
                    />
                  ))}
                </div>
                {comparison.hasMore && (
                  <>
                    <LoadMore onVisible={comparison.more} />
                    <p className="muted list-progress">
                      Mostrando {comparison.count.toLocaleString("pt-BR")} de{" "}
                      {rankedProductOffers.length.toLocaleString("pt-BR")} ofertas
                    </p>
                  </>
                )}
                {outsideOffers > 0 && (
                  <div className="nearby-outside">
                    <p>
                      {outsideOffers}{" "}
                      {outsideOffers === 1
                        ? "outra opção está"
                        : "outras opções estão"}{" "}
                      fora deste filtro de localização.
                    </p>
                    <Button variant="ghost" size="sm" trailing icon={<ChevronRight size={16} aria-hidden="true" />} onClick={() => setNearby(null)}>
                      Ver preços em todas as lojas
                    </Button>
                  </div>
                )}
                {rankedProductOffers.length === 0 && (
                  <div className="empty compact">
                    <Clock aria-hidden="true" />
                    <h3>Sem preço atual para este produto</h3>
                    <p>
                      {conditionalCount > 0 && !conditions
                        ? "Há preços com condição (clube, cupom ou quantidade mínima). Marque a opção acima para vê-los."
                        : "Você pode mantê-lo na lista e consultar novamente depois."}
                    </p>
                  </div>
                )}
                {inactiveOffers.length > 0 && (
                  <details className="inactive-offers" open={rankedProductOffers.length === 0}>
                    <summary>
                      {inactiveOffers.length}{" "}
                      {inactiveOffers.length === 1 ? "preço fora da comparação" : "preços fora da comparação"}
                    </summary>
                    <ul>
                      {inactiveOffers.map((o) => (
                        <li key={o.id}>
                          <strong>{o.retailer_name}</strong>
                          {o.price_cents !== null && <span> · {money(o.price_cents)}</span>}
                          <span className="inactive-reason">{outOfComparison(o)}</span>
                        </li>
                      ))}
                    </ul>
                    <p className="fineprint">
                      Estes preços não entram no menor preço, nas ofertas do dia
                      nem nas estimativas da lista.
                    </p>
                  </details>
                )}
              </>
            )}
            <h2 className="spaced">Alternativas</h2>
            <p className="muted">
              {active.subcategory
                ? `Outros produtos do tipo "${active.subcategory}". São produtos diferentes: não entram na comparação acima.`
                : "Produtos diferentes da mesma categoria. Não entram na comparação acima."}
            </p>
            {altProducts.length === 0 ? (
              <div className="empty compact">
                <Clock aria-hidden="true" />
                <h3>Sem alternativas no momento</h3>
                <p>Nenhum outro produto do mesmo tipo tem preço atual agora.</p>
              </div>
            ) : (
              <>
                <div className="product-grid">
                  {altProducts.slice(0, alternatives.count).map((p) => (
                    <ProductCard
                      key={p.id}
                      p={p}
                      region={dataRegion}
                      nearby={nearby}
                      locationsByRetailer={locationsByRetailer}
                      offers={filteredOffers}
                      conditions={conditions}
                      priceHidden={priceHidden}
                      listQuantity={listQuantity.get(p.id)}
                      onOpen={openProduct}
                      onAdd={add}
                    />
                  ))}
                </div>
                {alternatives.hasMore && (
                  <>
                    <LoadMore onVisible={alternatives.more} />
                    <p className="muted list-progress">
                      Mostrando {alternatives.count.toLocaleString("pt-BR")} de{" "}
                      {altProducts.length.toLocaleString("pt-BR")} produtos
                    </p>
                  </>
                )}
              </>
            )}
          </>
        ) : (
          <>
            {(view === "today" || view === "search") && (
              <>
                {view === "search" && (
                  <div
                    className={`intro catalog-intro${view === "search" ? " search-intro" : ""}`}
                  >
                    <div>
                      <p className="overline">Suas compras em Fortaleza</p>
                      <h1>
                        <span className="catalog-mobile-title">
                          Buscar produtos
                        </span>
                        <span className="catalog-desktop-title">
                          Encontre o que você precisa.
                        </span>
                      </h1>
                    </div>
                    <div className="pilot-stamp">
                      <ShieldCheck size={22} aria-hidden="true" />
                      <span>
                        Piloto em validação
                        <br />
                        <strong>Informação com origem</strong>
                      </span>
                    </div>
                  </div>
                )}
                {SearchBox("desktop-search")}
                <div className="search-hint">
                  Busque por produto, marca ou embalagem. Acentos não fazem diferença.
                </div>
                {view === "search" && (
                  <div
                    className={`category-row${filters ? " categories-expanded" : ""}`}
                    role="group"
                    aria-label="Categorias"
                  >
                    {[
                      "Todas",
                      ...(data?.categories.length
                        ? data.categories
                        : ["Mercearia", "Limpeza", "Bebidas", "Higiene"]),
                    ].map((c) => {
                      const on = category === c || (c === "Todas" && !category);
                      return (
                        <Chip
                          key={c}
                          selected={on}
                          icon={c === "Todas" ? <SlidersHorizontal size={16} aria-hidden="true" /> : undefined}
                          onClick={() => {
                            setCategory(c === "Todas" ? "" : c);
                            setView("search");
                          }}
                        >
                          {c}
                        </Chip>
                      );
                    })}
                  </div>
                )}
                {!!data?.retailers.length && (
                  // A friendlier way to see one chain's own catalog than digging into "Filtros" - the same
                  // spot on both Hoje and Buscar, so it isn't only reachable from one of them. On Hoje this
                  // jumps to Buscar already narrowed; on Buscar it narrows in place, keeping any other
                  // filter set, and taps the same chip again to go back to every store.
                  <div className="store-picker">
                    <p className="overline">Em {dataRegion}, temos estas redes monitoradas</p>
                    <div className="chip-row" role="group" aria-label="Ver só as ofertas de uma rede">
                      {data.retailers.map((r) => {
                        const sole = pf.networks.length === 1 && pf.networks[0] === r.id;
                        return (
                          <Chip
                            key={r.id}
                            selected={sole}
                            onClick={() =>
                              view === "today"
                                ? navigate("search", { networks: [r.id] })
                                : setPf((f) => ({ ...f, networks: sole ? [] : [r.id] }))
                            }
                          >
                            {r.name}
                          </Chip>
                        );
                      })}
                    </div>
                  </div>
                )}
              </>
            )}
            {view === "today" && (
              <>
                <div className="section-heading daily-heading">
                  <div>
                    <h1>
                      Ofertas do dia<span>.</span>
                    </h1>
                    <p>
                      Maiores descontos informados pelas lojas, entre as ofertas
                      monitoradas{nearby ? ` até ${nearby.radiusKm} km da sua referência` : ""}.
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    trailing
                    icon={<ChevronRight size={17} aria-hidden="true" />}
                    onClick={() => navigate("search")}
                  >
                    Ver todas
                  </Button>
                </div>
                {loading ? (
                  <>
                    <p className="loading" role="status">
                      Carregando as ofertas publicadas…
                    </p>
                    <RailSkeleton />
                  </>
                ) : error ? (
                  errorPanel
                ) : offline ? (
                  offlinePanel
                ) : shown.length ? (
                  <OfferRail onEnd={rail.hasMore ? rail.more : undefined}>
                    {todayProducts.slice(0, rail.count).map((p, i) => (
                      <ProductCard
                        key={p.id}
                        p={p}
                        style={{ "--i": Math.min(i, 5) } as CSSProperties}
                        region={dataRegion}
                        nearby={nearby}
                        locationsByRetailer={locationsByRetailer}
                        deal={deal?.product.id === p.id ? deal : undefined}
                        offers={filteredOffers}
                        conditions={conditions}
                        priceHidden={priceHidden}
                        listQuantity={listQuantity.get(p.id)}
                        onOpen={openProduct}
                        onAdd={add}
                      />
                    ))}
                  </OfferRail>
                ) : nearby ? (
                  <div className="empty compact nearby-empty">
                    <MapPin size={30} aria-hidden="true" />
                    <h3>Nenhuma oferta neste raio</h3>
                    <p>
                      Ainda não temos preços atuais de lojas até{" "}
                      {nearby.radiusKm} km dessa referência.
                    </p>
                    <Button variant="secondary" onClick={() => setNearby(null)}>
                      Ver preços em todas as lojas
                    </Button>
                  </div>
                ) : (
                  <div className="empty">
                    <span className="empty-icon">
                      <ShoppingBasket size={33} strokeWidth={1.3} aria-hidden="true" />
                    </span>
                    <div>
                      <p className="overline">Estamos conferindo as fontes</p>
                      <h3>
                        Uma boa comparação começa
                        <br className="desktop-break" /> com um preço confiável.
                      </h3>
                      <p>
                        Ainda não há preços atuais publicados para comparar.{" "}
                        Enquanto isso, consulte os encartes oficiais e monte sua
                        lista.
                      </p>
                      <Button
                        variant="primary"
                        trailing
                        icon={<ArrowUpRight size={17} aria-hidden="true" />}
                        onClick={() => navigate("flyers")}
                      >
                        Consultar encartes
                      </Button>
                    </div>
                  </div>
                )}
                {nearby && !offline && !error && (
                  <p className="nearby-scope">
                    Distâncias em linha reta até a unidade mais próxima de cada
                    rede.{" "}
                    {unlocated > 0
                      ? `${unlocated} ${unlocated === 1 ? "preço de rede sem endereço cadastrado ficou" : "preços de redes sem endereço cadastrado ficaram"} fora do filtro.`
                      : "Os preços são do site de cada rede e podem variar na loja."}
                  </p>
                )}
                {!error && (
                  <div className="coverage">
                    <ShieldCheck size={20} aria-hidden="true" />
                    <div>
                      <strong>
                        {demo ? "Cobertura fictícia" : "Ofertas monitoradas"}
                      </strong>
                      <span>
                        {loading || !data
                          ? <><span className="sr-only">Carregando a cobertura…</span><Skeleton style={{ width: "min(240px, 70%)", height: 13 }} /></>
                          : `${count(coverageNow.networks)} ${coverageNow.networks === 1 ? "rede" : "redes"} · ${count(coverageNow.products)} produtos · ${count(coverageNow.offers)} preços atuais${nearby ? " neste raio" : ""}`}
                      </span>
                      {data && (
                        <span className="coverage-time">
                          Dados publicados {whenLabel(data.generated_at)}
                        </span>
                      )}
                    </div>
                    <a href="#sources" className="text-link">
                      Como ler os preços <ChevronRight size={17} aria-hidden="true" />
                    </a>
                  </div>
                )}
                <div className="section-heading">
                  <div>
                    <p className="overline">Direto dos supermercados</p>
                    <h2>Encartes para consultar</h2>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    trailing
                    icon={<ChevronRight size={17} aria-hidden="true" />}
                    onClick={() => navigate("flyers")}
                  >
                    Ver todos
                  </Button>
                </div>
                {(() => {
                  const flyers = organizeFlyers(data?.flyers || []).current.slice(0, 3);
                  if (loading)
                    return (
                      <>
                        <p className="loading" role="status">
                          Carregando encartes…
                        </p>
                        <FlyerGridSkeleton />
                      </>
                    );
                  if (error) return <p className="muted">Os encartes também dependem da consulta que falhou.</p>;
                  if (!flyers.length)
                    return <p className="muted">Nenhum encarte dentro da validade publicado agora.</p>;
                  return (
                    <div className="flyer-grid">
                      {flyers.map((f) => (
                        <FlyerCard key={f.id} f={f} />
                      ))}
                    </div>
                  );
                })()}
              </>
            )}
            {view === "search" && (
              <>
                <div className="section-heading results-heading">
                  <h2>
                    <span className="catalog-mobile-title">
                      {query ? "Resultados" : "Produtos monitorados"}
                    </span>
                    <span className="catalog-desktop-title">
                      {query
                        ? `Resultados para “${query}”`
                        : "Produtos monitorados"}
                    </span>
                  </h2>
                  <Button
                    variant="secondary"
                    size="sm"
                    aria-expanded={filters}
                    aria-controls="filter-panel"
                    icon={<SlidersHorizontal size={17} aria-hidden="true" />}
                    onClick={() => setFilters(!filters)}
                  >
                    Filtros
                    {filterChips.length > 0 && (
                      <span className="count" aria-label={`, ${filterChips.length} ativos`}>
                        {filterChips.length}
                      </span>
                    )}
                  </Button>
                </div>
                {filters && (
                  <div className="filter-panel" id="filter-panel">
                    <fieldset className="filter-group">
                      <legend>Redes</legend>
                      <div className="chip-row">
                        {data?.retailers.map((r) => {
                          const on = pf.networks.includes(r.id);
                          return (
                            <ChipCheckbox
                              key={r.id}
                              checked={on}
                              onChange={() =>
                                setPf((f) => ({
                                  ...f,
                                  networks: on
                                    ? f.networks.filter((x) => x !== r.id)
                                    : [...f.networks, r.id],
                                }))
                              }
                            >
                              {r.name}
                            </ChipCheckbox>
                          );
                        })}
                      </div>
                    </fieldset>
                    <SelectField
                      label="Desconto"
                      value={String(pf.minDiscount)}
                      onChange={(next) => setPf((f) => ({ ...f, minDiscount: Number(next) }))}
                      options={[
                        { value: "0", label: "Qualquer" },
                        { value: "1", label: "Só com desconto" },
                        { value: "10", label: "10% ou mais" },
                        { value: "20", label: "20% ou mais" },
                        { value: "30", label: "30% ou mais" },
                        { value: "50", label: "50% ou mais" },
                      ]}
                    />
                    <PriceInput
                      label="Preço mínimo (R$)"
                      value={pf.minPrice}
                      onChange={(minPrice) => setPf((f) => ({ ...f, minPrice }))}
                    />
                    <PriceInput
                      label="Preço máximo (R$)"
                      value={pf.maxPrice}
                      onChange={(maxPrice) => setPf((f) => ({ ...f, maxPrice }))}
                    />
                    {hasConditional && (
                      <CheckboxField
                        checked={conditions}
                        onChange={setConditions}
                        label="Incluir preços de clube e outras condições"
                      />
                    )}
                    {hasUnpriced && (
                      <CheckboxField checked={old} onChange={setOld} label="Incluir produtos sem preço atual" />
                    )}
                    <p className="filter-note">
                      Os filtros valem para o preço de cada loja: “20% ou mais
                      até R$ 10” mostra produtos com uma oferta que atende às
                      duas condições.
                    </p>
                  </div>
                )}
                {!loading && !error && (
                  <div className="results-toolbar">
                    <p className="results-count" role="status">
                      {searching
                        ? "Atualizando resultados…"
                        : `${count(searchResults.length)} ${searchResults.length === 1 ? "produto" : "produtos"}${
                            groupedSearchResults.length !== searchResults.length
                              ? ` em ${count(groupedSearchResults.length)} cartões`
                              : ""
                          }`}
                    </p>
                    <SelectField
                      label="Ordenar por"
                      className="sort-select"
                      value={effectiveSort}
                      onChange={(key) => {
                        setPf((f) => ({ ...f, sort: key }));
                        setSortChosen(true);
                      }}
                      options={(Object.keys(sortLabels) as SortKey[])
                        .filter((key) => key !== "relevance" || typed)
                        .map((key) => ({ value: key, label: sortLabels[key] }))}
                    />
                  </div>
                )}
                {effectiveSort === "discount-near" && !nearby && !loading && !error && (
                  <p className="sort-hint muted">
                    Defina seu local em “Perto de você” para desempatar pela
                    distância; por enquanto, só o desconto está ordenando.
                  </p>
                )}
                {filterChips.length > 0 && (
                  <div className="filter-chips" role="group" aria-label="Filtros ativos">
                    {filterChips.map((chip) => (
                      <Chip
                        key={chip.key}
                        removable
                        aria-label={`Remover filtro: ${chip.label}`}
                        onClick={chip.clear}
                      >
                        {chip.label}
                      </Chip>
                    ))}
                    <Button variant="ghost" size="sm" onClick={clearFilters}>
                      Limpar filtros
                    </Button>
                  </div>
                )}
                {loading ? (
                  <>
                    <p role="status" className="loading">
                      {sharedTarget ? "Abrindo o produto do link…" : "Carregando as ofertas publicadas…"}
                    </p>
                    <GridSkeleton />
                  </>
                ) : error ? (
                  errorPanel
                ) : (
                  // The grid stays mounted while a new search is computed: veiled, never replaced by a box.
                  <div className="results" data-busy={searching}>
                    <div className="product-grid">
                      {groupedSearchResults.slice(0, grid.count).map((entry) =>
                        "members" in entry ? (
                          <ProductRangeCard
                            key={entry.key}
                            group={entry}
                            offersByProduct={offersByProduct}
                            conditions={conditions}
                            nearby={nearby}
                            locationsByRetailer={locationsByRetailer}
                            onOpen={openProduct}
                            onAdd={add}
                          />
                        ) : (
                          <ProductCard
                            key={entry.id}
                            p={entry}
                            region={dataRegion}
                            nearby={nearby}
                            locationsByRetailer={locationsByRetailer}
                            offers={filteredOffers}
                            conditions={conditions}
                            priceHidden={priceHidden}
                            listQuantity={listQuantity.get(entry.id)}
                            onOpen={openProduct}
                            onAdd={add}
                          />
                        ),
                      )}
                    </div>
                    {grid.hasMore ? (
                      <>
                        <LoadMore onVisible={grid.more} />
                        <p className="muted list-progress">
                          Mostrando {grid.count.toLocaleString("pt-BR")} de{" "}
                          {groupedSearchResults.length.toLocaleString("pt-BR")} cartões
                        </p>
                      </>
                    ) : (
                      groupedSearchResults.length > 24 && (
                        <p className="muted list-progress">Fim dos resultados.</p>
                      )
                    )}
                    {!searchResults.length && (
                      <div className="empty compact">
                        <Search size={30} aria-hidden="true" />
                        {nearby ? (
                          <>
                            <h3>Nenhuma oferta neste raio</h3>
                            <p>
                              Não encontramos {typed ? "este produto" : "preços atuais"} em lojas até{" "}
                              {nearby.radiusKm} km da referência. Amplie a distância ou remova o
                              filtro de localização.
                            </p>
                            <Button variant="secondary" onClick={() => setNearby(null)}>
                              Ver em todas as lojas
                            </Button>
                          </>
                        ) : matchedWithoutFilters > 0 ? (
                          <>
                            <h3>Nenhuma oferta com estes filtros</h3>
                            <p>
                              {count(matchedWithoutFilters)}{" "}
                              {matchedWithoutFilters === 1 ? "produto corresponde" : "produtos correspondem"}{" "}
                              {typed ? "à busca" : "ao catálogo"} sem os filtros ativos.
                            </p>
                            <Button variant="secondary" onClick={clearFilters}>
                              Remover filtros
                            </Button>
                          </>
                        ) : typed ? (
                          <>
                            <h3>Nenhum produto encontrado para “{typed}”</h3>
                            <p>
                              Confira a grafia ou tente uma palavra mais curta, como
                              “arroz” ou “leite”. A busca considera o começo das
                              palavras e ignora acentos.
                            </p>
                            <Button
                              variant="secondary"
                              onClick={() => {
                                clearShared();
                                setQuery("");
                                clearFilters();
                              }}
                            >
                              Limpar busca
                            </Button>
                          </>
                        ) : (
                          <>
                            <h3>Nenhum produto com preço atual</h3>
                            <p>Consulte os encartes enquanto novos preços são publicados.</p>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
            {view === "flyers" &&
              (loading ? (
                <>
                  <p className="loading" role="status">
                    Carregando os encartes…
                  </p>
                  <FlyerGridSkeleton count={6} />
                </>
              ) : error ? (
                errorPanel
              ) : (
                <FlyerBrowser
                  flyers={data?.flyers || []}
                  retailers={data?.retailers || []}
                />
              ))}
            {view === "list" && (
              <>
                <div className="page-title">
                  <p className="overline">Sem cadastro, guardada neste aparelho</p>
                  <h1>Minha lista.</h1>
                  <p>
                    {lines.length} {lines.length === 1 ? "item" : "itens"} para
                    seu planejamento de preços
                    {neededLines.length < lines.length &&
                      ` · ${lines.length - neededLines.length} já ${lines.length - neededLines.length === 1 ? "pego" : "pegos"}`}
                    .
                  </p>
                  <p className="list-purpose">
                    Aqui você consulta e compara preços. A compra é feita
                    diretamente com a loja.
                  </p>
                </div>
                {storageMessage(storageIssue) && (
                  <div className="notice amber storage-notice" role="status">
                    <TriangleAlert size={19} aria-hidden="true" />
                    <span>{storageMessage(storageIssue)}</span>
                    {(storageIssue === "unreadable" || storageIssue === "partial") && (
                      <Button variant="ghost" size="sm" onClick={() => setStorageIssue(null)}>
                        Entendi
                      </Button>
                    )}
                  </div>
                )}
                <ListAdder
                  products={listProducts}
                  priceOf={(id) => priceIndex.get(id) ?? null}
                  onProduct={add}
                />
                {undo && (
                  <div className="notice undo-notice" role="status">
                    <span>{undo.message}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<Undo2 size={16} aria-hidden="true" />}
                      onClick={() => {
                        setLines(undo.lines);
                        setUndo(null);
                        notify("Lista restaurada");
                      }}
                    >
                      Desfazer
                    </Button>
                  </div>
                )}
                {!lines.length && (
                  <div className="empty compact">
                    <ClipboardList size={32} aria-hidden="true" />
                    <h3>Comece sua lista de consulta.</h3>
                    <p>
                      Adicione um item acima ou escolha um produto na busca.
                    </p>
                  </div>
                )}
                {!loading && !offline && !error && unpricedLines.length > 0 && (
                  <div className="notice">
                    <span>
                      {unpricedLines.length === 1
                        ? "1 item da lista não tem preço atual e não entra no cálculo."
                        : `${unpricedLines.length} itens da lista não têm preço atual e não entram no cálculo.`}
                    </span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        remove(
                          unpricedLines.map((l) => l.product_id),
                          unpricedLines.length === 1
                            ? "1 item sem preço atual foi removido."
                            : `${unpricedLines.length} itens sem preço atual foram removidos.`,
                        )
                      }
                    >
                      Remover esses itens
                    </Button>
                  </div>
                )}
                <div className="shopping-list">
                  {sortedLines.map((l) => {
                    const o =
                      offline || error
                        ? null
                        : rankOffers(
                            offers.filter((o) => o.product_id === l.product_id),
                          )[0];
                    // Same per-kg/L/unit price shown everywhere else a price appears (search cards, the
                    // range-card modal, the detail comparison list) - suppressed the same way too, when
                    // the pack is already exactly one kg/L/unit and it would just repeat the price.
                    const product = productById.get(l.product_id);
                    const unit = o && product ? unitPriceText(product, o.price_cents!) : null;
                    const name = lineName(l);
                    const priceLine = (
                      <p>
                        {offline
                          ? "Preço oculto sem conexão"
                          : error
                            ? "Preço indisponível no momento"
                            : loading
                              ? "Carregando preço…"
                              : !product
                                ? "Este produto não está mais entre as ofertas monitoradas"
                                : o
                                  ? `Menor preço atual: ${money(o.price_cents!)}${unit ? ` (${unit})` : ""} no ${o.retailer_name} · visto ${whenLabel(o.price_observed_at)}`
                                  : `Sem preço atual nas lojas monitoradas${nearby ? " neste raio" : ""}`}
                      </p>
                    );
                    return (
                      <article
                        className={`list-item${l.checked ? " list-item-checked" : ""}`}
                        key={l.product_id}
                        data-checked={l.checked || undefined}
                      >
                        <CheckboxField
                          className="list-check"
                          checked={l.checked}
                          onChange={() => toggleChecked(l.product_id)}
                          label={<span className="sr-only">Marcar “{short(name)}” como já pego</span>}
                        />
                        <div className="list-product">
                          <Package size={23} aria-hidden="true" />
                          <div>
                            {product ? (
                              // Only the name and price line open the product - StoreContact below can hold
                              // its own tel: link, and a link inside a button is invalid HTML.
                              <button
                                className="list-open"
                                onClick={() => openProduct(product)}
                                aria-label={`${name}. Ver detalhes, alternativas e comparação de preços`}
                              >
                                <h3>{name}</h3>
                                {priceLine}
                              </button>
                            ) : (
                              <>
                                <h3>{name}</h3>
                                {priceLine}
                              </>
                            )}
                            {o && (
                              <StoreContact
                                offer={o}
                                nearby={nearby}
                                locations={locationsByRetailer[o.retailer_id] ?? []}
                              />
                            )}
                          </div>
                        </div>
                        <div className="list-quantity">
                          <p id={`qtd-${l.product_id}`}>Quantidade para planejar</p>
                          <div className="quantity" role="group" aria-labelledby={`qtd-${l.product_id}`}>
                            <button
                              aria-label={`Diminuir ${name}`}
                              disabled={l.quantity <= 1}
                              onClick={() => setQuantity(l.product_id, l.quantity - 1)}
                            >
                              <Minus size={16} aria-hidden="true" />
                            </button>
                            <span aria-live="polite" aria-atomic="true">
                              <span className="sr-only">Quantidade: </span>
                              <Count value={l.quantity} />
                            </span>
                            <button
                              aria-label={`Aumentar ${name}`}
                              disabled={l.quantity >= MAX_QUANTITY}
                              onClick={() => setQuantity(l.product_id, l.quantity + 1)}
                            >
                              <Plus size={16} aria-hidden="true" />
                            </button>
                          </div>
                        </div>
                        <Tooltip label="Remover da lista">
                          <IconButton
                            label={`Remover ${name} da lista`}
                            onClick={() => remove([l.product_id], `“${short(name)}” foi removido da lista.`)}
                          >
                            <X size={19} aria-hidden="true" />
                          </IconButton>
                        </Tooltip>
                      </article>
                    );
                  })}
                </div>
                {lines.length > 0 && (
                  <>
                    <h2 className="spaced">Estimativa por rede</h2>
                    <p className="muted">
                      Soma dos menores preços atuais de cada rede para as
                      quantidades da lista. Uma rede sem preço para algum item
                      mostra só o subtotal do que tem, que não é comparável a um
                      total completo.
                    </p>
                    <StoreEstimates
                      estimates={estimates}
                      total={lines.length}
                      nameOf={(id) => {
                        const line = lines.find((l) => l.product_id === id);
                        return line ? lineName(line) : id;
                      }}
                      hasReference={Boolean(nearby)}
                    />
                    {!estimates.length && (
                      <div className="notice">
                        {offline
                          ? "Estimativas ocultas sem conexão. Elas voltam quando a conexão voltar."
                          : error
                            ? "Estimativas indisponíveis: os preços não foram carregados."
                            : loading
                              ? "Carregando os preços para estimar…"
                              : "Ainda não há preços atuais para os itens da sua lista."}
                      </div>
                    )}
                    <p className="fineprint">
                      Sem frete ou deslocamento. Preços de clube, cupom ou
                      quantidade mínima não entram nas estimativas.
                    </p>
                  </>
                )}
              </>
            )}
            {view === "today" && data && (
              <Sources retailers={data.retailers} offers={allOffers} demo={demo} />
            )}
          </>
        )}
        <footer>
          <span>
            {BRAND.name.toLowerCase()}.{" "}
            <span className="muted">{BRAND.city}, CE</span>
          </span>
          <span className="muted footer-note">
            Consulta de preços. Sem venda, reserva ou entrega.
          </span>
        </footer>
      </main>
      <div className="mobile-dock">
        {showSearch && <div className="mobile-search">{SearchBox()}</div>}
        <nav
          className="bottom-nav"
          aria-label="Navegação mobile"
          ref={dockMarker.ref}
          style={dockMarker.style}
          data-ready={dockMarker.ready ? "" : undefined}
        >
          <span className="nav-marker" aria-hidden="true" />
          {(
            [
              { v: "today", t: "Hoje", icon: ShoppingBasket },
              { v: "search", t: "Buscar", icon: Search },
              { v: "flyers", t: "Encartes", icon: BookOpen },
              { v: "list", t: "Minha lista", icon: ClipboardList },
            ] as const
          ).map(({ v, t, icon: Icon }) => (
            <button
              key={v}
              onClick={() => navigate(v)}
              className={view === v ? "selected" : ""}
              aria-current={view === v ? "page" : undefined}
            >
              <Icon size={22} aria-hidden="true" />
              <span>{t}</span>
              {v === "list" && lines.length > 0 && (
                <b aria-label={`, ${lines.length} ${lines.length === 1 ? "item" : "itens"}`}>
                  <Count value={lines.length} />
                </b>
              )}
            </button>
          ))}
        </nav>
      </div>
      <Notifications bottom={narrow ? (showSearch ? 168 : 84) : 24} />
    </div>
    </TooltipProvider>
  );
}
