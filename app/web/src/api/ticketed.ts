/**
 * A request to a broker on this origin with a single-use ticket the app issued as the bearer token:
 * the model broker's enrolment interface (`model-account/api.ts`) and the deposit broker's account
 * interface (`deposit/api.ts`). The ticket names the person; nothing else of theirs is sent.
 */

const JSON_HEADERS = { "content-type": "application/json" };

export function ticketed(
  url: string,
  ticket: string,
  method: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<Response> {
  return fetch(url, {
    ...(signal ? { signal } : {}),
    method,
    headers: {
      authorization: `Bearer ${ticket}`,
      ...(body === undefined ? {} : JSON_HEADERS),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}
