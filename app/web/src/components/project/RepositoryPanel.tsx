/**
 * The repository chosen for a project, the project's Repository tab, and what the harness resolved
 * it to (docs/specs/deposit.md): the requirement sets by version and digest, what the repository
 * accepts, what Data Director assumes about it, the fields and documents a package for it must or
 * should have, and where those values came from (`RepositoryDetails`). The panel shows them as
 * they are; whether a package meets them is the deposit check's to say.
 *
 * A repository is chosen here, from the deployment's suggestions or a search of the pinned
 * re3data export (`RepositoryPicker`), or from `advisor.repository`'s shortlist in a conversation
 * in this project. Either way only its re3data identifier is sent, and the harness reads the rest
 * from the export. Choosing again changes it: the last choice counts. The panel reads the choice
 * again whenever `revision` changes, and after a choice made in it.
 */

import { MessageSquarePlus } from "lucide-react";
import { useEffect, useState } from "react";

import { type RepositoryRequirements, useProjectApi } from "../../project/api";
import { homePath, navigate } from "../../route";
import { Button } from "../ui/Button";
import { ConvertRecord } from "./ConvertRecord";
import { MetadataStandardChoice } from "./MetadataStandardChoice";
import { RepositoryDetails } from "./RepositoryDetails";
import { RepositoryPicker } from "./RepositoryPicker";

type Load =
  | { state: "loading" }
  | { state: "failed"; message: string }
  | { state: "loaded"; value: RepositoryRequirements | null };

const HEADING_ID = "repository-heading";

export function RepositoryPanel({
  projectId,
  revision,
}: {
  projectId: string;
  revision: number;
}) {
  const api = useProjectApi();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [changing, setChanging] = useState(false);
  // Bumped by a choice of repository made in the panel, so that its standard is read again, and
  // by a choice of standard, so that the requirements it resolved to are.
  const [repositoryChoices, setRepositoryChoices] = useState(0);
  const [standardChoices, setStandardChoices] = useState(0);

  const chosen = (value: RepositoryRequirements) => {
    setLoad({ state: "loaded", value });
    setChanging(false);
    setRepositoryChoices((n) => n + 1);
  };

  useEffect(() => {
    const controller = new AbortController();
    api.repository(projectId, controller.signal).then(
      (value) => setLoad({ state: "loaded", value }),
      (error: unknown) => {
        if (!controller.signal.aborted) {
          setLoad({
            state: "failed",
            message: error instanceof Error ? error.message : String(error),
          });
        }
      },
    );
    return () => controller.abort();
  }, [api, projectId, revision, standardChoices]);

  const identify = (
    <Button
      icon={MessageSquarePlus}
      onPress={() => navigate(homePath({ repository: true }))}
    >
      Start a new chat to identify the target data repository
    </Button>
  );

  const content = () => {
    if (load.state === "loading") return <p>Reading the chosen repository…</p>;
    if (load.state === "failed") {
      return (
        <div role="alert" className="callout status-danger">
          <p>
            Data Director could not read the chosen repository: {load.message}
          </p>
        </div>
      );
    }
    if (load.value === null) {
      return (
        <>
          <p>
            No repository has been chosen yet. Choose one below, or start a new
            chat to identify it.
          </p>
          {identify}
          <RepositoryPicker projectId={projectId} onChosen={chosen} />
        </>
      );
    }
    return (
      <>
        {changing ? (
          <>
            <RepositoryPicker projectId={projectId} onChosen={chosen} />
            <Button variant="quiet" onPress={() => setChanging(false)}>
              Keep the current repository
            </Button>
          </>
        ) : (
          <>
            <Button onPress={() => setChanging(true)}>Change repository</Button>{" "}
            {identify}
          </>
        )}
        <MetadataStandardChoice
          projectId={projectId}
          revision={revision + repositoryChoices}
          onChosen={() => setStandardChoices((n) => n + 1)}
        />
        <RepositoryDetails choice={load.value} />
        <ConvertRecord
          projectId={projectId}
          revision={revision + repositoryChoices}
        />
      </>
    );
  };

  return (
    <section className="repository" aria-labelledby={HEADING_ID}>
      <h2 id={HEADING_ID}>Repository</h2>
      <p className="hint">
        The package is checked against what this repository asks for. To change
        it, choose another here or from a shortlist; the last choice counts.
      </p>
      {content()}
    </section>
  );
}
