/**
 * The conversation endpoints, behind one interface so tests can stand in for the server.
 *
 * A turn sends only the agent and the message: the server builds the history from what it
 * stored (ADR-0024 §17) and refuses one the page sends.
 */

import { createContext, useContext } from "react";

import { RunRefused } from "../run/api";
import type { Problem } from "../run/types";
import type { Conversation, ConversationSummary } from "./types";

export interface ConversationApi {
  create(signal?: AbortSignal): Promise<string>;
  sendTurn(
    conversationId: string,
    agentId: string,
    messageText: string,
    signal?: AbortSignal,
  ): Promise<void>;
  list(signal?: AbortSignal): Promise<ConversationSummary[]>;
  get(conversationId: string, signal?: AbortSignal): Promise<Conversation>;
}

async function json<T>(response: Response): Promise<T> {
  if (response.status === 400) throw new RunRefused((await response.json()) as Problem);
  if (!response.ok) throw new Error(`the server answered ${response.status}`);
  return (await response.json()) as T;
}

function init(signal?: AbortSignal): RequestInit {
  return signal ? { signal } : {};
}

export const httpConversationApi: ConversationApi = {
  async create(signal) {
    const created = await json<{ conversation_id: string }>(
      await fetch("/api/conversations", { ...init(signal), method: "POST" }),
    );
    return created.conversation_id;
  },
  async sendTurn(conversationId, agentId, messageText, signal) {
    await json(
      await fetch(`/api/conversations/${encodeURIComponent(conversationId)}/turns`, {
        ...init(signal),
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ agent_id: agentId, message_text: messageText }),
      }),
    );
  },
  async list(signal) {
    return json(await fetch("/api/conversations", init(signal)));
  },
  async get(conversationId, signal) {
    return json(
      await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`, init(signal)),
    );
  },
};

export const ConversationApiContext = createContext<ConversationApi>(httpConversationApi);

export function useConversationApi(): ConversationApi {
  return useContext(ConversationApiContext);
}
