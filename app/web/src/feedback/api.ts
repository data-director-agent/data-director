/**
 * The build's identity and the problem report endpoint, behind one interface so tests can stand
 * in for the server (docs/specs/app.md).
 *
 * A refused report (a 400) carries Problem Details like a refused run; a 429 or 502 is shown to
 * the reporter in the server's words.
 */

import { createContext, useContext } from "react";

import type { About, FiledIssue } from "../api/generated/responses";
import { json } from "../http";

export type { About, FiledIssue } from "../api/generated/responses";

export type FeedbackKind = "bug" | "feature" | "other";

export interface Report {
  kind: FeedbackKind;
  title: string;
  description: string;
  page?: string;
  run?: string;
  conversation?: string;
  include_context: boolean;
}

export interface FeedbackApi {
  about(signal?: AbortSignal): Promise<About>;
  send(report: Report, signal?: AbortSignal): Promise<FiledIssue>;
}

/** The build as one line: `v0.3.0-alpha.1 (abc1234)`, or what is known of it. */
export function describeBuild(about: Pick<About, "app_version" | "commit">): string {
  const version = about.app_version ? `v${about.app_version}` : "unknown version";
  return about.commit ? `${version} (${about.commit.slice(0, 7)})` : version;
}

export const httpFeedbackApi: FeedbackApi = {
  async about(signal) {
    return json(await fetch("/api/about", signal ? { signal } : {}));
  },
  async send(report, signal) {
    return json(
      await fetch("/api/feedback", {
        ...(signal ? { signal } : {}),
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(report),
      }),
    );
  },
};

export const FeedbackApiContext = createContext<FeedbackApi>(httpFeedbackApi);

export function useFeedbackApi(): FeedbackApi {
  return useContext(FeedbackApiContext);
}
