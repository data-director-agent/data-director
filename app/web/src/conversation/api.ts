/**
 * The conversation endpoints, behind one interface so tests can stand in for the server.
 *
 * A turn (sent through its stream, `run/transport.ts`, with `turnBody`) sends only the agent, the message, the turn it follows, any inventory attached to it and
 * any answer to the latest turn's choice question, which the harness checks, and any supporting
 * document attached to it:
 * the server builds the history from what it stored (docs/specs/app.md) and refuses one the page
 * sends. An attached inventory or document goes to the conversation's project, never into the message. A turn that does not follow
 * the latest stored turn, or that arrives while another is running, is refused with a 409 and
 * nothing runs (docs/specs/orchestration.md), so a message sent again after a dropped connection is never
 * run twice (#337). A conversation is started in the project the shell is working in, or in a new
 * one (docs/specs/app.md).
 */

import type { FileInventory } from "@data-director/inventory";
import { createContext, useContext } from "react";

import type { Started } from "../api/generated/responses";
import { json, RunRefused } from "../http";
import { SIGNED_OUT, SignedOut } from "../session/api";
import type { Problem } from "../run/types";
import type { AttachedDocument } from "./documentation";
import type { ReplyAnswers } from "./question";
import type { Conversation, ConversationSummary, DeletedConversation } from "./types";

export type { Started } from "../api/generated/responses";

export interface ConversationApi {
  /** Starts a conversation in `projectId`, or in a new project when it is null. */
  create(projectId: string | null, signal?: AbortSignal): Promise<Started>;
  list(signal?: AbortSignal): Promise<ConversationSummary[]>;
  get(conversationId: string, signal?: AbortSignal): Promise<Conversation>;
  /** Delete the conversation, which hides it and erases nothing
   * (`DELETE /api/conversations/{id}`). Answers with until when it may be restored. */
  remove(conversationId: string): Promise<DeletedConversation>;
  /** Restore a deleted conversation within its restore period. */
  restore(conversationId: string): Promise<void>;
  /** The deleted conversations the person may still restore, the one deleted last first. */
  deleted(signal?: AbortSignal): Promise<DeletedConversation[]>;
}

/** The server refused a turn because the conversation has moved on since the page last read it:
 * another turn was stored, or is still running. Nothing was run. */
export class TurnConflict extends Error {
  constructor(readonly problem: Problem) {
    super(problem.detail ?? problem.title);
  }
}

/** A response's body, or its error, with a refused turn raised as `TurnConflict` and a proxy's
 * gateway error as `NoAnswer`. */
function parse<T>(response: Response): Promise<T> {
  return json<T>(response, (status, problem) => {
    if (status === 409 && problem) return new TurnConflict(problem);
    return GATEWAY_ERRORS.includes(status) ? new NoAnswer(status) : null;
  });
}

function init(signal?: AbortSignal): RequestInit {
  return signal ? { signal } : {};
}

/** The request got no HTTP response at all (the browser's `Failed to fetch`), or a proxy answered
 * for the app (`NoAnswer`), so the server may not have received it, or may still be running it. */
export class Unreachable extends Error {
  constructor() {
    super("the server could not be reached");
  }
}

/** What a proxy in front of the app (NGINX, or the Vite dev server) answers when the app gave it
 * no answer in time, or none at all. */
const GATEWAY_ERRORS = [502, 503, 504];

/** A proxy in front of the app answered for it (502, 503 or 504): the app may have received the
 * request and may still be running it, so this is handled as if no response had come. */
export class NoAnswer extends Unreachable {
  constructor(readonly status: number) {
    super();
    this.message = `the server answered ${status} without a reply from Data Director`;
  }
}

/** What a turn sends, the same to `POST …/turns` and, as `forwardedProps`, to its stream: the
 * answer, the inventory and the document only when there is one. */
export function turnBody(
  agentId: string,
  messageText: string,
  follows: string | null,
  inventory: FileInventory | null,
  answer: ReplyAnswers | null,
  document: AttachedDocument | null,
): Record<string, unknown> {
  return {
    agent_id: agentId,
    message_text: messageText,
    follows,
    ...(inventory ? { inventory } : {}),
    ...(answer ? { reply_answers: answer } : {}),
    ...(document
      ? {
          documentation: {
            name: document.name,
            media_type: document.media_type,
            text: document.text,
          },
        }
      : {}),
  };
}

/**
 * Why a turn's stream could not be opened, as the JSON route's errors say it: the AG-UI client
 * gives a refused request's status and Problem Details (`status`, `payload`), and a request that
 * got no response as a `TypeError`.
 */
export function streamFailure(error: unknown): Error {
  if (error instanceof TypeError) return new Unreachable();
  const { status, payload } = (error ?? {}) as { status?: unknown; payload?: unknown };
  if (typeof status !== "number") return error instanceof Error ? error : new Error(String(error));
  const problem =
    typeof payload === "object" && payload !== null && "title" in payload
      ? (payload as Problem)
      : null;
  if (status === 401) {
    window.dispatchEvent(new Event(SIGNED_OUT));
    return new SignedOut();
  }
  if (status === 409 && problem) return new TurnConflict(problem);
  if (GATEWAY_ERRORS.includes(status)) return new NoAnswer(status);
  if (status === 400 && problem) return new RunRefused(problem);
  return new Error(problem?.detail ?? `the server answered ${status}`);
}

/** `fetch`, with a request that got no response raised as `Unreachable`, whichever endpoint. */
async function request(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (e) {
    if (e instanceof TypeError) throw new Unreachable();
    throw e;
  }
}

export const httpConversationApi: ConversationApi = {
  async create(projectId, signal) {
    return parse<Started>(
      await request("/api/conversations", {
        ...init(signal),
        method: "POST",
        headers: { "content-type": "application/json" },
        ...(projectId === null ? {} : { body: JSON.stringify({ project_id: projectId }) }),
      }),
    );
  },
  async list(signal) {
    return parse(await request("/api/conversations", init(signal)));
  },
  async get(conversationId, signal) {
    return parse(await request(conversationPath(conversationId), init(signal)));
  },
  async remove(conversationId) {
    return json(await request(conversationPath(conversationId), changing("DELETE")));
  },
  async restore(conversationId) {
    const response = await request(`${conversationPath(conversationId)}/restore`, changing("POST"));
    if (!response.ok) await json(response);
  },
  async deleted(signal) {
    return json(await request("/api/conversations/deleted", init(signal)));
  },
};

function conversationPath(conversationId: string): string {
  return `/api/conversations/${encodeURIComponent(conversationId)}`;
}

/** A request that changes state, which the server takes only as JSON (#728). */
function changing(method: string): RequestInit {
  return { method, headers: { "content-type": "application/json" } };
}

export const ConversationApiContext = createContext<ConversationApi>(httpConversationApi);

export function useConversationApi(): ConversationApi {
  return useContext(ConversationApiContext);
}
