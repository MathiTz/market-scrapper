import { useState, type ReactNode } from "react";
import { ChevronRight, MapPin, Plus, Search, Share2, ShoppingBasket, SlidersHorizontal, X } from "lucide-react";
import { Button, IconButton, type ButtonSize, type ButtonVariant } from "@/components/ui/button";
import { Chip, ChipCheckbox } from "@/components/ui/chip";
import { TextField } from "@/components/ui/field";
import { SelectField } from "@/components/ui/select";
import { CheckboxField } from "@/components/ui/checkbox";
import { Segmented } from "@/components/ui/segmented";
import { Tooltip, TooltipProvider } from "@/components/ui/tooltip";
import { FlyerGridSkeleton, RailSkeleton } from "@/components/ui/skeleton";

/**
 * The components sheet at /demo?vitrine=1: every primitive in every state, side by side, plus the type
 * scale, the colour ramps and the shadows, all read from the tokens. Hover, focus and active are forced with
 * data attributes so a screenshot (and the hover audit) can see them on any device. Nothing here touches the
 * API or the shopping list.
 */
const forcedStates: { name: string; props: Record<string, unknown> }[] = [
  { name: "default", props: {} },
  { name: "hover", props: { "data-hover": "" } },
  { name: "focus", props: { "data-focus": "" } },
  { name: "active", props: { "data-active": "" } },
  { name: "disabled", props: { disabled: true } },
  { name: "loading", props: { loading: true } },
];
const variants: ButtonVariant[] = ["primary", "secondary", "ghost", "negative"];
const sizes: ButtonSize[] = ["sm", "md", "lg"];
const ramps: Record<string, string[]> = {
  neutral: ["0", "50", "100", "200", "300", "400", "500", "600", "700", "800", "900"],
  brand: ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900"],
  amber: ["50", "100", "200", "600", "700"],
  lime: ["100", "900"],
  red: ["50", "600", "700"],
  blue: ["50", "700"],
};
const typeSteps = ["xs", "sm", "md", "base", "lg", "xl", "2xl", "3xl", "4xl"];
const motionTokens = [
  ["--dur-press", "160 ms", "pressionar, chip, campo"],
  ["--dur-tooltip", "125 ms", "tooltip"],
  ["--dur-menu", "180 ms", "select, pílula da navegação"],
  ["--dur-state", "200 ms", "véu da busca, foto"],
  ["--dur-modal", "250 ms", "diálogo entra (sai em 190 ms)"],
  ["--dur-sheet", "500 ms", "bottom sheet"],
  ["--dur-toast", "400 ms", "toast"],
  ["--ease-out", "cubic-bezier(0.23, 1, 0.32, 1)", "entradas"],
  ["--ease-in-out", "cubic-bezier(0.77, 0, 0.175, 1)", "pílula que desliza"],
  ["--ease-drawer", "cubic-bezier(0.32, 0.72, 0, 1)", "sheet"],
];

function Section({ title, lead, children }: { title: string; lead?: string; children: ReactNode }) {
  return (
    <section className="vitrine-section">
      <h2>{title}</h2>
      {lead && <p>{lead}</p>}
      {children}
    </section>
  );
}

function Cell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="vitrine-cell">
      {children}
      <small>{label}</small>
    </div>
  );
}

export default function Vitrine() {
  const [selected, setSelected] = useState(true);
  const [text, setText] = useState("12,50");
  const [sort, setSort] = useState("discount-near");
  const [club, setClub] = useState(true);
  const [radius, setRadius] = useState(5);
  return (
    <TooltipProvider>
    <div className="app-shell">
      <div className="demo-banner">
        VITRINE DE COMPONENTES · dados fictícios <a href="/demo">Voltar à demonstração</a>
      </div>
      <main className="main vitrine" id="conteudo">
        <div className="vitrine-intro">
          <p className="overline">Mercado em Dia · sistema de interface</p>
          <h1>Cada componente, em cada estado.</h1>
          <p className="muted">
            Os valores vêm de <code>tokens/tokens.json</code>. Hover, foco e pressionado estão forçados por
            atributos para aparecerem em qualquer aparelho; nos demais estados o comportamento é o real.
          </p>
        </div>

        <Section title="Botões" lead="Quatro variantes, um só formato. Em carregamento, o spinner ocupa o lugar do ícone e o rótulo continua dizendo o que acontece.">
          {variants.map((variant) => (
            <div className="vitrine-grid" key={variant}>
              {forcedStates.map(({ name, props }) => (
                <Cell key={name} label={`${variant} · ${name}`}>
                  <Button variant={variant} icon={<Plus size={18} aria-hidden="true" />} {...props}>
                    Adicionar
                  </Button>
                </Cell>
              ))}
            </div>
          ))}
          <div className="vitrine-row">
            {sizes.map((size) => (
              <Button key={size} variant="primary" size={size} icon={<Plus size={18} aria-hidden="true" />}>
                Tamanho {size}
              </Button>
            ))}
            <Button variant="secondary" size="sm" trailing icon={<ChevronRight size={16} aria-hidden="true" />}>
              Ver todas
            </Button>
            <Button variant="secondary" iconOnly aria-label="Compartilhar oferta" icon={<Share2 size={18} aria-hidden="true" />} />
            <IconButton label="Fechar">
              <X size={21} aria-hidden="true" />
            </IconButton>
          </div>
        </Section>

        <Section title="Chips" lead="Categorias, redes e filtros ativos com a mesma pílula. O ✓ desliza para dentro quando o chip é selecionado.">
          <div className="vitrine-grid">
            <Cell label="default">
              <Chip>Mercearia</Chip>
            </Cell>
            <Cell label="hover">
              <Chip data-hover="">Mercearia</Chip>
            </Cell>
            <Cell label="focus">
              <Chip data-focus="">Mercearia</Chip>
            </Cell>
            <Cell label="active">
              <Chip data-active="">Mercearia</Chip>
            </Cell>
            <Cell label="selected">
              <Chip selected>Mercearia</Chip>
            </Cell>
            <Cell label="selected · hover">
              <Chip selected data-hover="">
                Mercearia
              </Chip>
            </Cell>
            <Cell label="disabled">
              <Chip disabled>Mercearia</Chip>
            </Cell>
            <Cell label="com ícone">
              <Chip icon={<SlidersHorizontal size={16} aria-hidden="true" />}>Todas</Chip>
            </Cell>
            <Cell label="removable">
              <Chip removable aria-label="Remover filtro: Desconto de 20% ou mais">
                Desconto de 20% ou mais
              </Chip>
            </Cell>
            <Cell label="checkbox (toque para alternar)">
              <ChipCheckbox checked={selected} onChange={setSelected}>
                Sams Club
              </ChipCheckbox>
            </Cell>
          </div>
        </Section>

        <Section title="Campos" lead="Rótulo, caixa e dica. O erro troca a cor da borda e da dica; a busca da página inicial só herda o anel de foco.">
          <div className="vitrine-grid">
            <Cell label="default">
              <TextField label="Preço máximo (R$)" placeholder="0,00" inputMode="decimal" value={text} onChange={(e) => setText(e.target.value)} />
            </Cell>
            <Cell label="hover">
              <TextField label="Preço máximo (R$)" placeholder="0,00" defaultValue="" data-hover="" />
            </Cell>
            <Cell label="focus">
              <TextField label="Preço máximo (R$)" placeholder="0,00" defaultValue="12," data-focus="" />
            </Cell>
            <Cell label="invalid">
              <TextField label="Preço máximo (R$)" defaultValue="doze" invalid hint="Use apenas números, como 12,50." />
            </Cell>
            <Cell label="disabled">
              <TextField label="Preço máximo (R$)" defaultValue="12,50" disabled />
            </Cell>
            <Cell label="com dica">
              <TextField label="Endereço ou bairro" placeholder="Ex.: Aldeota" hint="Só endereços em Fortaleza." />
            </Cell>
          </div>
          <form className="searchbar" role="search" onSubmit={(e) => e.preventDefault()}>
            <Search size={22} aria-hidden="true" />
            <input aria-label="Buscar produtos" placeholder="Buscar produtos" />
            <button type="submit">
              Buscar <span aria-hidden="true">→</span>
            </button>
          </form>
        </Section>

        <Section title="Select, checkbox, segmentado e tooltip" lead="A lista cresce a partir do gatilho em 180 ms; o ✓ da caixa se desenha em 160 ms; a pílula desliza; o primeiro tooltip espera 400 ms e os vizinhos abrem na hora.">
          <div className="vitrine-grid">
            <Cell label="select">
              <SelectField
                label="Ordenar por"
                value={sort}
                onChange={setSort}
                options={[
                  { value: "relevance", label: "Mais relevantes" },
                  { value: "discount-near", label: "Maior desconto" },
                  { value: "price-asc", label: "Menor preço" },
                  { value: "price-desc", label: "Maior preço" },
                ]}
              />
            </Cell>
            <Cell label="select · disabled">
              <SelectField label="Semana" value="*" onChange={() => {}} disabled options={[{ value: "*", label: "Selecione um mês" }]} />
            </Cell>
            <Cell label="checkbox">
              <CheckboxField label="Incluir preços de clube" checked={club} onChange={setClub} />
            </Cell>
            <Cell label="checkbox · disabled">
              <CheckboxField label="Incluir sem preço atual" checked={false} onChange={() => {}} disabled />
            </Cell>
          </div>
          <div className="vitrine-row" style={{ maxWidth: 480 }}>
            <Segmented<number>
              legend="Mostrar lojas até"
              options={[1, 3, 5, 10].map((km) => ({ value: km, label: `${km} km` }))}
              value={radius}
              onChange={setRadius}
            />
          </div>
          <div className="vitrine-row">
            <Tooltip label="Anteriores">
              <IconButton label="Ofertas anteriores">
                <ChevronRight size={18} aria-hidden="true" style={{ transform: "rotate(180deg)" }} />
              </IconButton>
            </Tooltip>
            <Tooltip label="Próximas">
              <IconButton label="Próximas ofertas">
                <ChevronRight size={18} aria-hidden="true" />
              </IconButton>
            </Tooltip>
            <Tooltip label="Compartilhar">
              <Button variant="secondary" iconOnly aria-label="Compartilhar oferta" icon={<Share2 size={18} aria-hidden="true" />} />
            </Tooltip>
            <Tooltip label="Fechar">
              <IconButton label="Fechar">
                <X size={21} aria-hidden="true" />
              </IconButton>
            </Tooltip>
            <small className="muted">Passe o ponteiro ou use Tab.</small>
          </div>
        </Section>

        <Section title="Carregando" lead="A forma do que vem, com uma onda que só usa transform. Com movimento reduzido a onda para e o bloco fica.">
          <RailSkeleton count={3} />
          <FlyerGridSkeleton count={3} />
        </Section>

        <Section title="Tipografia" lead="Archivo Variable em nove passos (razão 1,2). O preço é a única licença: semicondensado, tabular.">
          <ul className="vitrine-type">
            {typeSteps.map((step) => (
              <li key={step}>
                <code>--md-text-{step}</code>
                <span style={{ fontSize: `var(--md-text-${step})`, lineHeight: 1.2 }}>Arroz Tio João 5 kg</span>
              </li>
            ))}
            <li>
              <code>.price</code>
              <strong className="price" style={{ margin: 0 }}>
                R$ 1.234,56
              </strong>
            </li>
          </ul>
        </Section>

        <Section title="Cor" lead="Rampas em OKLCH; a interface só usa os nomes semânticos. O canvas é branco com 3% de gelo; o verde é acento, nunca superfície.">
          {Object.entries(ramps).map(([ramp, steps]) => (
            <div className="vitrine-ramp" key={ramp}>
              {steps.map((step) => (
                <span className="vitrine-swatch" key={step}>
                  <i style={{ background: `var(--md-${ramp}-${step})` }} />
                  {ramp}-{step}
                </span>
              ))}
            </div>
          ))}
          <div className="vitrine-ramp">
            {["surface-canvas", "surface-level-1", "surface-level-2", "surface-inverse", "selected-fill", "deal-fill", "condition-fill", "messaging-warning-fill", "messaging-error-fill", "messaging-info-fill"].map((name) => (
              <span className="vitrine-swatch" key={name}>
                <i style={{ background: `var(--md-${name})` }} />
                {name}
              </span>
            ))}
          </div>
        </Section>

        <Section title="Elevação" lead="Sombras tingidas de tinta, nunca cinza puro. Cartões usam 1; menus e sugestões, 2; diálogos, 3.">
          <div className="vitrine-grid">
            {["0", "1", "2", "3"].map((level) => (
              <Cell key={level} label={`--md-elevation-${level}`}>
                <div className="vitrine-elevation" style={{ boxShadow: `var(--md-elevation-${level})`, width: "100%" }} />
              </Cell>
            ))}
          </div>
        </Section>

        <Section title="Motion" lead="Durações e curvas dos tokens. Com movimento reduzido, escala e deslocamento viram zero e os fades ficam.">
          <ul className="vitrine-motion">
            {motionTokens.map(([token, value, use]) => (
              <li key={token}>
                <code>{token}</code> · {value} · {use}
              </li>
            ))}
          </ul>
          <div className="vitrine-row">
            <Button variant="primary" icon={<ShoppingBasket size={18} aria-hidden="true" />}>
              Pressione para sentir
            </Button>
            <Button variant="secondary" size="sm" icon={<MapPin size={16} aria-hidden="true" />}>
              Onde encontrar
            </Button>
          </div>
        </Section>
      </main>
    </div>
    </TooltipProvider>
  );
}
