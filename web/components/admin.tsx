import { useEffect, useState } from "react";
import { ShieldCheck, ArrowLeft, RefreshCw, LogOut } from "lucide-react";
import { money, localTime, offerState, cents, ordinary } from "@/lib/domain";
type Row = Record<string, any>;
type Data = Record<string, Row[]>;
const toISO = (v: string) => (v ? new Date(v + "-03:00").toISOString() : null);
export default function Admin() {
  const [actor, setActor] = useState<string | null>(null),
    [data, setData] = useState<Data>({}),
    [tab, setTab] = useState("sources"),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [editing, setEditing] = useState<Row | null>(null);
  async function load() {
    const r = await fetch("/api/admin", { cache: "no-store" });
    if (r.ok) setData(await r.json());
    else setActor(null);
  }
  useEffect(() => {
    fetch("/api/session")
      .then((r) => r.json())
      .then((v) => {
        setActor(v.actor);
        if (v.actor) load();
      });
  }, []);
  async function act(action: string, body: unknown) {
    setBusy(true);
    setMessage("");
    try {
      const r = await fetch("/api/admin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, data: body }),
      });
      const v = await r.json();
      if (!r.ok) throw Error(v.error);
      setMessage("Operação registrada.");
      await load();
      return true;
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Falha ao salvar");
      return false;
    } finally {
      setBusy(false);
    }
  }
  const options = (name: string) => data[name] || [];
  function Field({
    name,
    label,
    type = "text",
    value,
    required = true,
  }: {
    name: string;
    label: string;
    type?: string;
    value?: string | number;
    required?: boolean;
  }) {
    return (
      <label>
        {label}
        <input
          name={name}
          type={type}
          defaultValue={value}
          required={required}
        />
      </label>
    );
  }
  function Network() {
    return (
      <label>
        Rede
        <select name="retailer_id" required>
          {options("retailers").map((r) => (
            <option value={r.id} key={r.id}>
              {r.name}
            </option>
          ))}
        </select>
      </label>
    );
  }
  function Context() {
    return (
      <label>
        Contexto de loja
        <select name="context_id" required>
          <option value="">Selecione</option>
          {options("store_contexts").map((c) => (
            <option value={c.id} key={c.id}>
              {c.label} ({c.channel})
            </option>
          ))}
        </select>
      </label>
    );
  }
  function Product() {
    return (
      <label>
        Produto canônico
        <select name="product_id" required>
          <option value="">Selecione</option>
          {options("products").map((p) => (
            <option value={p.id} key={p.id}>
              {p.name} · {p.brand} · {p.variant} · {p.amount} {p.unit}
            </option>
          ))}
        </select>
      </label>
    );
  }
  async function submit(
    e: React.FormEvent<HTMLFormElement>,
    action: string,
    convert: (v: Row) => Row,
  ) {
    e.preventDefault();
    try {
      const f = e.currentTarget,
        v = Object.fromEntries(new FormData(f));
      if (await act(action, convert(v))) {
        f.reset();
        setEditing(null);
      }
    } catch (e) {
      setMessage(String(e));
    }
  }
  return (
    <main className="admin-shell">
      <header className="admin-header">
        <a href="/" className="text-link">
          <ArrowLeft size={18} />
          Mercado em Dia
        </a>
        <h1>
          <ShieldCheck />
          Administração
        </h1>
        {actor && (
          <button
            className="secondary"
            onClick={async () => {
              await fetch("/api/session", { method: "DELETE" });
              setActor(null);
            }}
          >
            <LogOut size={17} />
            Sair
          </button>
        )}
      </header>
      {message && (
        <div className="notice" role="status">
          {message}
        </div>
      )}
      {!actor ? (
        <form
          className="admin-login"
          onSubmit={async (e) => {
            e.preventDefault();
            const f = Object.fromEntries(new FormData(e.currentTarget));
            const r = await fetch("/api/session", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(f),
            });
            if (r.ok) {
              setActor(String(f.username));
              setMessage("");
              load();
            } else setMessage((await r.json()).error);
          }}
        >
          <h2>Acesso restrito</h2>
          <p>Entre com sua conta administrativa.</p>
          <label>
            Usuário
            <input name="username" autoComplete="username" required />
          </label>
          <label>
            Senha
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
            />
          </label>
          <button className="primary">Entrar</button>
        </form>
      ) : (
        <>
          <div className="admin-tabs">
            {[
              ["sources", "Fontes e lojas"],
              ["products", "Produtos"],
              ["offers", "Ofertas"],
              ["reviews", "Revisão"],
              ["flyers", "Encartes"],
              ["runs", "Execuções"],
              ["audit", "Auditoria"],
            ].map(([id, t]) => (
              <button
                key={id}
                className={tab === id ? "active" : ""}
                onClick={() => {
                  setTab(id);
                  setEditing(null);
                }}
              >
                {t}
              </button>
            ))}
          </div>
          <fieldset disabled={busy} className="admin-content">
            {tab === "sources" && (
              <>
                <h2>Fontes de dados</h2>
                <p>
                  Habilitar depende de um conector implementado, autorização
                  documentada e respeito ao robots.txt.
                </p>
                {options("retailers").map((r) => (
                  <article className="admin-row" key={r.id}>
                    <div>
                      <h3>{r.name}</h3>
                      <p>{r.audit_status}</p>
                      <span className="small">
                        {r.last_error ||
                          "Nenhuma coleta de preços bem-sucedida registrada."}
                      </span>
                    </div>
                    <div className="actions">
                      <button
                        className="secondary"
                        onClick={() =>
                          act("source", { id: r.id, enabled: !r.enabled })
                        }
                      >
                        {r.enabled ? "Desabilitar" : "Habilitar"}
                      </button>
                      <button
                        className="secondary"
                        onClick={() =>
                          act("collect", { id: r.id, key: crypto.randomUUID() })
                        }
                      >
                        <RefreshCw size={16} />
                        Coletar
                      </button>
                    </div>
                  </article>
                ))}
                <h2 className="spaced">Contextos verificados</h2>
                {options("store_contexts").map((c) => (
                  <div className="admin-row" key={c.id}>
                    <div>
                      {c.label} · {c.region} · {c.channel}
                      <p>
                        {c.address || "Endereço não informado"} ·{" "}
                        {c.phone || "Telefone não informado"}
                      </p>
                    </div>
                  </div>
                ))}
                <form
                  className="admin-form"
                  onSubmit={(e) => submit(e, "context", (v) => v)}
                >
                  <h3>Registrar loja ou atendimento</h3>
                  <Network />
                  <Field name="label" label="Loja / contexto" />
                  <Field name="region" label="Região" value="Fortaleza" />
                  <Field
                    name="address"
                    label="Endereço confirmado (opcional)"
                    required={false}
                  />
                  <Field
                    name="phone"
                    label="Telefone confirmado (opcional)"
                    type="tel"
                    required={false}
                  />
                  <label>
                    Canal
                    <select name="channel">
                      <option value="catalog">Online</option>
                      <option value="physical">Loja física</option>
                      <option value="flyer">Encarte</option>
                    </select>
                  </label>
                  <label className="wide">
                    Evidência de abrangência e dos contatos informados
                    <textarea name="evidence" required minLength={10} />
                  </label>
                  <button className="primary">
                    Salvar contexto verificado
                  </button>
                </form>
              </>
            )}
            {tab === "products" && (
              <>
                <h2>Produtos canônicos</h2>
                <p>
                  A edição retira ofertas vinculadas e exige nova revisão das
                  correspondências.
                </p>
                {options("products").map((p) => (
                  <div className="admin-row" key={p.id}>
                    <div>
                      <strong>
                        {p.name} · {p.brand}
                      </strong>
                      <p>
                        {p.variant} · {p.amount} {p.unit} × {p.pack_count} ·{" "}
                        {p.published ? "Publicado" : "Rascunho"}
                      </p>
                    </div>
                    <button className="secondary" onClick={() => setEditing(p)}>
                      Editar
                    </button>
                  </div>
                ))}
                <form
                  key={editing?.id || "new"}
                  className="admin-form"
                  onSubmit={(e) =>
                    submit(e, "product", (v) => ({
                      ...v,
                      ...(editing ? { id: editing.id } : {}),
                      amount: Number(v.amount),
                      pack_count: Number(v.pack_count),
                      gtin: v.gtin || null,
                      gtin_evidence: v.gtin_evidence || null,
                    }))
                  }
                >
                  <h3>{editing ? "Editar produto" : "Novo produto"}</h3>
                  {[
                    ["name", "Nome"],
                    ["brand", "Marca"],
                    ["category", "Categoria"],
                    ["variant", "Variante"],
                  ].map(([name, label]) => (
                    <Field
                      key={name}
                      name={name}
                      label={label}
                      value={editing?.[name]}
                    />
                  ))}
                  <Field
                    name="amount"
                    label="Conteúdo em g, ml ou unidades"
                    type="number"
                    value={editing?.amount}
                  />
                  <label>
                    Unidade
                    <select name="unit" defaultValue={editing?.unit || "g"}>
                      <option>g</option>
                      <option>ml</option>
                      <option>un</option>
                    </select>
                  </label>
                  <Field
                    name="pack_count"
                    label="Quantidade de embalagens"
                    type="number"
                    value={editing?.pack_count || 1}
                  />
                  <Field
                    name="gtin"
                    label="GTIN confirmado (opcional)"
                    required={false}
                    value={editing?.gtin}
                  />
                  <Field
                    name="gtin_evidence"
                    label="Evidência do GTIN"
                    required={false}
                    value={editing?.gtin_evidence}
                  />
                  <button className="primary">Salvar rascunho</button>
                </form>
              </>
            )}
            {tab === "offers" && (
              <>
                <h2>Ofertas e publicação</h2>
                {options("offers").map((o) => (
                  <div className="admin-row" key={o.id}>
                    <div>
                      <strong>
                        {o.retailer_name} ·{" "}
                        {o.price_cents ? money(o.price_cents) : "Sem preço"}
                      </strong>
                      <p>
                        {o.context_label} · {offerState(o as any)} · {o.method}
                      </p>
                      <p className="small">{o.evidence}</p>
                    </div>
                    <button
                      className="secondary"
                      onClick={() =>
                        act("publish", { id: o.id, published: !o.published })
                      }
                    >
                      {o.published ? "Retirar" : "Publicar"}
                    </button>
                  </div>
                ))}
                <form
                  className="admin-form"
                  onSubmit={(e) =>
                    submit(e, "offer", (v) => ({
                      product_id: v.product_id,
                      retailer_id: v.retailer_id,
                      context_id: v.context_id,
                      channel: v.channel,
                      price_cents: v.price ? cents(v.price) : null,
                      conditions: {
                        ...ordinary(),
                        club: v.club || null,
                        coupon: v.coupon || null,
                        min_quantity: Number(v.min_quantity || 1),
                        limit_per_customer: v.limit ? Number(v.limit) : null,
                        payment: v.payment || null,
                        region_note: v.region_note || "",
                      },
                      availability: v.availability,
                      price_observed_at: toISO(v.observed),
                      valid_from: toISO(v.start),
                      valid_until: toISO(v.end),
                      source_url: v.source_url,
                      evidence: v.evidence,
                    }))
                  }
                >
                  <h3>Entrada manual identificada</h3>
                  <Product />
                  <Network />
                  <Context />
                  <label>
                    Canal
                    <select name="channel">
                      <option value="catalog">Online</option>
                      <option value="physical">Loja física</option>
                      <option value="flyer">Encarte</option>
                    </select>
                  </label>
                  <Field
                    name="price"
                    label="Preço (ex.: 12,90)"
                    required={false}
                  />
                  <label>
                    Disponibilidade
                    <select name="availability">
                      <option value="unknown">Desconhecida</option>
                      <option value="available">Disponível na fonte</option>
                      <option value="unavailable">
                        Indisponível confirmado
                      </option>
                    </select>
                  </label>
                  <Field
                    name="observed"
                    label="Observação · horário de Fortaleza"
                    type="datetime-local"
                  />
                  <Field
                    name="start"
                    label="Válida a partir de · Fortaleza"
                    type="datetime-local"
                    required={false}
                  />
                  <Field
                    name="end"
                    label="Válida até · Fortaleza"
                    type="datetime-local"
                    required={false}
                  />
                  {[
                    ["club", "Clube"],
                    ["coupon", "Cupom"],
                    ["min_quantity", "Quantidade mínima"],
                    ["limit", "Limite por cliente"],
                    ["payment", "Pagamento"],
                    ["region_note", "Restrição regional"],
                  ].map(([name, label]) => (
                    <Field
                      key={name}
                      name={name}
                      label={label}
                      required={false}
                    />
                  ))}
                  <Field
                    name="source_url"
                    label="URL oficial da oferta"
                    type="url"
                  />
                  <label className="wide">
                    Evidência e condições verificadas
                    <textarea name="evidence" minLength={3} required />
                  </label>
                  <button className="primary">
                    Salvar oferta para publicar
                  </button>
                </form>
              </>
            )}
            {tab === "reviews" && (
              <>
                <h2>Fila de revisão</h2>
                {options("review_items").map((r) => (
                  <article className="review-card" key={r.id}>
                    <span className="badge">
                      {r.kind} · {r.status}
                    </span>
                    <h3>{r.reason}</h3>
                    <pre>{r.payload}</pre>
                    {r.status === "pending" && (
                      <form
                        onSubmit={(e) =>
                          submit(e, "review", (v) => ({ id: r.id, ...v }))
                        }
                      >
                        <label>
                          Nota da revisão
                          <input name="note" minLength={5} required />
                        </label>
                        {r.kind === "match" && <Product />}
                        <label>
                          Decisão
                          <select name="decision">
                            <option value="reject">Rejeitar</option>
                            <option value="approve">Aprovar</option>
                          </select>
                        </label>
                        <button className="secondary">Registrar decisão</button>
                        {r.kind !== "source" && (
                          <button
                            type="button"
                            className="secondary"
                            onClick={() => setEditing(r)}
                          >
                            Corrigir extração
                          </button>
                        )}
                      </form>
                    )}
                  </article>
                ))}
                {editing && (
                  <form
                    className="admin-form"
                    onSubmit={(e) =>
                      submit(e, "edit_review", (v) => ({
                        id: editing.id,
                        payload: JSON.parse(v.payload),
                        note: v.note,
                      }))
                    }
                  >
                    <h3>Corrigir campos extraídos</h3>
                    <label className="wide">
                      Campos JSON
                      <textarea
                        name="payload"
                        rows={10}
                        defaultValue={editing.payload}
                        required
                      />
                    </label>
                    <Field name="note" label="Motivo da correção" />
                    <button className="primary">Salvar correção</button>
                  </form>
                )}
                <details className="spaced">
                  <summary>
                    Registrar extração assistida para correspondência
                  </summary>
                  <form
                    className="admin-form"
                    onSubmit={(e) =>
                      submit(e, "candidate", (v) => ({
                        ...v,
                        product: JSON.parse(v.product),
                      }))
                    }
                  >
                    <Network />
                    <Context />
                    <Field name="original_id" label="Identificador original" />
                    <Field name="original_name" label="Nome original" />
                    <Field name="source_url" label="URL oficial" type="url" />
                    <label className="wide">
                      Campos extraídos (JSON; formato do produto canônico)
                      <textarea
                        name="product"
                        rows={8}
                        required
                        placeholder={
                          '{"name":"...","brand":"...","category":"...","variant":"...","amount":250,"unit":"g","pack_count":1}'
                        }
                      />
                    </label>
                    <button className="primary">Enviar para revisão</button>
                  </form>
                </details>
              </>
            )}
            {tab === "flyers" && (
              <>
                <h2>Encartes registrados</h2>
                {options("flyers").map((f) => (
                  <div className="admin-row" key={f.id}>
                    <div>
                      <strong>{f.title}</strong>
                      <p>{f.scope}</p>
                      <span className="small">
                        {f.method} · {f.status} ·{" "}
                        {f.valid_until
                          ? localTime(f.valid_until)
                          : "Validade pendente"}
                      </span>
                    </div>
                    <a href={f.source_url} target="_blank" rel="noreferrer">
                      Original ↗
                    </a>
                  </div>
                ))}
                <form
                  className="admin-form"
                  onSubmit={(e) =>
                    submit(e, "flyer", (v) => ({
                      retailer_id: v.retailer_id,
                      title: v.title,
                      source_url: v.source_url,
                      media_url: v.media_url || null,
                      media_type: v.media_type || null,
                      media_pages: String(v.media_pages || "")
                        .split(/\r?\n/)
                        .map((url) => url.trim())
                        .filter(Boolean),
                      valid_from: toISO(v.start),
                      valid_until: toISO(v.end),
                      scope: v.scope,
                      evidence: v.evidence,
                    }))
                  }
                >
                  <h3>Cadastrar encarte oficial</h3>
                  <Network />
                  <Field name="title" label="Título" />
                  <Field name="source_url" label="URL oficial" type="url" />
                  <Field
                    name="media_url"
                    label="URL do arquivo no domínio oficial (opcional)"
                    type="url"
                    required={false}
                  />
                  <label>
                    Formato do arquivo
                    <select name="media_type" defaultValue="">
                      <option value="">Sem arquivo cadastrado</option>
                      <option value="image">Imagem</option>
                      <option value="pdf">PDF</option>
                    </select>
                  </label>
                  <p className="wide">
                    Cadastre somente arquivos oficiais cuja exibição seja
                    permitida. Registre essa confirmação na evidência. O
                    aplicativo não copia páginas nem contorna bloqueios.
                  </p>
                  <label className="wide">
                    Páginas para o carrossel (opcional, uma URL de imagem por
                    linha)
                    <textarea
                      name="media_pages"
                      rows={4}
                      placeholder="https://dominio-oficial.com/pagina-1.jpg"
                    />
                  </label>
                  <Field
                    name="start"
                    label="Início · Fortaleza"
                    type="datetime-local"
                    required={false}
                  />
                  <Field
                    name="end"
                    label="Fim · Fortaleza"
                    type="datetime-local"
                    required={false}
                  />
                  <Field
                    name="scope"
                    label="Abrangência confirmada ou pendência explícita"
                  />
                  <Field
                    name="evidence"
                    label="Evidência e responsável pela conferência"
                  />
                  <button className="primary">Publicar link</button>
                </form>
              </>
            )}
            {tab === "runs" && (
              <>
                <h2>Execuções de coleta</h2>
                <div className="notice">
                  Meta de 95% em sete dias ainda não verificada. Execução
                  ignorada não equivale a sucesso; descoberta de encartes não
                  equivale a cobertura de preços.
                </div>
                {options("collection_runs").map((r) => (
                  <div className="admin-row" key={r.id}>
                    <div>
                      <strong>
                        {r.retailer_id} · {r.status}
                      </strong>
                      <p>
                        {localTime(r.started_at)} · {r.trigger_type}
                      </p>
                      <p>
                        {r.obtained} obtidos · {r.published} publicados ·{" "}
                        {r.review_count} em revisão
                      </p>
                      <span className="warning">{r.error}</span>
                    </div>
                  </div>
                ))}
                {!options("collection_runs").length && (
                  <p>Nenhuma execução registrada.</p>
                )}
              </>
            )}
            {tab === "audit" && (
              <>
                <h2>Trilha de auditoria</h2>
                {options("audit_log").map((a) => (
                  <div className="audit-item" key={a.id}>
                    <strong>{a.action}</strong>
                    <p>
                      {a.actor} · {localTime(a.created_at)}
                    </p>
                    <pre>{a.detail}</pre>
                  </div>
                ))}
              </>
            )}
          </fieldset>
        </>
      )}
    </main>
  );
}
