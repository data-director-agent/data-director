/**
 * Where the project's documentation site describes an agent. Every in-tree agent has a page at
 * `agents/<package directory>/`, and a directory is its agent's id with the dot written as a
 * hyphen (`advisor.dmp` is `agents/advisor-dmp/`, as `mkdocs.yml` lists it). An agent from
 * outside the tree has no page there, so this names where the page would be, not that it exists.
 */

const SITE = "https://data-director-agent.github.io/data-director/";

/** The documentation page for the agent `id`. */
export function agentDocsUrl(id: string): string {
  return `${SITE}agents/${id.replaceAll(".", "-")}/`;
}
