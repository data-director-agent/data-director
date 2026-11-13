/**
 * The conversation endpoints, behind one interface so tests can stand in for the server.
 *
 * A turn sends only the agent, the message, the turn it follows, any inventory attached to it and
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

import { RunRefused } from "../run/api";
import type { Problem } from "../run/types";
import { checkSignedIn } from "../session/api";
import type { AttachedDocument } from "./documentation";
import type { ReplyAnswers } from "./question";
import type { Conversation, ConversationSummary } from "./types";

/** A conversation the server started, and the project it was started in, if it keeps them. */
export interface Started {
  conversation_id: string;
  project_id: string | null;
}

export interface ConversationApi {
  /** Starts a conversation in `projectId`, or in a new project when it is null. */
  create(projectId: string | null, signal?: AbortSignal): Promise<Started>;
  sendTurn(
    conversationId: string,
    agentId: string,
    messageText: string,
    follows: string | null,
    inventory?: FileInventory | null,
    signal?: AbortSignal,
    answer?: ReplyAnswers | null,
    document?: AttachedDocument | null,
  ): Promise<void>;
  list(signal?: AbortSignal): Promise<ConversationSummary[]>;
  get(conversationId: string, signal?: AbortSignal): Promise<Conversation>;
}

/** The server refused a turn because the conversation has moved on since the page last read it:
 * another turn was stored, or is still running. Nothing was run. */
export class TurnConflict extends Error {
  constructor(readonly problem: Problem) {
    super(problem.detail ?? problem.title);
  }
}

async function json<T>(response: Response): Promise<T> {
  checkSignedIn(response);
  if (response.status === 400) throw new RunRefused((await response.json()) as Problem);
  if (response.status === 409) throw new TurnConflict((await response.json()) as Problem);
  if (!response.ok) throw new Error(`the server answered ${response.status}`);
  return (await response.json()) as T;
}

function init(signal?: AbortSignal): RequestInit {
  return signal ? { signal } : {};
}

/** The request got no HTTP response at all (the browser's `Failed to fetch`), so the server may
 * not have received it. */
export class Unreachable extends Error {
  constructor() {
    super("the server could not be reached");
  }
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
    const created = await json<{ conversation_id: string; project_id?: string | null }>(
      await request("/api/conversations", {
        ...init(signal),
        method: "POST",
        headers: { "content-type": "application/json" },
        ...(projectId === null ? {} : { body: JSON.stringify({ project_id: projectId }) }),
      }),
    );
    return { conversation_id: created.conversation_id, project_id: created.project_id ?? null };
  },
  async sendTurn(conversationId, agentId, messageText, follows, inventory, signal, answer, document) {
    await json(
      await request(`/api/conversations/${encodeURIComponent(conversationId)}/turns`, {
        ...init(signal),
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
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
        }),
      }),
    );
  },
  async list(signal) {
    return json(await request("/api/conversations", init(signal)));
  },
  async get(conversationId, signal) {
    return json(
      await request(`/api/conversations/${encodeURIComponent(conversationId)}`, init(signal)),
    );
  },
};

export const ConversationApiContext = createContext<ConversationApi>(httpConversationApi);

export function useConversationApi(): ConversationApi {
  return useContext(ConversationApiContext);
}
