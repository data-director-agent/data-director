/**
 * What to say when the server refused a request with no words of its own. A 502 or 503 from the
 * proxy means the app is not answering, as while it restarts for a deployment (#900): the person
 * is still signed in and only needs to try again.
 */

const RESTARTING = [502, 503];

export function serverAnswered(status: number): string {
  return RESTARTING.includes(status)
    ? `Data Director is restarting or unavailable (the server answered ${status}): try again in a minute`
    : `the server answered ${status}`;
}
