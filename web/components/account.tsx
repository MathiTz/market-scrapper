import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ClipboardList,
  LocateFixed,
  LogOut,
  MapPin,
  Search,
  ShieldCheck,
  ShoppingBasket,
  UserRound,
} from "lucide-react";
import {
  ACCOUNT_QUERY_KEY,
  accountApi,
  useAccount,
  type Credentials,
} from "@/lib/account-api";
import {
  accountDate,
  displayName,
  emailProblem,
  passwordProblem,
  type Preferences,
  type Session,
} from "@/lib/account";
import { addressAt, searchPlaces, type AddressResult } from "@/lib/geocoding";
import { radii, validCoordinates } from "@/lib/location";
import { BRAND } from "@/lib/domain";
import { notify } from "@/lib/notify";
import { SavedLists } from "@/components/saved-lists";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";

/** The `?entrou=` / `?erro=` the Google callback comes back with, as a message for the page. */
function queryNotice(): { text: string; ok: boolean } {
  const params = new URLSearchParams(window.location.search);
  const error = params.get("erro");
  if (error === "google-estado") return { text: "A entrada com o Google expirou antes de terminar. Tente de novo.", ok: false };
  if (error === "google-cancelado") return { text: "A entrada com o Google foi cancelada.", ok: false };
  if (error === "google-indisponivel") return { text: "Entrar com o Google não está configurado neste servidor.", ok: false };
  if (error === "google-token" || error === "google-conta")
    return { text: "Não foi possível entrar com o Google agora. Tente de novo ou use seu e-mail e senha.", ok: false };
  if (params.get("entrou") === "google") return { text: "Você entrou com o Google.", ok: true };
  return { text: "", ok: false };
}

function Brand() {
  const [first, ...rest] = BRAND.name.split(" ");
  return (
    <a className="brand" href="/">
      <span className="brand-icon">
        <ShoppingBasket size={25} aria-hidden="true" />
      </span>
      <span>
        {first.toLowerCase()}
        <span className="brand-second">
          {rest.join(" ").toLowerCase()}
          <span className="brand-dot">.</span>
        </span>
      </span>
    </a>
  );
}

export default function Account() {
  const session = useAccount();
  const [notice, setNotice] = useState(queryNotice);
  useEffect(() => {
    if (!notice.text) return;
    // The message is kept while the page is open; the address bar goes back to a clean /conta.
    window.history.replaceState({}, "", "/conta");
  }, [notice]);

  return (
    <div className="account-shell">
      <header className="account-header">
        <Brand />
        <a className="account-back" href="/">
          <ArrowLeft size={17} aria-hidden="true" /> Voltar às ofertas
        </a>
      </header>
      <main className="account-main">
        {notice.text && (
          <p className={notice.ok ? "notice" : "notice amber"} role={notice.ok ? "status" : "alert"}>
            <ShieldCheck size={19} aria-hidden="true" />
            <span>{notice.text}</span>
          </p>
        )}
        {session.isPending ? (
          <p className="account-loading" role="status">
            Carregando sua conta…
          </p>
        ) : session.isError ? (
          <div className="account-loading" role="alert">
            <p>Não foi possível consultar sua conta agora.</p>
            <Button variant="secondary" onClick={() => void session.refetch()}>
              Tentar novamente
            </Button>
          </div>
        ) : session.data?.user ? (
          <SignedIn session={session.data} onNotice={setNotice} />
        ) : (
          <SignIn google={Boolean(session.data?.google)} onSignedIn={() => setNotice({ text: "", ok: false })} />
        )}
        <p className="account-privacy">
          <ShieldCheck size={16} aria-hidden="true" />
          <span>
            Sua senha é guardada apenas como um hash. Suas listas e o local preferido ficam na sua conta e
            podem ser removidos a qualquer momento; sem conta, tudo continua só neste navegador.
          </span>
        </p>
      </main>
    </div>
  );
}

/* --------------------------------------------------------------------------------------------- */
/* Signed out                                                                                     */
/* --------------------------------------------------------------------------------------------- */

function SignIn({ google, onSignedIn }: { google: boolean; onSignedIn: () => void }) {
  const client = useQueryClient();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [touched, setTouched] = useState<{ email: boolean; password: boolean }>({ email: false, password: false });

  const emailIssue = emailProblem(email);
  const passwordIssue = passwordProblem(password);

  const enter = useMutation({
    mutationFn: (credentials: Credentials) =>
      mode === "login" ? accountApi.login(credentials) : accountApi.register(credentials),
    onSuccess: (data) => {
      client.setQueryData(ACCOUNT_QUERY_KEY, {
        user: data.user,
        preferences: data.preferences,
        google,
      } satisfies Session);
      onSignedIn();
    },
    onError: (failure: Error) => setError(failure.message),
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setTouched({ email: true, password: true });
    const problem = emailIssue || passwordIssue;
    if (problem) {
      setError(problem);
      return;
    }
    setError("");
    enter.mutate({ email: email.trim(), password, ...(mode === "register" ? { name: name.trim() || undefined } : {}) });
  }

  return (
    <div className="account-guest">
      <div className="account-guest-copy">
        <p className="overline">Área do usuário</p>
        <h1>Sua conta no Mercado em Dia.</h1>
        <p>
          Guarde suas listas de compras e o lugar de onde você compara preços. A busca e os preços
          continuam abertos sem cadastro.
        </p>
        <ul>
          <li>
            <ClipboardList size={18} aria-hidden="true" /> Listas salvas que abrem em qualquer aparelho.
          </li>
          <li>
            <MapPin size={18} aria-hidden="true" /> Seu local preferido já aplicado em “Perto de você”.
          </li>
          <li>
            <ShieldCheck size={18} aria-hidden="true" /> Nada de propaganda: a conta serve só para isso.
          </li>
        </ul>
      </div>

      <div className="account-form-card">
        <div className="account-tabs" role="tablist" aria-label="Entrar ou criar conta">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            className={mode === "login" ? "selected" : ""}
            onClick={() => {
              setMode("login");
              setError("");
            }}
          >
            Entrar
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            className={mode === "register" ? "selected" : ""}
            onClick={() => {
              setMode("register");
              setError("");
            }}
          >
            Criar conta
          </button>
        </div>

        <h2>{mode === "login" ? "Entrar na sua conta" : "Criar uma conta"}</h2>
        <form onSubmit={submit} noValidate>
          {mode === "register" && (
            <TextField
              label="Nome (opcional)"
              value={name}
              maxLength={80}
              autoComplete="name"
              onChange={(event) => setName(event.target.value)}
            />
          )}
          <TextField
            label="E-mail"
            type="email"
            value={email}
            autoComplete="email"
            inputMode="email"
            placeholder="nome@exemplo.com"
            required
            invalid={touched.email && Boolean(emailIssue)}
            hint={touched.email ? (emailIssue ?? undefined) : undefined}
            onChange={(event) => {
              setEmail(event.target.value);
              setError("");
            }}
            onBlur={() => setTouched((current) => ({ ...current, email: true }))}
          />
          <TextField
            label="Senha"
            type="password"
            value={password}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
            placeholder={mode === "login" ? "Sua senha" : "Pelo menos 8 caracteres"}
            required
            minLength={8}
            maxLength={200}
            invalid={touched.password && Boolean(passwordIssue)}
            hint={
              mode === "register"
                ? (touched.password && passwordIssue) || "Pelo menos 8 caracteres."
                : touched.password
                  ? (passwordIssue ?? undefined)
                  : undefined
            }
            onChange={(event) => {
              setPassword(event.target.value);
              setError("");
            }}
            onBlur={() => setTouched((current) => ({ ...current, password: true }))}
          />
          {error && (
            <p className="account-error" role="alert">
              {error}
            </p>
          )}
          <Button
            type="submit"
            variant="primary"
            loading={enter.isPending}
            icon={<UserRound size={18} aria-hidden="true" />}
          >
            {enter.isPending ? "Entrando…" : mode === "login" ? "Entrar" : "Criar conta"}
          </Button>
        </form>

        {google && (
          <>
            <div className="account-divider">ou</div>
            <a className="btn btn-secondary btn-md account-google" href="/api/auth/google/start">
              <span className="btn-label">Continuar com o Google</span>
            </a>
          </>
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------------------------------------- */
/* Signed in                                                                                      */
/* --------------------------------------------------------------------------------------------- */

function SignedIn({ session, onNotice }: { session: Session; onNotice: (notice: { text: string; ok: boolean }) => void }) {
  const user = session.user!;
  const client = useQueryClient();
  const logout = useMutation({
    mutationFn: accountApi.logout,
    onSuccess: () => {
      client.setQueryData(ACCOUNT_QUERY_KEY, { user: null, preferences: null, google: session.google } satisfies Session);
      onNotice({ text: "", ok: false });
      notify("Você saiu da sua conta.");
    },
    onError: (failure: Error) => onNotice({ text: failure.message, ok: false }),
  });

  return (
    <>
      <div className="account-title">
        <p className="overline">Área do usuário</p>
        <h1>Olá, {displayName(user)}.</h1>
        <p>
          {user.email} · conta criada em {accountDate(user.created_at)}
        </p>
      </div>

      <section className="account-card" aria-labelledby="account-place-title">
        <div className="account-card-head">
          <h2 id="account-place-title">Onde você compara preços</h2>
          <p>
            É o local que o filtro “Perto de você” usa ao abrir o site. As distâncias são em linha reta.
          </p>
        </div>
        <PreferredPlace preferences={session.preferences} />
      </section>

      <section className="account-card" aria-labelledby="account-lists-title">
        <div className="account-card-head">
          <h2 id="account-lists-title">Listas salvas</h2>
          <p>Abra uma lista da conta neste aparelho. Para salvar a lista atual, use “Minha lista”.</p>
        </div>
        <SavedLists />
      </section>

      <div className="account-signout">
        <Button variant="ghost" icon={<LogOut size={17} aria-hidden="true" />} loading={logout.isPending} onClick={() => logout.mutate()}>
          Sair da conta
        </Button>
      </div>
    </>
  );
}

type Place = { latitude: number; longitude: number };

function PreferredPlace({ preferences }: { preferences: Preferences | null }) {
  const client = useQueryClient();
  const saved = preferences?.location ?? null;
  const [editing, setEditing] = useState(false);
  const [place, setPlace] = useState<Place | null>(saved ? { latitude: saved.latitude, longitude: saved.longitude } : null);
  const [label, setLabel] = useState(saved?.label ?? "");
  const [radius, setRadius] = useState(saved?.radius_km ?? 5);
  const [query, setQuery] = useState("");
  const [places, setPlaces] = useState<AddressResult[]>([]);
  const [busy, setBusy] = useState<"search" | "gps" | "lookup" | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const save = useMutation({
    mutationFn: (next: Preferences) => accountApi.savePreferences(next),
    onSuccess: (data) => {
      client.setQueryData(ACCOUNT_QUERY_KEY, (current: Session | undefined) =>
        current ? { ...current, preferences: data.preferences } : current,
      );
      // Keep the editor's draft in step with what was stored ("Remover" leaves it empty).
      const stored = data.preferences.location;
      setPlace(stored ? { latitude: stored.latitude, longitude: stored.longitude } : null);
      setLabel(stored?.label ?? "");
      setRadius(stored?.radius_km ?? 5);
      setEditing(false);
      setError("");
      setMessage("");
      notify(data.preferences.location ? "Local preferido salvo." : "Local preferido removido.");
    },
    onError: (failure: Error) => setError(failure.message),
  });

  const region = preferences?.region ?? "Fortaleza";

  function choose(nextPlace: Place, nextLabel: string) {
    setPlace(nextPlace);
    setLabel(nextLabel);
    setPlaces([]);
    setQuery("");
    setMessage("");
    setError("");
  }

  async function find() {
    setBusy("search");
    setMessage("");
    try {
      const found = await searchPlaces(query.trim());
      setPlaces(found);
      if (!found.length)
        setMessage("Não encontramos esse endereço em Fortaleza. Tente o nome da rua com o número, ou um bairro.");
    } catch (failure) {
      setMessage(failure instanceof Error ? failure.message : "Não foi possível buscar o endereço agora.");
    } finally {
      setBusy(null);
    }
  }

  function locate() {
    setMessage("");
    setPlaces([]);
    if (!window.isSecureContext) {
      setMessage("O GPS exige uma conexão segura (HTTPS). Neste link local, digite seu endereço ou bairro.");
      return;
    }
    if (!navigator.geolocation) {
      setMessage("Seu navegador não oferece localização. Digite seu endereço ou bairro.");
      return;
    }
    setBusy("gps");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude, accuracy } = position.coords;
        if (!validCoordinates({ latitude, longitude }) || !Number.isFinite(accuracy) || accuracy > 2000) {
          setBusy(null);
          setMessage("A localização recebida está pouco precisa. Digite um endereço ou bairro.");
          return;
        }
        setBusy("lookup");
        void addressAt(latitude, longitude).then((found) => {
          choose({ latitude, longitude }, found ?? "Minha localização");
          setBusy(null);
        });
      },
      (failure) => {
        setBusy(null);
        setMessage(
          failure.code === 1
            ? "Localização não autorizada. Você pode digitar seu endereço ou bairro."
            : "Não foi possível obter sua localização. Digite seu endereço ou bairro.",
        );
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    );
  }

  return (
    <div className="account-place">
      {!editing && saved && (
        <>
          <div className="account-place-saved">
            <span className="account-place-icon">
              <MapPin size={20} aria-hidden="true" />
            </span>
            <div>
              <strong>{saved.label}</strong>
              <small>Até {saved.radius_km} km · {region} · usado em “Perto de você”</small>
            </div>
          </div>
          <div className="account-place-actions">
            <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
              Alterar
            </Button>
            <Button
              variant="ghost"
              size="sm"
              loading={save.isPending}
              onClick={() => save.mutate({ region, location: null })}
            >
              Remover
            </Button>
          </div>
        </>
      )}

      {!editing && !saved && (
        <>
          <p className="account-place-empty">
            Nenhum local preferido ainda. Sem ele, o filtro “Perto de você” começa sem referência.
          </p>
          <Button variant="secondary" size="sm" icon={<MapPin size={16} aria-hidden="true" />} onClick={() => setEditing(true)}>
            Definir local
          </Button>
        </>
      )}

      {editing && (
        <div className="account-place-editor">
          <p className="account-place-current">
            {place ? (
              <>
                Referência escolhida: <strong>{label}</strong>
              </>
            ) : (
              "Escolha uma referência em Fortaleza: use o GPS ou busque um endereço."
            )}
          </p>
          <div className="account-place-find">
            <TextField
              label="Endereço ou bairro em Fortaleza"
              type="search"
              value={query}
              minLength={3}
              maxLength={120}
              placeholder="Ex.: Rua Coronel Alexandrino, 405"
              autoComplete="off"
              onChange={(event) => {
                setQuery(event.target.value);
                setMessage("");
                if (event.target.value.trim().length < 3) setPlaces([]);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  if (query.trim().length >= 3) void find();
                }
              }}
            />
            <Button
              variant="secondary"
              loading={busy === "search"}
              disabled={busy !== null || query.trim().length < 3}
              icon={<Search size={17} aria-hidden="true" />}
              onClick={() => void find()}
            >
              Buscar
            </Button>
          </div>
          {message && (
            <p className="account-place-message" role="status">
              {message}
            </p>
          )}
          {places.length > 0 && (
            <ul className="account-place-results">
              {places.map((result) => (
                <li key={result.id}>
                  <button
                    type="button"
                    onClick={() =>
                      choose(
                        { latitude: result.latitude, longitude: result.longitude },
                        result.label,
                      )
                    }
                  >
                    <MapPin size={18} aria-hidden="true" />
                    <span>{result.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="account-place-gps">
            <Button
              variant="secondary"
              disabled={busy !== null}
              loading={busy === "gps" || busy === "lookup"}
              icon={<LocateFixed size={18} aria-hidden="true" />}
              onClick={locate}
            >
              {busy === "gps" ? "Obtendo localização…" : busy === "lookup" ? "Buscando seu endereço…" : "Usar minha localização"}
            </Button>
          </div>
          <Segmented<number>
            legend="Mostrar lojas até"
            options={radii.map((value) => ({ value, label: `${value} km` }))}
            value={radius}
            onChange={setRadius}
            disabled={busy !== null || save.isPending}
          />
          {error && (
            <p className="account-error" role="alert">
              {error}
            </p>
          )}
          <div className="account-place-save">
            <Button
              variant="primary"
              loading={save.isPending}
              disabled={!place || busy !== null}
              onClick={() =>
                place &&
                save.mutate({
                  region,
                  location: { label: label.trim() || "Minha localização", latitude: place.latitude, longitude: place.longitude, radius_km: radius },
                })
              }
            >
              Salvar local
            </Button>
            <Button
              variant="ghost"
              disabled={save.isPending}
              onClick={() => {
                setEditing(false);
                setPlace(saved ? { latitude: saved.latitude, longitude: saved.longitude } : null);
                setLabel(saved?.label ?? "");
                setRadius(saved?.radius_km ?? 5);
                setPlaces([]);
                setQuery("");
                setMessage("");
                setError("");
              }}
            >
              Cancelar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
