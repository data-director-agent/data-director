/** Problem types (docs/specs/contract.md): each is a URI under the project's problem namespace. */

const PROBLEM_BASE = "https://w3id.org/data-director/problems/";

/** The problem type's last segment, such as `input-not-accepted`, or null. */
export function problemSlug(type: string | undefined | null): string | null {
  if (!type) return null;
  return type.startsWith(PROBLEM_BASE) ? type.slice(PROBLEM_BASE.length) : type;
}
