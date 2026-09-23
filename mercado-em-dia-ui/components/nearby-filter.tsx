import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, LocateFixed, MapPin, Search, X } from "lucide-react";
import {
  radii,
  validCoordinates,
  type LocationPoint,
  type Nearby,
} from "@/lib/location";
import type { AddressResult } from "@/lib/geocoding";

/** The street address at a GPS position, or null when it cannot be found (the position is rounded first). */
async function addressAt(latitude: number, longitude: number): Promise<string | null> {
  try {
    const params = new URLSearchParams({
      lat: latitude.toFixed(4),
      lon: longitude.toFixed(4),
    });
    const response = await fetch("/api/location/reverse?" + params, {
      signal: AbortSignal.timeout(6000),
    });
    if (!response.ok) return null;
    const data = await response.json();
    return typeof data?.place?.label === "string" ? data.place.label : null;
  } catch {
    return null;
  }
}

export function NearbyFilter({
  value,
  onChange,
  demo,
}: {
  value: Nearby | null;
  onChange: (value: Nearby | null) => void;
  demo: boolean;
}) {
  const id = useId();
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const sequence = useRef(0);
  const request = useRef<AbortController | null>(null);
  const [opened, setOpened] = useState(false);
  const [radius, setRadius] = useState(value?.radiusKm || 5);
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState<AddressResult[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<"address" | "device" | "lookup" | null>(null);
  // True from the moment an address is long enough to search until its suggestions arrive, including the
  // short wait after the last key, so the box below the field never looks idle while a search is coming.
  const [searching, setSearching] = useState(false);
  useEffect(() => {
    if (!opened) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [opened]);
  useEffect(
    () => () => {
      sequence.current++;
      request.current?.abort();
    },
    [],
  );
  function cancelPending() {
    sequence.current++;
    request.current?.abort();
    setBusy(null);
    setSearching(false);
  }
  function close() {
    cancelPending();
    dialog.current?.close();
    setOpened(false);
    trigger.current?.focus({ preventScroll: true });
  }
  function open() {
    setRadius(value?.radiusKm || 5);
    setQuery("");
    setPlaces([]);
    setMessage("");
    dialog.current?.showModal();
    setOpened(true);
  }
  function apply(point: LocationPoint) {
    onChange({ point, radiusKm: radius });
    close();
  }
  // `auto` is the search-as-you-type call: it keeps the suggestions on screen and leaves the form enabled.
  async function search(auto = false) {
    cancelPending();
    const token = sequence.current;
    const abort = new AbortController();
    request.current = abort;
    if (!auto) setPlaces([]);
    setMessage("");
    setSearching(true);
    if (!auto) setBusy("address");
    const timer = setTimeout(() => abort.abort(), 15000);
    try {
      const response = await fetch("/api/location", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
        signal: abort.signal,
        cache: "no-store",
      });
      const data = await response.json();
      if (token !== sequence.current) return;
      if (!response.ok)
        throw Error(data.error || "Não foi possível buscar o endereço.");
      const results = Array.isArray(data.places)
        ? data.places.filter(
            (p: AddressResult) =>
              p &&
              typeof p.id === "string" &&
              typeof p.label === "string" &&
              validCoordinates(p),
          )
        : [];
      setPlaces(results);
      if (!results.length)
        setMessage(
          "Não encontramos esse endereço em Fortaleza. Tente o nome da rua com o número, ou um bairro.",
        );
    } catch (error) {
      if (token !== sequence.current) return;
      setMessage(
        abort.signal.aborted
          ? "A busca demorou mais que o esperado. Tente novamente."
          : error instanceof Error
            ? error.message
            : "Busca de endereço indisponível.",
      );
    } finally {
      clearTimeout(timer);
      if (token === sequence.current) {
        setSearching(false);
        if (!auto) setBusy(null);
      }
    }
  }
  // Suggestions appear as the address is typed, a moment after the last key.
  useEffect(() => {
    if (!opened || query.trim().length < 3) return;
    setSearching(true);
    const timer = setTimeout(() => void search(true), 350);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, opened]);
  function locate() {
    cancelPending();
    setMessage("");
    setPlaces([]);
    if (!window.isSecureContext) {
      setMessage(
        "O GPS exige uma conexão segura (HTTPS). Neste link local do Wi-Fi, digite seu endereço ou bairro abaixo.",
      );
      return;
    }
    if (!navigator.geolocation) {
      setMessage(
        "Seu navegador não oferece localização. Digite seu endereço ou bairro abaixo.",
      );
      return;
    }
    const token = sequence.current;
    setBusy("device");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (token !== sequence.current) return;
        const { latitude, longitude, accuracy } = position.coords;
        if (
          !validCoordinates({ latitude, longitude }) ||
          !Number.isFinite(accuracy) ||
          accuracy > 2000
        ) {
          setBusy(null);
          setMessage(
            "A localização recebida está pouco precisa. Digite um endereço ou bairro para encontrar lojas próximas.",
          );
          return;
        }
        // Show where you are as a street address; "Minha localização" only if none is found.
        setBusy("lookup");
        void addressAt(latitude, longitude).then((label) => {
          if (token !== sequence.current) return;
          setBusy(null);
          apply({
            latitude,
            longitude,
            accuracy,
            label: label ?? "Minha localização",
            source: "device",
          });
        });
      },
      (error) => {
        if (token !== sequence.current) return;
        setBusy(null);
        setMessage(
          error.code === 1
            ? "Localização não autorizada. Você pode digitar seu endereço ou bairro abaixo."
            : error.code === 3
              ? "A localização demorou mais que o esperado. Tente novamente ou digite seu endereço."
              : "Não foi possível obter sua localização. Digite seu endereço ou bairro abaixo.",
        );
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    );
  }
  return (
    <>
      <div className={`nearby-bar${value ? " nearby-active" : ""}`}>
        <button
          ref={trigger}
          className="nearby-trigger"
          onClick={open}
          aria-label={
            value
              ? `Alterar localização: ${value.point.label}, até ${value.radiusKm} km`
              : "Filtrar por endereço"
          }
          aria-haspopup="dialog"
          title={value?.point.label}
        >
          <MapPin size={19} />
          <span>{value ? value.point.label : "Perto de você"}</span>
          <small>{value ? `Até ${value.radiusKm} km` : "Definir local"}</small>
          <ChevronDown size={15} />
        </button>
        {value && (
          <button
            className="nearby-clear"
            aria-label="Remover filtro de localização"
            onClick={() => onChange(null)}
          >
            <X size={18} />
          </button>
        )}
      </div>
      <dialog
        className="nearby-dialog"
        ref={dialog}
        aria-labelledby={`${id}-title`}
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
        onClick={(event) => {
          if (event.target === dialog.current) close();
        }}
      >
        <div className="nearby-dialog-content">
          <div className="nearby-dialog-heading">
            <div>
              <span className="eyebrow green-text">LOJAS MAIS PRÓXIMAS</span>
              <h2 id={`${id}-title`}>De onde você quer comparar?</h2>
            </div>
            <button
              className="icon-button"
              onClick={close}
              aria-label="Fechar localização"
            >
              <X size={21} />
            </button>
          </div>
          <p>
            Escolha uma referência em Fortaleza. As distâncias são aproximadas,
            em linha reta.
          </p>
          {demo && (
            <p className="nearby-demo">
              Demonstração: as posições das lojas e os preços são fictícios.
            </p>
          )}
          {value && (
            <p className="nearby-current">Referência: {value.point.label}</p>
          )}
          <fieldset className="nearby-radius" disabled={busy !== null}>
            <legend>Mostrar lojas até</legend>
            {radii.map((r) => (
              <label key={r} className={radius === r ? "selected" : ""}>
                <input
                  type="radio"
                  name={`${id}-radius`}
                  value={r}
                  checked={radius === r}
                  onChange={() => setRadius(r)}
                  // With a reference already set, choosing a distance applies it right away. A click
                  // (detail > 0) also closes the dialog; arrowing through the options (detail 0) does not.
                  onClick={(event) => {
                    if (!value) return;
                    onChange({ point: value.point, radiusKm: r });
                    if (event.detail > 0) close();
                  }}
                />
                {r} km
              </label>
            ))}
          </fieldset>
          <button
            className="secondary nearby-device"
            disabled={busy !== null}
            onClick={locate}
          >
            <LocateFixed size={19} />
            {busy === "device"
              ? "Obtendo localização…"
              : busy === "lookup"
                ? "Buscando seu endereço…"
                : "Usar minha localização"}
          </button>
          <div className="nearby-divider">ou informe um endereço</div>
          <form
            // Preserve Chrome iOS autofill metadata added before hydration.
            suppressHydrationWarning
            onSubmit={(event) => {
              event.preventDefault();
              void search();
            }}
          >
            <label htmlFor={`${id}-query`}>
              Endereço ou bairro em Fortaleza
            </label>
            <input
              suppressHydrationWarning
              id={`${id}-query`}
              value={query}
              type="search"
              minLength={3}
              maxLength={120}
              required
              placeholder="Ex.: Rua Coronel Alexandrino, 405"
              autoComplete="off"
              enterKeyHint="search"
              onChange={(event) => {
                cancelPending();
                setQuery(event.target.value);
                setMessage("");
                if (event.target.value.trim().length < 3) setPlaces([]);
              }}
            />
            {/* A fixed-height box right under the field: loading, results, "none found" and hints all
                fill the same space, so the dialog never changes height while you type. */}
            <div
              className="nearby-suggestions"
              aria-live="polite"
              aria-busy={searching}
            >
              <div className="nearby-suggestions-head">
                <span>Sugestões de endereço</span>
                {searching && (
                  <span className="nearby-searching">
                    <span className="nearby-spinner" aria-hidden="true" />
                    Buscando…
                  </span>
                )}
              </div>
              <div className="nearby-suggestions-body">
                {message ? (
                  <p className="nearby-message" role="status">
                    {message}
                  </p>
                ) : places.length > 0 ? (
                  // Kept on screen (dimmed) while the next search runs, instead of flashing empty.
                  <ul className={searching ? "nearby-stale" : undefined}>
                    {places.map((place) => (
                      <li key={place.id}>
                        <button
                          type="button"
                          onClick={() =>
                            apply({
                              latitude: place.latitude,
                              longitude: place.longitude,
                              label: place.label,
                              source: "manual",
                            })
                          }
                        >
                          <MapPin size={18} />
                          <span>{place.label}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : searching ? (
                  <div className="nearby-skeleton" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </div>
                ) : (
                  <p className="nearby-hint">
                    Digite o nome da rua e o número, ou um bairro. As sugestões
                    aparecem aqui.
                  </p>
                )}
              </div>
            </div>
            <button
              type="submit"
              className="primary"
              disabled={busy !== null || query.trim().length < 3}
            >
              <Search size={17} />
              {busy === "address" ? "Buscando endereço…" : "Buscar endereço"}
            </button>
            <p className="nearby-privacy">
              O texto digitado é enviado ao Photon/OpenStreetMap para sugerir
              endereços. Ao usar o GPS, suas coordenadas (arredondadas) também
              são enviadas, só para mostrar o seu endereço; nada é guardado por
              nós e a posição fica neste navegador, durante a sessão.
            </p>
          </form>
          <p className="nearby-attribution">
            Endereços:{" "}
            <a
              href="https://www.openstreetmap.org/copyright"
              target="_blank"
              rel="noreferrer"
            >
              © OpenStreetMap
            </a>{" "}
            ·{" "}
            <a href="https://photon.komoot.io" target="_blank" rel="noreferrer">
              Photon
            </a>
          </p>
        </div>
      </dialog>
    </>
  );
}
