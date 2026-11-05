import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, FolderOpen, Trash2 } from "lucide-react";
import { accountApi, SAVED_LISTS_QUERY_KEY, useAccount } from "@/lib/account-api";
import {
  accountDate,
  defaultListName,
  itemCount,
  listNameProblem,
  savedLines,
  type SavedList,
} from "@/lib/account";
import { browserStorage, writeList, type Line } from "@/lib/list-storage";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/ui/field";
import { notify } from "@/lib/notify";

/**
 * The lists kept in the shopper's account: saving the list that is on screen, opening a saved one and
 * deleting it. Signed out, it is a one-line invitation - the local list keeps working without an account.
 */
export function SavedLists({ current, onOpen }: { current?: Line[]; onOpen?: (lines: Line[]) => void }) {
  const session = useAccount();
  const client = useQueryClient();
  const [name, setName] = useState(defaultListName);
  const [error, setError] = useState("");

  const lists = useQuery({
    queryKey: SAVED_LISTS_QUERY_KEY,
    queryFn: async () => (await accountApi.lists()).lists,
    enabled: Boolean(session.data?.user),
    staleTime: 30_000,
  });

  const refresh = () => client.invalidateQueries({ queryKey: SAVED_LISTS_QUERY_KEY });

  const save = useMutation({
    mutationFn: async () => {
      const trimmed = name.trim();
      const same = (lists.data ?? []).find((list) => list.name.toLowerCase() === trimmed.toLowerCase());
      return same
        ? accountApi.updateList(same.id, trimmed, savedLines(current ?? []))
        : accountApi.createList(trimmed, savedLines(current ?? []));
    },
    onSuccess: () => {
      setName(defaultListName());
      setError("");
      void refresh();
      notify("Lista salva na sua conta.");
    },
    onError: (failure: Error) => setError(failure.message),
  });

  const remove = useMutation({
    mutationFn: (id: string) => accountApi.deleteList(id),
    onSuccess: () => {
      setError("");
      void refresh();
      notify("Lista excluída da sua conta.");
    },
    onError: (failure: Error) => setError(failure.message),
  });

  function open(list: SavedList) {
    if (onOpen) {
      onOpen(list.lines);
      notify(`"${list.name}" aberta na sua lista.`);
      return;
    }
    // From the account page there is no list on screen: put it in this browser's list and go there.
    if (!writeList(browserStorage(), "med-list-real", list.lines)) {
      setError("Este navegador não permite guardar a lista. Abra a lista em um navegador com armazenamento liberado.");
      return;
    }
    window.location.href = "/";
  }

  if (session.isPending) return null;
  if (!session.data?.user) {
    return (
      <p className="list-account-hint">
        <ClipboardList size={18} aria-hidden="true" />
        <span>
          Sua lista fica neste aparelho.{" "}
          <a href="/conta">Entre na sua conta</a> para guardar uma cópia e abrir em outro aparelho.
        </span>
      </p>
    );
  }

  const problem = name ? listNameProblem(name) : null;
  const saved = lists.data ?? [];

  return (
    <section className="saved-lists" aria-labelledby="saved-lists-title">
      <div className="saved-lists-head">
        <h3 id="saved-lists-title">Suas listas na conta</h3>
        <p>
          Uma cópia da lista fica no servidor; este aparelho continua com a versão dele. Salvar com um nome
          já usado atualiza aquela lista. Abrir uma lista salva substitui a lista deste aparelho.
        </p>
      </div>

      {current && (
        <div className="saved-lists-save">
          <TextField
            label="Salvar a lista atual como"
            value={name}
            maxLength={80}
            invalid={Boolean(problem)}
            hint={problem ?? "Até 80 caracteres."}
            onChange={(event) => {
              setName(event.target.value);
              setError("");
            }}
          />
          <Button
            variant="primary"
            loading={save.isPending}
            disabled={Boolean(problem) || !current.length}
            onClick={() => save.mutate()}
          >
            {save.isPending ? "Salvando…" : "Salvar na conta"}
          </Button>
        </div>
      )}

      {error && (
        <p className="saved-lists-error" role="alert">
          {error}
        </p>
      )}

      {lists.isPending ? (
        <p className="saved-lists-empty">Carregando suas listas…</p>
      ) : lists.isError ? (
        <div className="saved-lists-empty" role="status">
          <span>Não foi possível carregar as listas da conta agora.</span>
          <Button variant="ghost" size="sm" onClick={() => void lists.refetch()}>
            Tentar novamente
          </Button>
        </div>
      ) : saved.length === 0 ? (
        <p className="saved-lists-empty">Nenhuma lista salva ainda.</p>
      ) : (
        <ul className="saved-lists-items">
          {saved.map((list) => (
            <li key={list.id}>
              <div>
                <strong>{list.name}</strong>
                <small>
                  {itemCount(list.lines.length)} · salva em {accountDate(list.updated_at)}
                </small>
              </div>
              <div className="saved-lists-actions">
                <Button
                  variant="secondary"
                  size="sm"
                  icon={<FolderOpen size={16} aria-hidden="true" />}
                  onClick={() => open(list)}
                  aria-label={`Abrir a lista ${list.name}`}
                >
                  Abrir
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 size={16} aria-hidden="true" />}
                  loading={remove.isPending && remove.variables === list.id}
                  onClick={() => remove.mutate(list.id)}
                  aria-label={`Excluir a lista ${list.name}`}
                >
                  Excluir
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
