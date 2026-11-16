/**
 * Choosing a project's repository on its page (docs/specs/deposit.md). The combo box offers the
 * repositories the deployment suggests until something is typed, then searches the pinned re3data
 * export by name, re3data identifier, re3data DOI or URL (`GET /api/repositories`). The same text
 * always finds the same repositories. **Choose repository** records the one selected by its re3data
 * identifier alone, as a choice from an advisor's shortlist does; the last choice counts.
 */

import "./RepositoryPicker.css";

import { ChevronDown } from "lucide-react";
import { useEffect, useId, useState } from "react";
import {
  Button as AriaButton,
  ComboBox,
  Input,
  Label,
  ListBox,
  ListBoxItem,
  Popover,
  Text,
} from "react-aria-components";

import {
  type RepositoryMatch,
  type RepositoryRequirements,
  useProjectApi,
} from "../../project/api";
import { errorMessage } from "../../run/api";
import { Button } from "../ui/Button";

/** How long typing must pause before the export is searched. */
export const SEARCH_DELAY_MS = 250;

type Found =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; suggested: boolean; repositories: RepositoryMatch[] };

function detail(repository: RepositoryMatch): string {
  return [repository.additional_names[0], repository.url, repository.re3data_id]
    .filter(Boolean)
    .join(" · ");
}

export function RepositoryPicker({
  projectId,
  onChosen,
}: {
  projectId: string;
  onChosen: (requirements: RepositoryRequirements) => void;
}) {
  const api = useProjectApi();
  const hintId = useId();
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Found>({ state: "loading" });
  const [selected, setSelected] = useState<RepositoryMatch | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const search = () =>
      api.searchRepositories(query, controller.signal).then(
        (result) =>
          setFound({
            state: "loaded",
            suggested: result.suggested,
            repositories: result.repositories,
          }),
        (e: unknown) => {
          if (!controller.signal.aborted) setFound({ state: "failed", message: errorMessage(e) });
        },
      );
    // The suggestions are read at once; a search waits for typing to pause.
    const timer = setTimeout(() => void search(), query.trim() ? SEARCH_DELAY_MS : 0);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [api, query]);

  const repositories = found.state === "loaded" ? found.repositories : [];

  async function choose() {
    if (selected === null) return;
    setPending(true);
    setError(null);
    try {
      onChosen(await api.chooseRepository(projectId, selected.re3data_id));
    } catch (e) {
      setError(`Data Director could not record ${selected.name} as your repository: ${errorMessage(e)}`);
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="repository-picker">
      <ComboBox
        className="repository-picker-combobox"
        items={repositories}
        inputValue={query}
        onInputChange={(value) => {
          setQuery(value);
          if (selected !== null && value !== selected.name) setSelected(null);
        }}
        selectedKey={selected?.re3data_id ?? null}
        onSelectionChange={(key) => {
          const match = repositories.find((r) => r.re3data_id === key) ?? null;
          setSelected(match);
          if (match !== null) setQuery(match.name);
        }}
        menuTrigger="focus"
        allowsEmptyCollection
        // The server has already filtered; the combo box shows what it found as it is.
        defaultFilter={() => true}
        aria-describedby={hintId}
      >
        <Label className="repository-picker-label">Find a repository</Label>
        <div className="repository-picker-field">
          <Input className="repository-picker-input" />
          <AriaButton
            className="button button-secondary repository-picker-toggle"
            aria-label="Show repositories"
          >
            <ChevronDown className="button-icon" size="1.125em" aria-hidden="true" />
          </AriaButton>
        </div>
        <Popover className="repository-picker-popover">
          <ListBox<RepositoryMatch>
            className="repository-picker-list"
            renderEmptyState={() => (
              <p className="repository-picker-empty">
                {found.state === "loading"
                  ? "Searching…"
                  : found.state === "failed"
                    ? `Repositories cannot be searched: ${found.message}`
                    : "No repository in re3data matches that."}
              </p>
            )}
          >
            {(repository) => (
              <ListBoxItem
                id={repository.re3data_id}
                textValue={repository.name}
                className="repository-picker-option"
              >
                <Text slot="label">{repository.name}</Text>
                <Text slot="description" className="muted">
                  {detail(repository)}
                </Text>
              </ListBoxItem>
            )}
          </ListBox>
        </Popover>
      </ComboBox>
      <p id={hintId} className="hint">
        {found.state === "loaded" && found.suggested
          ? "Suggested by this deployment. Type a name, a re3data identifier (r3d…), its re3data DOI or the repository’s web address to search re3data."
          : "Searching re3data by name, re3data identifier (r3d…), re3data DOI or web address."}
      </p>
      {found.state === "failed" && (
        <div role="alert" className="callout status-danger">
          <p>Repositories cannot be searched: {found.message}</p>
        </div>
      )}
      <Button
        variant="primary"
        isDisabled={selected === null || pending}
        onPress={() => void choose()}
      >
        {pending ? "Choosing…" : "Choose repository"}
      </Button>
      {error && (
        <div role="alert" className="callout status-danger">
          <p>{error}</p>
        </div>
      )}
    </div>
  );
}
