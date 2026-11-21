/**
 * Where a person reads a repository's registry record, from the identifier it was chosen by
 * (docs/specs/deposit.md): its re3data page, or, for one re3data does not list, its DataCite
 * repository record.
 */
export function registryRecord(repositoryId: string): { url: string; registry: "re3data" | "DataCite" } {
  return /^r3d\d{9}$/.test(repositoryId)
    ? { url: `https://www.re3data.org/repository/${encodeURIComponent(repositoryId)}`, registry: "re3data" }
    : { url: `https://api.datacite.org/repositories/${encodeURIComponent(repositoryId)}`, registry: "DataCite" };
}
