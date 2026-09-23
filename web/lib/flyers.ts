import { flyerState, type Flyer } from "./domain";

const timestamp = (value: string | null) => {
  const time = value ? Date.parse(value) : NaN;
  return Number.isFinite(time) ? time : 0;
};

export function organizeFlyers(flyers: Flyer[], now = new Date()) {
  const sorted = [...flyers].sort(
    (a, b) =>
      Number(flyerState(b, now) === "current") -
        Number(flyerState(a, now) === "current") ||
      (timestamp(b.valid_from) || timestamp(b.collected_at)) -
        (timestamp(a.valid_from) || timestamp(a.collected_at)) ||
      timestamp(b.collected_at) - timestamp(a.collected_at) ||
      a.id.localeCompare(b.id),
  );
  const groups: Record<"current" | "future" | "unknown" | "archived", Flyer[]> =
    {
      current: [],
      future: [],
      unknown: [],
      archived: [],
    };
  for (const flyer of sorted) {
    const state = flyerState(flyer, now);
    groups[state === "expired" ? "archived" : state].push(flyer);
  }
  return groups;
}

export function flyerPages(
  flyer: Flyer,
): { url: string; type: "image" | "pdf" }[] {
  if (flyer.media_pages?.length)
    return flyer.media_pages.map((url) => ({ url, type: "image" }));
  return flyer.media_url && flyer.media_type
    ? [{ url: flyer.media_url, type: flyer.media_type }]
    : [];
}

export function flyerCountdown(flyer: Flyer, now = new Date()) {
  const state = flyerState(flyer, now);
  if (state === "unknown") return "Validade a confirmar";
  if (state === "expired") return "Encerrado";
  const end = Date.parse(
    (state === "future" ? flyer.valid_from : flyer.valid_until)!,
  );
  const minutes = Math.max(1, Math.ceil((end - now.getTime()) / 60000));
  const days = Math.floor(minutes / 1440),
    hours = Math.floor((minutes % 1440) / 60);
  const time = days
    ? `${days}d ${hours}h`
    : hours
      ? `${hours}h ${minutes % 60}min`
      : `${minutes}min`;
  return `${state === "future" ? "Começa" : "Termina"} em ${time}`;
}

export const flyerStates = {
  current: "Dentro da validade",
  future: "Em breve",
  expired: "Vencido",
  unknown: "Validade não confirmada",
};

export function flyerDateRange(f: Flyer) {
  if (flyerState(f) === "unknown") return "Período a confirmar";
  const format = new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeZone: "America/Fortaleza",
  });
  return `${format.format(new Date(f.valid_from!))} a ${format.format(new Date(f.valid_until!))}`;
}

// The archive uses the start date in Fortaleza. Weeks are 1–7, 8–14, etc.
export function flyerPeriod(flyer: Flyer) {
  const date = new Date(
    timestamp(flyer.valid_from) || timestamp(flyer.collected_at),
  );
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Fortaleza",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const part = (type: string) => parts.find((p) => p.type === type)!.value;
  return {
    month: `${part("year")}-${part("month")}`,
    week: Math.ceil(Number(part("day")) / 7),
  };
}

export function flyerMonthLabel(month: string) {
  return new Intl.DateTimeFormat("pt-BR", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${month}-01T12:00:00Z`));
}

export function flyerWeekLabel(month: string, week: number) {
  const [year, number] = month.split("-").map(Number);
  const lastDay = new Date(Date.UTC(year, number, 0)).getUTCDate();
  return `Semana ${week} · ${(week - 1) * 7 + 1} a ${Math.min(week * 7, lastDay)}`;
}

export function flyerShareUrl(flyer: Flyer, origin: string) {
  return new URL(flyer.media_url || flyer.source_url, origin).href;
}
