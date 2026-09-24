import { useEffect, useMemo, useRef, useState } from "react";
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
  Check,
  Store,
  ChevronRight,
  X,
  Clock,
} from "lucide-react";
import {
  BRAND,
  money,
  rankOffers,
  isConditional,
  conditionLabel,
  unitPrice,
  localTime,
  basket,
  flyerState,
  clean,
  type Product,
  type Offer,
  type Flyer,
} from "@/lib/domain";
import { demoData } from "@/lib/demo";
import { FlyerBrowser, FlyerCard } from "@/components/flyers";
import { ProductCard } from "@/components/product-card";
import { ProductRangeCard } from "@/components/product-range-card";
import { groupBySize } from "@/lib/group";
import { OfferRail } from "@/components/offer-rail";
import { LoadMore, useIncremental } from "@/components/infinite";
import { ListAdder } from "@/components/list-adder";
import { StoreEstimates } from "@/components/store-estimates";
import { storeEstimates } from "@/lib/estimates";
import { buildIndex, filterIndexed } from "@/lib/search";
import { stockNote } from "@/lib/stock";
import { PriceInput } from "@/components/price-input";
import {
  activeFilterCount,
  alternativesOf,
  filterProducts,
  noFilters,
  productsWithPrice,
  type ProductFilters,
} from "@/lib/filters";
import { useDebounced } from "@/lib/use-debounced";
import { DealNote } from "@/components/deal-note";
import { StoreContact } from "@/components/store-contact";
import { StoreLocation } from "@/components/store-location";
import { OfferShare } from "@/components/offer-share";
import { organizeFlyers } from "@/lib/flyers";
import { NearbyFilter } from "@/components/nearby-filter";
import { dailyDeals } from "@/lib/deals";
import {
  filterNearby,
  readNearby,
  offerLocation,
  groupLocations,
  distanceLabel,
  FORTALEZA_CENTER,
  type LocationsByRetailer,
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
type Line = { product_id: string; name: string; quantity: number };
type View = "today" | "search" | "flyers" | "list";
const channelNames: Record<string, string> = {
  catalog: "Online",
  physical: "Loja física",
  flyer: "Encarte",
};
function Placeholder() {
  return (
    <div className="product-placeholder">
      <Package size={30} strokeWidth={1.2} />
      <span>Sem imagem</span>
    </div>
  );
}

export default function Market({ demo = false }: { demo?: boolean }) {
  const [view, setView] = useState<View>("today"),
    [query, setQuery] = useState(""),
    [pf, setPf] = useState<ProductFilters>(noFilters),
    [channel, setChannel] = useState(""),
    [category, setCategory] = useState(""),
    [conditions, setConditions] = useState(false),
    [old, setOld] = useState(false),
    [region, setRegion] = useState("Fortaleza"),
    [active, setActive] = useState<Product | null>(null),
    [lines, setLines] = useState<Line[]>([]),
    [loaded, setLoaded] = useState(false),
    [offline, setOffline] = useState(false),
    [toast, setToast] = useState(""),
    [filters, setFilters] = useState(false),
    [clock, setClock] = useState(0),
    [searching, setSearching] = useState(false);
  const networks = pf.networks;
  const [sharedTarget, setSharedTarget] = useState<{
    productId: string;
    offerId: string;
  } | null>(null);
  const [sharedNotice, setSharedNotice] = useState("");
  const [nearby, setNearby] = useState<Nearby | null>(null);
  const nearbyKey = "med-nearby-" + (demo ? "demo" : "real");
  const sharedOpened = useRef(false);
  const sharedScrolled = useRef(false);
  useEffect(() => {
    const timer = setInterval(() => setClock((v) => v + 1), 60000);
    return () => clearInterval(timer);
  }, []);
  const listKey = "med-list-" + (demo ? "demo" : "real");
  useEffect(() => {
    try {
      const l = JSON.parse(localStorage.getItem(listKey) || "[]");
      setLines(
        Array.isArray(l)
          ? l
              .filter(
                (x) =>
                  typeof x.product_id === "string" &&
                  Number.isInteger(x.quantity) &&
                  x.quantity > 0,
              )
              .slice(0, 200)
          : [],
      );
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
    const online = () => setOffline(!navigator.onLine);
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
    if (loaded)
      try {
        localStorage.setItem(listKey, JSON.stringify(lines));
      } catch {
        setToast("Não foi possível salvar a lista neste navegador.");
      }
  }, [lines, loaded, listKey]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 2800);
    return () => clearTimeout(t);
  }, [toast]);
  // The API sends one complete snapshot (cached by the browser, the edge and React Query), so search
  // and filters run here instead of asking the server for a new list on every keystroke.
  const search = useDebounced(query, 220);
  const dataRegion = region;
  const result = useQuery({
    queryKey: ["public", demo],
    queryFn: async ({ signal }): Promise<Data> => {
      if (demo) return demoData();
      const r = await fetch("/api/public", {
        signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => null);
        throw Error(body?.error || "Não foi possível atualizar.");
      }
      return r.json();
    },
  });
  const loading = result.isPending;
  // A failed refresh keeps showing the data that is already loaded.
  const error =
    result.isError && !result.data
      ? result.error instanceof Error
        ? result.error.message
        : "Não foi possível atualizar."
      : "";
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
      setSharedNotice("Produto compartilhado não encontrado.");
      return;
    }
    setActive(product);
    const offer = rankOffers(d.offers, true).find(
      (o) => o.product_id === product.id && o.id === sharedTarget.offerId,
    );
    if (offer) setConditions(isConditional(offer.conditions));
    else
      setSharedNotice(
        "Esta oferta não está disponível no momento. Veja as opções atuais.",
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
  function clearShared() {
    if (!sharedTarget) return;
    setSharedTarget(null);
    setSharedNotice("");
    sharedOpened.current = false;
    sharedScrolled.current = false;
    window.history.replaceState(window.history.state, "", demo ? "/demo" : "/");
  }
  const openProduct = (product: Product) => {
    clearShared();
    setActive(product);
  };
  const navigate = (v: View) => {
    clearShared();
    setView(v);
    setActive(null);
    setPf(noFilters);
    setChannel("");
    setCategory("");
    setQuery("");
  };
  const add = (p: Product) => {
    setLines((l) =>
      l.some((x) => x.product_id === p.id)
        ? l.map((x) =>
            x.product_id === p.id
              ? { ...x, quantity: Math.min(x.quantity + 1, 999) }
              : x,
          )
        : [
            ...l,
            {
              product_id: p.id,
              name: [p.name, p.brand, `${p.amount} ${p.unit}`].filter(Boolean).join(" · "),
              quantity: 1,
            },
          ],
    );
    setToast("Adicionado à sua lista");
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
  // This whole derived block is memoized: `data` only changes when the *debounced* `search`
  // (or the snapshot) changes, so between keystrokes these stay stable and the catalog isn't
  // re-filtered on every render — that was the source of the typing lag.
  const {
    products,
    filteredOffers,
    current,
    productOffers,
    shown,
    todayProducts,
    deal,
    offersByProduct,
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
    const current =
      offline || error ? [] : rankOffers(filteredOffers, conditions);
    const productOffers = filteredOffers.filter(
      (o) => o.product_id === active?.id,
    );
    const shown = products.filter((p) =>
      view === "today" ? current.some((o) => o.product_id === p.id) : true,
    );
    const deal =
      !offline && !error ? dailyDeals(shown, filteredOffers)[0] : undefined;
    const todayProducts = deal
      ? [deal.product, ...shown.filter((p) => p.id !== deal.product.id)]
      : shown;
    const offersByProduct = new Map<string, Offer[]>();
    for (const o of filteredOffers) {
      const list = offersByProduct.get(o.product_id);
      if (list) list.push(o);
      else offersByProduct.set(o.product_id, [o]);
    }
    return {
      products,
      filteredOffers,
      current,
      productOffers,
      shown,
      todayProducts,
      deal,
      offersByProduct,
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
  ]);
  const listResetKey = [
    view,
    search,
    JSON.stringify(pf),
    channel,
    category,
    conditions,
    nearby
      ? `${nearby.point.latitude},${nearby.point.longitude},${nearby.radiusKm}`
      : "",
    old,
  ].join("|");
  const rail = useIncremental(todayProducts.length, 12, listResetKey);
  // Memoized on the debounced `search` (via `shown`) so the filter over the whole catalog only
  // runs after typing pauses, not on every keystroke.
  const searchResults = useMemo(
    () =>
      view === "search"
        ? filterProducts(shown, offersByProduct, pf, {
            conditions,
            includeUnpriced: old,
            nearby: nearby?.point,
            locationsByRetailer,
          })
        : [],
    [view, shown, offersByProduct, pf, conditions, old, nearby, locationsByRetailer],
  );
  const hasConditional = offers.some((o) => isConditional(o.conditions));
  // Once the debounced search settles (new results are computed), clear the typing spinner.
  useEffect(() => {
    if (searching) setSearching(false);
  }, [searchResults, searching]);
  const hasUnpriced = shown.some((p) => !offersByProduct.get(p.id)?.length);
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
  // The whole catalog, not `products` above - that one is narrowed to whatever text is still sitting in
  // the search box (see the `data` memo's own note on why), which is exactly right for the search results
  // grid but wrong here: a product opened while "queijo" is still typed must still see every alternative,
  // not just the other ones whose name happens to contain "queijo".
  const allProducts = result.data?.products ?? [];
  const pricedIds = useMemo(() => {
    const ids = new Set<string>();
    for (const [id, os] of offersByProduct) if (rankOffers(os, conditions).length) ids.add(id);
    return ids;
  }, [offersByProduct, conditions]);
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
        (o) => offerLocation(o, locationsByRetailer, nearby.point) === null,
      ).length
    : 0;
  const activeQuantity =
    lines.find((l) => l.product_id === active?.id)?.quantity || 0;
  const showSearch = !active && (view === "today" || view === "search");
  const estimates = useMemo(
    () => (offline || error ? [] : storeEstimates(lines, offers, nearby, locationsByRetailer)),
    [lines, offers, offline, error, clock, nearby, locationsByRetailer],
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
  function SearchBox(className = "") {
    return (
      <form
        // Chrome iOS annotates forms/fields with __gCrUniqueID before React loads.
        suppressHydrationWarning
        className={`searchbar ${className}`}
        onSubmit={(e) => {
          e.preventDefault();
          setView("search");
          setActive(null);
          clearShared();
          window.scrollTo({ top: 0, behavior: "instant" });
        }}
      >
        <Search size={22} />
        <input
          suppressHydrationWarning
          aria-label="Buscar produtos"
          enterKeyHint="search"
          disabled={!loaded}
          placeholder="Buscar produtos"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setSearching(true);
            clearShared();
            setView("search");
            setActive(null);
          }}
        />
        <button type="submit">
          Buscar <span>→</span>
        </button>
      </form>
    );
  }
  return (
    <div className={`app-shell${showSearch ? " has-mobile-search" : ""}`}>
      {demo && (
        <div className="demo-banner">
          MODO DEMONSTRATIVO · dados fictícios{" "}
          <a href="/">Voltar aos dados reais</a>
        </div>
      )}
      <header className="header">
        <a className="brand" href={demo ? "/demo" : "/"}>
          <span className="brand-icon">
            <ShoppingBasket size={25} />
          </span>
          <span>
            {BRAND.name.split(" ")[0].toLowerCase()}
            <span className="brand-second">
              {BRAND.name.split(" ").slice(1).join(" ").toLowerCase()}
              <span className="brand-dot">.</span>
            </span>
          </span>
        </a>
        <nav className="desktop-nav" aria-label="Navegação principal">
          {[
            ["today", "Hoje"],
            ["search", "Buscar"],
            ["flyers", "Encartes"],
            ["list", "Minha lista"],
          ].map(([v, t]) => (
            <button
              key={v}
              className={view === v ? "selected" : ""}
              onClick={() => navigate(v as View)}
            >
              {t}
              {v === "list" && lines.length > 0 && (
                <span className="count">{lines.length}</span>
              )}
            </button>
          ))}
        </nav>
        <label className="region">
          <MapPin size={18} />
          <span className="sr-only">Região</span>
          <select
            suppressHydrationWarning
            value={region}
            onChange={(e) => {
              setRegion(e.target.value);
              setNearby(null);
              try {
                localStorage.setItem("med-region", e.target.value);
              } catch {}
            }}
          >
            {(data?.regions || ["Fortaleza"]).map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
          <span className="region-state">CE</span>
        </label>
      </header>
      <main className="main">
        {offline && (
          <div className="notice amber" role="status">
            <WifiOff size={19} />
            Sem conexão. Os preços não serão tratados como atuais.
          </div>
        )}
        {error && (
          <div className="notice amber" role="alert">
            {error}{" "}
            <button onClick={() => window.location.reload()}>
              Tentar novamente
            </button>
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
            <button
              className="back"
              onClick={() => {
                setActive(null);
                clearShared();
              }}
            >
              <ArrowLeft size={18} /> Voltar à busca
            </button>
            <div className="product-heading">
              <Placeholder />
              <div>
                <span className="eyebrow">{active.brand}</span>
                <h1>{active.name}</h1>
                <p>
                  {active.variant && `${active.variant} · `}{active.pack_count} embalagem ·{" "}
                  {active.amount} {active.unit}
                </p>
                <div className="product-list-actions">
                  <p className="product-list-status" aria-live="polite">
                    {activeQuantity > 0
                      ? `${activeQuantity} ${activeQuantity === 1 ? "unidade" : "unidades"} na sua lista`
                      : "Salve na lista para planejar suas quantidades."}
                  </p>
                  <div>
                    <button
                      className="primary"
                      disabled={activeQuantity >= 999}
                      onClick={() => add(active)}
                    >
                      <Plus size={18} />{" "}
                      {activeQuantity
                        ? "Adicionar mais 1"
                        : "Adicionar à lista"}
                    </button>
                    {activeQuantity > 0 && (
                      <button
                        className="text-link"
                        onClick={() => navigate("list")}
                      >
                        Ver minha lista <ChevronRight size={17} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
            <div className="section-heading">
              <div>
                <h2>Mesmo produto, preços encontrados</h2>
                <p>
                  Marca, variante e embalagem equivalentes.
                  {nearby
                    ? ` Lojas até ${nearby.radiusKm} km da sua referência.`
                    : ""}
                </p>
              </div>
            </div>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={conditions}
                onChange={(e) => setConditions(e.target.checked)}
              />
              Incluir clube, cupom e preços condicionados
            </label>
            <div className="comparison-list">
              {!offline &&
                !error &&
                rankedProductOffers.slice(0, comparison.count).map((o, i) => {
                  const up = unitPrice(active, o.price_cents!);
                  return (
                    <article
                      className={`offer-row${sharedTarget?.offerId === o.id ? " shared-offer" : ""}`}
                      id={`offer-${o.id}`}
                      key={o.id}
                    >
                      <div className="store-mark">
                        <Store size={23} />
                      </div>
                      <div className="offer-details">
                        {sharedTarget?.offerId === o.id && (
                          <span className="badge green">
                            Oferta compartilhada
                          </span>
                        )}
                        {i === 0 && (
                          <span className="eyebrow green-text">
                            Menor preço encontrado entre as ofertas monitoradas
                          </span>
                        )}
                        <h3>{o.retailer_name}</h3>
                        <p>
                          {o.context_label} · {channelNames[o.channel]}
                          {nearby &&
                            (() => {
                              const found = offerLocation(o, locationsByRetailer, nearby.point);
                              return found && ` · ${distanceLabel(found.distanceKm)}`;
                            })()}
                        </p>
                        <span
                          className={
                            "badge " +
                            (conditionLabel(o.conditions) ===
                            "Sem condição especial"
                              ? "green"
                              : "amber")
                          }
                        >
                          {conditionLabel(o.conditions)}
                        </span>
                        <p className="small">
                          {o.channel === "flyer"
                            ? "Preço anunciado no encarte"
                            : "Observado em"}{" "}
                          {localTime(o.price_observed_at)}
                          {o.valid_until &&
                            ` · válido até ${localTime(o.valid_until)}`}
                        </p>
                        <p className="small">
                          {o.availability === "available"
                            ? "Disponível na consulta da fonte"
                            : "Disponibilidade desconhecida"}
                          {stockNote(o) && ` · ${stockNote(o)}`}{" "}
                          ·{" "}
                          {o.method === "manual"
                            ? "Registro manual identificado"
                            : o.method === "demo"
                              ? "Dado fictício"
                              : "Coleta automática"}
                        </p>
                        {o.collection_error && (
                          <p className="small warning">
                            Última coleta falhou; a observação não foi renovada.
                          </p>
                        )}
                      </div>
                      <div className="offer-value">
                        <strong>{money(o.price_cents!)}</strong>
                        <DealNote offer={o} />
                        <span>
                          {money(up.value)}/{up.unit}
                        </span>
                        {demo ? (
                          <span className="small">
                            Origem: exemplo fictício
                          </span>
                        ) : (
                          <a
                            href={o.source_url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Ver origem <ArrowUpRight size={16} />
                          </a>
                        )}
                        <OfferShare
                          offer={o}
                          productName={active.name}
                          region={dataRegion}
                        />
                        <StoreLocation
                          offer={o}
                          productName={active.name}
                          region={dataRegion}
                          address={
                            offerLocation(o, locationsByRetailer, nearby?.point ?? FORTALEZA_CENTER)
                              ?.location.address ?? null
                          }
                        />
                      </div>
                    </article>
                  );
                })}
            </div>
            {comparison.hasMore && !offline && !error && (
              <>
                <LoadMore onVisible={comparison.more} />
                <p className="muted list-progress">
                  Mostrando {comparison.count.toLocaleString("pt-BR")} de{" "}
                  {rankedProductOffers.length.toLocaleString("pt-BR")} ofertas
                </p>
              </>
            )}
            {outsideOffers > 0 && !offline && !error && (
              <div className="nearby-outside">
                <p>
                  {outsideOffers}{" "}
                  {outsideOffers === 1
                    ? "outra opção está"
                    : "outras opções estão"}{" "}
                  fora deste filtro de localização.
                </p>
                <button className="text-link" onClick={() => setNearby(null)}>
                  Ver preços em todas as lojas <ChevronRight size={16} />
                </button>
              </div>
            )}
            {rankedProductOffers.length === 0 && (
              <div className="empty compact">
                <Clock />
                <h3>Sem oferta atual para este produto</h3>
                <p>Você pode mantê-lo na lista e consultar novamente depois.</p>
              </div>
            )}
            <h2 className="spaced">Alternativas</h2>
            <p className="muted">
              {active.subcategory
                ? `Outros produtos do tipo "${active.subcategory}". Não entram na comparação exata acima.`
                : "Produtos diferentes da mesma categoria. Não entram na comparação exata acima."}
            </p>
            {altProducts.length === 0 ? (
              <div className="empty compact">
                <Clock />
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
                      unavailable={Boolean(offline || error)}
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
                      <span className="eyebrow green-text">
                        SUAS COMPRAS EM FORTALEZA
                      </span>
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
                      <ShieldCheck size={22} />
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
                  Busque por produto, marca ou embalagem.
                </div>
                {view === "search" && (
                  <div
                    className={`category-row${filters ? " categories-expanded" : ""}`}
                  >
                    {[
                      "Todas",
                      ...(data?.categories.length
                        ? data.categories
                        : ["Mercearia", "Limpeza", "Bebidas", "Higiene"]),
                    ].map((c) => (
                      <button
                        key={c}
                        className={
                          category === c || (c === "Todas" && !category)
                            ? "active"
                            : ""
                        }
                        onClick={() => {
                          setCategory(c === "Todas" ? "" : c);
                          setView("search");
                        }}
                      >
                        {c === "Todas" && <SlidersHorizontal size={16} />} {c}
                      </button>
                    ))}
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
                    <p>Menores preços nas lojas consultadas.</p>
                  </div>
                  <button
                    className="text-link"
                    onClick={() => navigate("search")}
                  >
                    Comparar <ChevronRight size={17} />
                  </button>
                </div>
                {loading ? (
                  <div className="loading" role="status">
                    Consultando ofertas publicadas…
                  </div>
                ) : shown.length ? (
                  <OfferRail onEnd={rail.hasMore ? rail.more : undefined}>
                    {todayProducts.slice(0, rail.count).map((p) => (
                      <ProductCard
                        key={p.id}
                        p={p}
                        region={dataRegion}
                        nearby={nearby}
                        locationsByRetailer={locationsByRetailer}
                        deal={deal?.product.id === p.id ? deal : undefined}
                        offers={filteredOffers}
                        conditions={conditions}
                        unavailable={Boolean(offline || error)}
                        onOpen={openProduct}
                        onAdd={add}
                      />
                    ))}
                  </OfferRail>
                ) : nearby ? (
                  <div className="empty compact nearby-empty">
                    <MapPin size={30} />
                    <h3>Nenhuma oferta neste raio</h3>
                    <p>
                      Ainda não temos preços atuais de lojas até{" "}
                      {nearby.radiusKm} km dessa referência.
                    </p>
                    <button
                      className="secondary"
                      onClick={() => setNearby(null)}
                    >
                      Ver preços em todas as lojas
                    </button>
                  </div>
                ) : (
                  <div className="empty">
                    <span className="empty-icon">
                      <ShoppingBasket size={33} strokeWidth={1.3} />
                    </span>
                    <div>
                      <span className="eyebrow">
                        ESTAMOS CONFERINDO AS FONTES
                      </span>
                      <h3>
                        Uma boa comparação começa
                        <br className="desktop-break" /> com um preço confiável.
                      </h3>
                      <p>
                        Ainda não temos preços validados para comparar.
                        <br />
                        Enquanto isso, consulte os encartes oficiais e monte sua
                        lista.
                      </p>
                      <button
                        className="primary"
                        onClick={() => navigate("flyers")}
                      >
                        Consultar encartes <ArrowUpRight size={17} />
                      </button>
                    </div>
                  </div>
                )}
                {nearby && (
                  <p className="nearby-scope">
                    Distâncias em linha reta.{" "}
                    {unlocated > 0
                      ? `${unlocated} oferta(s) sem localização conferida ficaram fora do filtro.`
                      : "O raio considera o endereço da unidade; preços online podem variar na loja."}
                  </p>
                )}
                <div className="coverage">
                  <ShieldCheck size={20} />
                  <div>
                    <strong>
                      Cobertura de preços {demo ? "fictícios" : "validados"}
                    </strong>
                    <span>
                      {nearby
                        ? new Set(current.map((o) => o.retailer_id)).size
                        : data?.coverage.networks || 0}{" "}
                      redes ·{" "}
                      {nearby
                        ? new Set(current.map((o) => o.product_id)).size
                        : data?.coverage.products || 0}{" "}
                      produtos ·{" "}
                      {nearby ? current.length : data?.coverage.offers || 0}{" "}
                      ofertas atuais{nearby ? " neste raio" : ""}
                    </span>
                  </div>
                  <a href="#sources" className="text-link">
                    Ver fontes <ChevronRight size={17} />
                  </a>
                </div>
                <div className="section-heading">
                  <div>
                    <span className="eyebrow green-text">
                      DIRETO DOS SUPERMERCADOS
                    </span>
                    <h2>Encartes para consultar</h2>
                  </div>
                  <button
                    className="text-link"
                    onClick={() => navigate("flyers")}
                  >
                    Ver todos <ChevronRight size={17} />
                  </button>
                </div>
                <div className="flyer-grid">
                  {organizeFlyers(data?.flyers || [])
                    .current.slice(0, 3)
                    .map((f) => (
                      <FlyerCard key={f.id} f={f} />
                    ))}
                </div>
              </>
            )}
            {view === "search" && (
              <>
                <div className="section-heading">
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
                  <button
                    className="secondary"
                    onClick={() => setFilters(!filters)}
                  >
                    <SlidersHorizontal size={17} />
                    Filtros
                  </button>
                </div>
                {filters && (
                  <div className="filter-panel">
                    <fieldset className="filter-group">
                      <legend>Redes</legend>
                      <div className="chip-row">
                        {data?.retailers.map((r) => {
                          const on = pf.networks.includes(r.id);
                          return (
                            <label
                              key={r.id}
                              className={`chip-check${on ? " selected" : ""}`}
                            >
                              <input
                                type="checkbox"
                                checked={on}
                                onChange={() =>
                                  setPf((f) => ({
                                    ...f,
                                    networks: on
                                      ? f.networks.filter((x) => x !== r.id)
                                      : [...f.networks, r.id],
                                  }))
                                }
                              />
                              {r.name}
                            </label>
                          );
                        })}
                      </div>
                    </fieldset>
                    <label>
                      Desconto
                      <select
                        value={pf.minDiscount}
                        onChange={(e) =>
                          setPf((f) => ({
                            ...f,
                            minDiscount: Number(e.target.value),
                          }))
                        }
                      >
                        <option value={0}>Qualquer</option>
                        <option value={1}>Só com desconto</option>
                        <option value={10}>10% ou mais</option>
                        <option value={20}>20% ou mais</option>
                        <option value={30}>30% ou mais</option>
                        <option value={50}>50% ou mais</option>
                      </select>
                    </label>
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
                    <label>
                      Ordenar por
                      <select
                        value={pf.sort}
                        onChange={(e) =>
                          setPf((f) => ({
                            ...f,
                            sort: e.target.value as ProductFilters["sort"],
                          }))
                        }
                      >
                        <option value="discount-near">Maior desconto e mais perto</option>
                        <option value="discount">Maior desconto</option>
                        <option value="price-asc">Menor preço</option>
                        <option value="price-desc">Maior preço</option>
                        <option value="name">Nome (A a Z)</option>
                      </select>
                      {pf.sort === "discount-near" && !nearby && (
                        <small className="muted">
                          Defina seu local em &ldquo;Perto de você&rdquo; para considerar a distância; por
                          enquanto, só o desconto está ordenando.
                        </small>
                      )}
                    </label>
                    {hasConditional && (
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={conditions}
                          onChange={(e) => setConditions(e.target.checked)}
                        />
                        Incluir preços de clube e outras condições
                      </label>
                    )}
                    {hasUnpriced && (
                      <label className="checkbox">
                        <input
                          type="checkbox"
                          checked={old}
                          onChange={(e) => setOld(e.target.checked)}
                        />
                        Incluir produtos sem preço atual
                      </label>
                    )}
                    {(activeFilterCount(pf) > 0 || pf.sort !== "name") && (
                      <button
                        className="text-link clear-filters"
                        onClick={() => setPf(noFilters)}
                      >
                        Limpar filtros
                      </button>
                    )}
                  </div>
                )}
                {loading || searching ? (
                  <div role="status" className="loading">
                    {searching ? "Filtrando…" : "Buscando no catálogo…"}
                  </div>
                ) : (
                  <>
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
                          unavailable={Boolean(offline || error)}
                          onOpen={openProduct}
                          onAdd={add}
                        />
                      ),
                    )}
                  </div>
                  {grid.hasMore && (
                    <>
                      <LoadMore onVisible={grid.more} />
                      <p className="muted list-progress">
                        Mostrando {grid.count.toLocaleString("pt-BR")} de{" "}
                        {groupedSearchResults.length.toLocaleString("pt-BR")} produtos
                      </p>
                    </>
                  )}
                  </>
                )}
                {!loading && !searchResults.length && (
                    <div className="empty compact">
                      <Search size={30} />
                      <h3>
                        {nearby
                          ? "Nenhuma oferta neste raio"
                          : "Nenhum produto encontrado"}
                      </h3>
                      <p>
                        {nearby
                          ? `Não encontramos este produto em lojas até ${nearby.radiusKm} km da referência. Amplie a distância ou remova o filtro.`
                          : "Tente outro nome ou embalagem. A cobertura ainda está sendo validada."}
                      </p>
                      <button
                        className="secondary"
                        onClick={() => {
                          clearShared();
                          setQuery("");
                          setCategory("");
                          setPf(noFilters);
                          setChannel("");
                          setNearby(null);
                        }}
                      >
                        Limpar busca e filtros
                      </button>
                    </div>
                  )}
              </>
            )}
            {view === "flyers" && (
              <FlyerBrowser
                flyers={data?.flyers || []}
                retailers={data?.retailers || []}
              />
            )}
            {view === "list" && (
              <>
                <div className="page-title">
                  <span className="eyebrow green-text">
                    SEM CADASTRO, NO SEU DISPOSITIVO
                  </span>
                  <h1>Minha lista.</h1>
                  <p>
                    {lines.length} {lines.length === 1 ? "item" : "itens"} para
                    seu planejamento de preços.
                  </p>
                  <p className="list-purpose">
                    Aqui você consulta e compara preços. A compra é feita
                    diretamente com a loja.
                  </p>
                </div>
                <ListAdder
                  products={listProducts}
                  priceOf={(id) => priceIndex.get(id) ?? null}
                  onProduct={add}
                />
                {!lines.length && (
                  <div className="empty compact">
                    <ClipboardList size={32} />
                    <h3>Comece sua lista de consulta.</h3>
                    <p>
                      Adicione um item acima ou escolha um produto na busca.
                    </p>
                  </div>
                )}
                {!loading && !offline && !error && lines.some((l) => !priceIndex.has(l.product_id)) && (
                  <div className="notice">
                    {lines.filter((l) => !priceIndex.has(l.product_id)).length === 1
                      ? "1 item da lista não tem preço atual e não entra no cálculo."
                      : `${lines.filter((l) => !priceIndex.has(l.product_id)).length} itens da lista não têm preço atual e não entram no cálculo.`}{" "}
                    <button
                      className="text-link"
                      onClick={() =>
                        setLines((l) => l.filter((x) => priceIndex.has(x.product_id)))
                      }
                    >
                      Remover esses itens
                    </button>
                  </div>
                )}
                <div className="shopping-list">
                  {lines.map((l) => {
                    const o =
                      offline || error
                        ? null
                        : rankOffers(
                            offers.filter((o) => o.product_id === l.product_id),
                          )[0];
                    // Same per-kg/L/unit price shown everywhere else a price appears (search cards, the
                    // range-card modal, the detail comparison list) - suppressed the same way too, when
                    // the pack is already exactly one kg/L/unit and it would just repeat the price.
                    const product = data?.products.find((p) => p.id === l.product_id);
                    const up = o && product ? unitPrice(product, o.price_cents!) : null;
                    return (
                      <article className="list-item" key={l.product_id}>
                        <div className="list-product">
                          <Package size={23} />
                          <div>
                            <h3>{l.name}</h3>
                            <p>
                              {o
                                ? `Referência: ${money(o.price_cents!)}${up && up.value !== o.price_cents ? ` (${money(up.value)}/${up.unit})` : ""} por embalagem · ${o.retailer_name}`
                                : `Sem preço atual nas lojas consultadas${nearby ? " neste raio" : ""}`}
                            </p>
                            {o && (
                              <StoreContact
                                offer={o}
                                address={
                                  offerLocation(o, locationsByRetailer, nearby?.point ?? FORTALEZA_CENTER)
                                    ?.location.address ?? null
                                }
                              />
                            )}
                          </div>
                        </div>
                        <div className="list-quantity">
                          <p>Quantidade para planejar</p>
                          <div className="quantity">
                            <button
                              aria-label={`Diminuir ${l.name}`}
                              disabled={l.quantity <= 1}
                              onClick={() =>
                                setLines((a) =>
                                  a.map((x) =>
                                    x.product_id === l.product_id
                                      ? { ...x, quantity: x.quantity - 1 }
                                      : x,
                                  ),
                                )
                              }
                            >
                              <Minus size={16} />
                            </button>
                            <span>{l.quantity}</span>
                            <button
                              aria-label={`Aumentar ${l.name}`}
                              disabled={l.quantity >= 999}
                              onClick={() =>
                                setLines((a) =>
                                  a.map((x) =>
                                    x.product_id === l.product_id
                                      ? {
                                          ...x,
                                          quantity: Math.min(
                                            999,
                                            x.quantity + 1,
                                          ),
                                        }
                                      : x,
                                  ),
                                )
                              }
                            >
                              <Plus size={16} />
                            </button>
                          </div>
                        </div>
                        <button
                          className="icon-button"
                          aria-label={`Remover ${l.name}`}
                          onClick={() =>
                            setLines((a) =>
                              a.filter((x) => x.product_id !== l.product_id),
                            )
                          }
                        >
                          <X size={19} />
                        </button>
                      </article>
                    );
                  })}
                </div>
                {lines.length > 0 && (
                  <>
                    <h2 className="spaced">Estimativa por loja</h2>
                    <p className="muted">
                      Compare a cobertura de cada estimativa. Listas incompletas
                      não são classificadas como mais baratas.
                    </p>
                    <StoreEstimates
                      estimates={estimates}
                      lines={lines}
                      hasReference={Boolean(nearby)}
                    />
                    {!estimates.length && (
                      <div className="notice">
                        Ainda não há preços atuais para calcular sua lista.
                      </div>
                    )}
                    <p className="fineprint">
                      Sem frete ou deslocamento. Itens com clube, cupom ou
                      quantidade mínima não entram no subtotal padrão.
                    </p>
                  </>
                )}
              </>
            )}
            {view === "today" && (
              <section id="sources" className="sources">
                <div className="section-heading">
                  <h2>Transparência nas fontes</h2>
                  <span className="badge">Piloto</span>
                </div>
                <p className="muted">
                  Uma rede listada aqui não significa que seus preços já estão
                  sendo monitorados.
                </p>
                {data?.retailers.map((r) => (
                  <div key={r.id} className="source-row">
                    <Store size={19} />
                    <div>
                      <strong>{r.name}</strong>
                      <span>
                        {r.last_error
                          ? "Fonte temporariamente indisponível"
                          : r.audit_status}
                      </span>
                    </div>
                    <a
                      href={r.official_url}
                      aria-label={`Site oficial ${r.name}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <ArrowUpRight size={20} />
                    </a>
                  </div>
                ))}
              </section>
            )}
          </>
        )}
        <footer>
          <span>
            {BRAND.name.toLowerCase()}.{" "}
            <span className="muted">{BRAND.city}, CE</span>
          </span>
          <a href="/admin">Administração</a>
        </footer>
      </main>
      <div className="mobile-dock">
        {showSearch && <div className="mobile-search">{SearchBox()}</div>}
        <nav className="bottom-nav" aria-label="Navegação mobile">
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
            >
              <Icon size={22} />
              <span>{t}</span>
              {v === "list" && lines.length > 0 && <b>{lines.length}</b>}
            </button>
          ))}
        </nav>
      </div>
      {toast && (
        <div className="toast" role="status">
          <Check size={19} />
          {toast}
        </div>
      )}
    </div>
  );
}
