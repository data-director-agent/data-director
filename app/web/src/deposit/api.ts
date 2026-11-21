/**
 * Depositing a draft through a repository's API, and the person's own repository account, behind
 * one interface so tests can stand in for the servers (docs/specs/deposit.md, Depositing through an
 * API).
 *
 * The app records a person's approval and asks the deposit broker for the draft
 * (`/api/projects/{id}/deposits`). The person's repository token never passes through the app: to
 * connect an account, the page asks the app for a single-use ticket (`POST
 * /api/repository-account/ticket`), which also says where the deposit broker is on this origin, then
 * either sends the browser to the broker to sign in at the repository (OAuth) or sends a pasted
 * token to the broker with the ticket. The broker answers with a label, never the token, or with a
 * reason code in `X-DD-Reason` that `reasonText` puts in plain words.
 */

import { createContext, useContext } from "react";

import type {
  DepositRefusedProblem,
  DepositShown,
  Deposits,
  RepositoryTicket,
} from "../api/generated/responses";
import { ticketed } from "../api/ticketed";
import { checkSignedIn } from "../session/api";

export type { DepositShown, Deposits } from "../api/generated/responses";

/** Nothing was approved or sent; `refusal` says why, and `draftUrl` names an earlier draft. */
export class DepositRefused extends Error {
  readonly refusal: string;
  readonly draftUrl: string | null;

  constructor(problem: DepositRefusedProblem) {
    super(problem.detail);
    this.name = "DepositRefused";
    this.refusal = problem.refusal;
    this.draftUrl = problem.draft_url ?? null;
  }
}

/** The deposit broker refused, with its reason code. */
export class RepositoryAccountRefused extends Error {
  constructor(readonly reason: string) {
    super(reason);
    this.name = "RepositoryAccountRefused";
  }
}

/** What the deposit broker says of the person's account at one repository. */
export interface RepositoryAccount {
  baseUrl: string;
  connected: boolean;
  label?: string;
  method?: "oauth" | "token";
  created?: string;
}

/** One repository the deposit broker serves, and whether it is connected through OAuth. */
export interface RepositoryOption {
  baseUrl: string;
  transport: string;
  oauth: boolean;
}

export interface DepositApi {
  deposits(projectId: string, signal?: AbortSignal): Promise<Deposits>;
  /** Approve the deposit of the package `digest`; answers with the deposit, made or failed. */
  deposit(projectId: string, digest: string): Promise<DepositShown>;
  /** The repositories the deposit broker serves. */
  options(signal?: AbortSignal): Promise<RepositoryOption[]>;
  account(baseUrl: string, signal?: AbortSignal): Promise<RepositoryAccount>;
  /** Send the browser to the repository to sign in and approve depositing (OAuth). */
  connect(transport: string, baseUrl: string): Promise<void>;
  /** Keep a personal token, which the broker checks first. */
  saveToken(baseUrl: string, token: string): Promise<RepositoryAccount>;
  disconnect(baseUrl: string): Promise<void>;
}

const BY_HAND =
  "This deployment does not deposit to this repository for you. Deposit by hand, as the steps below say.";
const UNREACHABLE =
  "The repository could not be reached. Nothing was published. Try again in a few minutes.";
const STALE =
  "The project has changed since this package was built. Build the package again, then deposit it.";
const TOO_LONG = "The request took too long. Try again.";

const REASONS: Record<string, string> = {
  "account-missing":
    "You have not connected your repository account yet. Connect it on the Settings page, then try again.",
  "account-rejected":
    "The repository did not accept your account. It may have been disconnected or the token revoked: connect it again on the Settings page.",
  "item-rejected":
    "The repository refused the metadata. Check the approved metadata record, or deposit by hand.",
  "target-unknown":
    "The repository does not know the community or collection this deployment deposits to. Tell the deployment's operator.",
  "repository-unavailable": UNREACHABLE,
  "broker-unavailable": UNREACHABLE,
  "already-deposited": "This package has already been deposited in the repository.",
  "transport-not-offered": BY_HAND,
  "transport-not-installed": BY_HAND,
  "deposit-broker-unset": BY_HAND,
  "by-hand": BY_HAND,
  "not-latest-package": STALE,
  "package-stale": STALE,
  "ticket-expired": TOO_LONG,
  "ticket-used": TOO_LONG,
  "ticket-invalid": TOO_LONG,
  "base-url-not-allowed": "This deployment may not send your account to that repository.",
  "body-invalid": "That does not look like a token. Paste the whole token, with no spaces.",
};

/** A refusal code, from the app or the deposit broker, in words a person can act on. */
export function reasonText(reason: string): string {
  return REASONS[reason] ?? "Something went wrong, and nothing was changed. Try again.";
}

// The app refuses a request that changes state unless it declares JSON, body or not (#728).
const JSON_HEADERS = { "content-type": "application/json" };
const REASON_HEADER = "x-dd-reason";

function depositsPath(projectId: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/deposits`;
}

async function ticket(): Promise<RepositoryTicket> {
  const response = await fetch("/api/repository-account/ticket", {
    method: "POST",
    headers: JSON_HEADERS,
  });
  checkSignedIn(response);
  if (!response.ok) throw new Error(`the server answered ${response.status}`);
  return (await response.json()) as RepositoryTicket;
}

async function broker(
  method: string,
  query: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<Response> {
  const issued = await ticket();
  const url = `${issued.deposit_broker_url}/connect/account?${query}`;
  const response = await ticketed(url, issued.ticket, method, body, signal);
  if (!response.ok) {
    throw new RepositoryAccountRefused(response.headers.get(REASON_HEADER) ?? "broker-error");
  }
  return response;
}

interface RawAccount {
  base_url: string;
  connected: boolean;
  label?: string;
  method?: "oauth" | "token";
  created?: string;
}

function account(raw: RawAccount): RepositoryAccount {
  return {
    baseUrl: raw.base_url,
    connected: raw.connected,
    ...(raw.label ? { label: raw.label } : {}),
    ...(raw.method ? { method: raw.method } : {}),
    ...(raw.created ? { created: raw.created } : {}),
  };
}

export const httpDepositApi: DepositApi = {
  async deposits(projectId, signal) {
    const response = await fetch(depositsPath(projectId), signal ? { signal } : {});
    checkSignedIn(response);
    if (!response.ok) throw new Error(`the server answered ${response.status}`);
    return (await response.json()) as Deposits;
  },
  async deposit(projectId, digest) {
    const response = await fetch(depositsPath(projectId), {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ digest }),
    });
    checkSignedIn(response);
    if (response.status === 409) {
      throw new DepositRefused((await response.json()) as DepositRefusedProblem);
    }
    if (!response.ok) throw new Error(`the server answered ${response.status}`);
    return (await response.json()) as DepositShown;
  },
  async options(signal) {
    const issued = await ticket();
    const response = await fetch(
      `${issued.deposit_broker_url}/connect/options`,
      signal ? { signal } : {},
    );
    if (!response.ok) throw new Error(`the deposit broker answered ${response.status}`);
    const raw = (await response.json()) as {
      repositories: { base_url: string; transport: string; oauth: boolean }[];
    };
    return raw.repositories.map((r) => ({
      baseUrl: r.base_url,
      transport: r.transport,
      oauth: r.oauth,
    }));
  },
  async account(baseUrl, signal) {
    const query = new URLSearchParams({ base_url: baseUrl }).toString();
    return account((await (await broker("GET", query, undefined, signal)).json()) as RawAccount);
  },
  async connect(transport, baseUrl) {
    // A top-level form post, so that the broker can send the browser on to the repository and
    // the ticket travels in the body, not the address.
    const issued = await ticket();
    const form = document.createElement("form");
    form.method = "POST";
    form.action = `${issued.deposit_broker_url}/connect/${encodeURIComponent(transport)}/start`;
    form.hidden = true;
    for (const [name, value] of [
      ["ticket", issued.ticket],
      ["base_url", baseUrl],
    ] as const) {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = name;
      input.value = value;
      form.append(input);
    }
    document.body.append(form);
    form.submit();
  },
  async saveToken(baseUrl, token) {
    const query = new URLSearchParams({ base_url: baseUrl }).toString();
    const body = { base_url: baseUrl, token };
    return account((await (await broker("PUT", query, body)).json()) as RawAccount);
  },
  async disconnect(baseUrl) {
    await broker("DELETE", new URLSearchParams({ base_url: baseUrl }).toString());
  },
};

export const DepositApiContext = createContext<DepositApi>(httpDepositApi);

export function useDepositApi(): DepositApi {
  return useContext(DepositApiContext);
}
