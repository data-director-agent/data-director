/**
 * Reading a response from the app's API, the same way for every endpoint: a body on success, a
 * sign-in check, and a refused request raised with the server's Problem Details.
 */

import type { Problem } from "./run/types";
import { checkSignedIn } from "./session/api";

/** The server refused the request before any run began (a 400 with Problem Details). */
export class RunRefused extends Error {
  constructor(readonly problem: Problem) {
    super(problem.detail ?? problem.title);
  }
}

/**
 * The error an endpoint raises for a status and Problem Details of its own, such as a conflict,
 * or null to fall back on the common ones.
 */
export type Refine = (status: number, problem: Problem | null) => Error | null;

/**
 * The body of `response` as `T`, or the error it carries: `SignedOut` for a 401, what `refine`
 * makes of it, `RunRefused` for a 400 with Problem Details, and otherwise an error in the
 * server's words, or with its status if it gave none.
 */
export async function json<T>(response: Response, refine?: Refine): Promise<T> {
  if (response.ok) return (await response.json()) as T;
  checkSignedIn(response);
  const problem = (await response.json().catch(() => null)) as Problem | null;
  const refined = refine?.(response.status, problem);
  if (refined) throw refined;
  if (response.status === 400 && problem) throw new RunRefused(problem);
  throw new Error(problem?.detail ?? `the server answered ${response.status}`);
}
