import { demoFlyerUrl } from "@/lib/demo-flyer";
import { ordinary, type Product, type Offer, type Flyer } from "./domain";
// Fictional fixtures. Only served by /demo when explicitly enabled outside production.
export function demoData() {
  const stamp = new Date().toISOString();
  const products: Product[] = [
    {
      id: "demo-cafe",
      name: "Café torrado e moído",
      brand: "Marca Exemplo",
      category: "Mercearia",
      subcategory: "Café",
      variant: "Tradicional",
      amount: 250,
      unit: "g",
      pack_count: 1,
      gtin: null,
      gtin_evidence: null,
    },
    {
      id: "demo-arroz",
      name: "Arroz branco",
      brand: "Marca Exemplo",
      category: "Mercearia",
      subcategory: "Arroz",
      variant: "Tipo 1",
      amount: 1000,
      unit: "g",
      pack_count: 1,
      gtin: null,
      gtin_evidence: null,
    },
    {
      id: "demo-detergente",
      name: "Detergente líquido",
      brand: "Marca Exemplo",
      category: "Limpeza",
      subcategory: "Detergente",
      variant: "Neutro",
      amount: 500,
      unit: "ml",
      pack_count: 1,
      gtin: null,
      gtin_evidence: null,
    },
  ];
  const base = {
    currency: "BRL",
    conditions: ordinary(),
    availability: "unknown" as const,
    price_observed_at: stamp,
    source_checked_at: stamp,
    valid_from: null,
    valid_until: null,
    collected_at: stamp,
    source_url: "https://example.com",
    method: "demo" as const,
    published: 1,
    ttl_hours: 24,
    channel: "catalog" as const,
  };
  const offers: Offer[] = [
    {
      ...base,
      id: "d1",
      product_id: "demo-cafe",
      retailer_id: "demo-a",
      retailer_name: "Mercado Exemplo A",
      context_id: "da",
      context_label: "Loja fictícia A · Fortaleza",
      price_cents: 1590,
    },
    {
      ...base,
      id: "d2",
      product_id: "demo-cafe",
      retailer_id: "demo-b",
      retailer_name: "Mercado Exemplo B",
      context_id: "db",
      context_label: "Loja fictícia B · Fortaleza",
      price_cents: 1749,
    },
    {
      ...base,
      id: "d3",
      product_id: "demo-cafe",
      retailer_id: "demo-b",
      retailer_name: "Mercado Exemplo B",
      context_id: "db",
      context_label: "Loja fictícia B · Fortaleza",
      price_cents: 1290,
      conditions: { ...ordinary(), club: "Exemplo" },
    },
    {
      ...base,
      id: "d4",
      product_id: "demo-arroz",
      retailer_id: "demo-a",
      retailer_name: "Mercado Exemplo A",
      context_id: "da",
      context_label: "Loja fictícia A · Fortaleza",
      price_cents: 690,
    },
    {
      ...base,
      id: "d5",
      product_id: "demo-detergente",
      retailer_id: "demo-b",
      retailer_name: "Mercado Exemplo B",
      context_id: "db",
      context_label: "Loja fictícia B · Fortaleza",
      price_cents: 229,
      price_observed_at: new Date(Date.now() - 48 * 3600000).toISOString(),
    },
  ];
  return {
    products,
    offers: offers.map((o) => ({ ...o, store_phone: "(85) 0000-0000" })),
    flyers: demoFlyers(),
    // Fictional branches, isolated from the real store contexts/database - one each, so the demo still
    // exercises the same nearest-branch code path as the real data (see lib/location.ts's offerLocation).
    retailer_locations: [
      {
        id: "demo-loc-a", retailer_id: "demo-a", name: "Loja fictícia A",
        address: "Rua de Exemplo, 100 · Fortaleza (endereço fictício)",
        latitude: -3.744, longitude: -38.526,
      },
      {
        id: "demo-loc-b", retailer_id: "demo-b", name: "Loja fictícia B",
        address: "Rua de Exemplo, 200 · Fortaleza (endereço fictício)",
        latitude: -3.764, longitude: -38.554,
      },
    ],
    retailers: [
      {
        id: "demo-a",
        name: "Mercado Exemplo A",
        official_url: "https://example.com",
        audit_status: "Fictício",
        enabled: 0,
        last_error: null,
      },
      {
        id: "demo-b",
        name: "Mercado Exemplo B",
        official_url: "https://example.com",
        audit_status: "Fictício",
        enabled: 0,
        last_error: null,
      },
    ],
    regions: ["Fortaleza"],
    categories: ["Mercearia", "Limpeza"],
    coverage: { networks: 2, products: 3, offers: 3, exact_pairs: 1 },
    generated_at: stamp,
  };
}

export function demoFlyers(now = new Date()): Flyer[] {
  const day = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Fortaleza",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  const start = new Date(`${day}T03:00:00Z`).getTime();
  const at = (offset: number) =>
    new Date(start + offset * 86400000).toISOString();
  return [
    {
      id: "demo-a-atual",
      retailer: "A",
      title: "Seleção da semana",
      from: -1,
      until: 6,
    },
    {
      id: "demo-b-atual",
      retailer: "B",
      title: "Preços para consultar",
      from: -2,
      until: 5,
    },
    {
      id: "demo-a-anterior",
      retailer: "A",
      title: "Edição anterior",
      from: -8,
      until: -1,
    },
    {
      id: "demo-a-mes-anterior",
      retailer: "A",
      title: "Edição do mês anterior",
      from: -35,
      until: -28,
    },
    {
      id: "demo-b-anterior",
      retailer: "B",
      title: "Edição anterior",
      from: -9,
      until: -2,
    },
  ].map((f) => {
    const flyer = {
      id: f.id,
      retailer_id: `demo-${f.retailer.toLowerCase()}`,
      retailer_name: `Mercado Exemplo ${f.retailer}`,
      title: f.title,
      valid_from: at(f.from),
      valid_until: at(f.until),
    };
    const pages = [demoFlyerUrl(flyer, 1), demoFlyerUrl(flyer, 2)];
    return {
      ...flyer,
      source_url: pages[0],
      media_url: pages[0],
      media_type: "image",
      media_pages: pages,
      scope:
      "Encarte fictício para experimentar o wireframe. Não representa ofertas de uma loja real.",
      version_hash: f.id,
      collected_at: at(f.from),
      source_checked_at: null,
      method: "demo",
      status: "demo",
      published: 1,
    };
  });
}
