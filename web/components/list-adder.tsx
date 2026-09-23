import { useId, useMemo, useState } from "react";
import { Plus } from "lucide-react";
import { money, type Product } from "@/lib/domain";
import { buildIndex, searchIndexed } from "@/lib/search";
import { useDebounced } from "@/lib/use-debounced";

/**
 * The "add an item" box of the shopping list. It only adds products we have: typing "banana" lists the
 * matching ones (prata, ouro, nanica...) to pick from, so every item can be priced in each store.
 * There is no free text.
 */
export function ListAdder({
  products,
  priceOf,
  onProduct,
}: {
  products: Product[];
  priceOf: (productId: string) => number | null;
  onProduct: (product: Product) => void;
}) {
  const [text, setText] = useState("");
  const [active, setActive] = useState(-1);
  const [open, setOpen] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const id = useId();
  const typed = text.trim();
  // Typing against a couple of thousand products visibly lagged: each keystroke re-cleaned every product
  // name from scratch. The index is built once per product list (rarely changes); only the search itself,
  // debounced, runs per keystroke, and it now just scans already-split words.
  const index = useMemo(() => buildIndex(products, (p) => p.name), [products]);
  const debouncedTyped = useDebounced(typed, 150);
  const suggestions = useMemo(
    () => (debouncedTyped.length >= 2 ? searchIndexed(index, debouncedTyped, 8) : []),
    [index, debouncedTyped],
  );
  const showList = open && typed.length >= 2;

  function choose(index: number) {
    const pick = suggestions[index >= 0 ? index : 0]; // no highlight: the best match
    if (!pick) {
      setNotFound(true);
      return;
    }
    onProduct(pick);
    setText("");
    setActive(-1);
    setNotFound(false);
  }

  return (
    <form
      className="quick-add list-adder"
      onSubmit={(e) => {
        e.preventDefault();
        choose(active);
      }}
    >
      <div className="combo">
        <input
          role="combobox"
          aria-expanded={showList}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 ? `${id}-${active}` : undefined}
          aria-invalid={notFound || undefined}
          name="item"
          maxLength={160}
          required
          autoComplete="off"
          placeholder="Buscar um produto para a lista (ex.: banana)"
          aria-label="Buscar um produto para adicionar à lista"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setOpen(true);
            setActive(-1);
            setNotFound(false);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActive((a) => Math.min(a + 1, suggestions.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, -1));
            } else if (e.key === "Escape") {
              setOpen(false);
              setActive(-1);
            }
          }}
        />
        {showList && (
          <ul id={`${id}-list`} role="listbox" className="suggestions">
            {suggestions.map((product, index) => {
              const price = priceOf(product.id);
              return (
                <li
                  key={product.id}
                  id={`${id}-${index}`}
                  role="option"
                  aria-selected={active === index}
                  className={active === index ? "active" : undefined}
                  // mousedown, not click: the input's blur would otherwise close the list first
                  onMouseDown={(e) => {
                    e.preventDefault();
                    choose(index);
                  }}
                >
                  <span>{product.name}</span>
                  {price !== null && <small>a partir de {money(price)}</small>}
                </li>
              );
            })}
            {!suggestions.length && (
              <li className="no-match" role="option" aria-disabled="true" aria-selected="false">
                Nenhum produto com preço encontrado para “{typed}”
              </li>
            )}
          </ul>
        )}
        {notFound && (
          <p className="field-hint" role="alert">
            Escolha um produto da lista de sugestões.
          </p>
        )}
      </div>
      <button className="primary" type="submit">
        <Plus size={18} />
        Adicionar
      </button>
    </form>
  );
}
