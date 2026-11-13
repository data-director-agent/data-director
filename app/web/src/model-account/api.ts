/**
 * A person's own model account, behind one interface so tests can stand in for the servers
 * (docs/specs/model-accounts.md, Enrolment).
 *
 * The key goes from this page straight to the model broker and never to the app. For each request
 * the page first asks the app for a single-use enrolment ticket (`POST /api/model-account/ticket`),
 * which also says where the broker is on this origin, then sends the request to the broker with
 * the ticket as a bearer token. The broker answers with the account's label (never the key) and
 * the person's token use, or with a reason code that `reasonText` puts in plain words.
 */

import { createContext, useContext } from "react";

import { checkSignedIn } from "../session/api";

export interface AccountLabel {
  provider: string;
  /** The provider, the account's name if the provider gives one, and the key's last four characters. */
  label: string;
  /** When the key was added (ISO 8601). */
  created: string;
}

export interface TokenUse {
  day: string;
  payer: "own" | "deployment";
  provider: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
}

export interface ModelAccount {
  account: AccountLabel | null;
  usage: TokenUse[];
}

export interface RawModelAccount {
  account: AccountLabel | null;
  usage: {
    day: string;
    payer: "own" | "deployment";
    provider: string;
    model: string;
    input_tokens: number;
    output_tokens: number;
  }[];
}

export interface Ticket {
  ticket: string;
  broker_url: string;
  expires_at: string;
}

/** The broker refused or failed, with its reason code. */
export class AccountRefused extends Error {
  constructor(readonly reason: string) {
    super(reason);
  }
}

export interface ModelAccountApi {
  read(signal?: AbortSignal): Promise<ModelAccount>;
  enrol(provider: string, key: string): Promise<ModelAccount>;
  remove(): Promise<void>;
}

export function fromRaw(raw: RawModelAccount): ModelAccount {
  return {
    account: raw.account,
    usage: raw.usage.map((row) => ({
      day: row.day,
      payer: row.payer,
      provider: row.provider,
      model: row.model,
      inputTokens: row.input_tokens,
      outputTokens: row.output_tokens,
    })),
  };
}

/** A broker reason code in plain words, for the person to act on. */
export function reasonText(reason: string): string {
  switch (reason) {
    case "model-account-rejected":
      return "The provider did not accept this key. Check that you copied all of it and that it has not been revoked.";
    case "model-account-limit":
      return "The provider says this account has reached a rate or spending limit. Try again later, or check the account’s limits with the provider.";
    case "provider-unreachable":
    case "provider-error":
      return "The provider could not be reached to check the key. Nothing was saved. Try again in a few minutes.";
    case "ticket-expired":
    case "ticket-used":
      return "The request took too long. Try again.";
    case "account-unsupported":
      return "This provider is not supported here yet.";
    case "request-invalid":
      return "That does not look like an API key. Paste the whole key, with no spaces.";
    default:
      return "Something went wrong, and nothing was changed. Try again.";
  }
}

// The app refuses a request that changes state unless it declares JSON, body or not (#728).
const JSON_HEADERS = { "content-type": "application/json" };

async function ticket(signal?: AbortSignal): Promise<Ticket> {
  const response = await fetch("/api/model-account/ticket", {
    ...(signal ? { signal } : {}),
    method: "POST",
    headers: JSON_HEADERS,
  });
  checkSignedIn(response);
  if (!response.ok) throw new Error(`the server answered ${response.status}`);
  return (await response.json()) as Ticket;
}

async function broker(method: string, body?: unknown, signal?: AbortSignal): Promise<Response> {
  const issued = await ticket(signal);
  const response = await fetch(`${issued.broker_url}/enrolment/account`, {
    ...(signal ? { signal } : {}),
    method,
    headers: {
      authorization: `Bearer ${issued.ticket}`,
      ...(body === undefined ? {} : JSON_HEADERS),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const refused = (await response.json().catch(() => null)) as { reason?: string } | null;
    throw new AccountRefused(refused?.reason ?? "broker-error");
  }
  return response;
}

export const httpModelAccountApi: ModelAccountApi = {
  async read(signal) {
    return fromRaw((await (await broker("GET", undefined, signal)).json()) as RawModelAccount);
  },
  async enrol(provider, key) {
    return fromRaw((await (await broker("PUT", { provider, key })).json()) as RawModelAccount);
  },
  async remove() {
    await broker("DELETE");
  },
};

export const ModelAccountApiContext = createContext<ModelAccountApi>(httpModelAccountApi);

export function useModelAccountApi(): ModelAccountApi {
  return useContext(ModelAccountApiContext);
}
