import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import {
  type ConversationApi,
  ConversationApiContext,
} from "../../conversation/api";
import type {
  ConversationSummary,
  DeletedConversation,
} from "../../conversation/types";
import { EarlierConversations } from "./EarlierConversations";

const SUMMARY: ConversationSummary = {
  conversation_id: "c1",
  project_id: "p1",
  agent_id: "orchestrator.model",
  title: "Depositing a soil survey",
  title_source: "model",
  turns: 2,
  started_at: "2026-01-01T09:30:00Z",
};

const DELETED: DeletedConversation = {
  conversation_id: "c1",
  project_id: "p1",
  title: SUMMARY.title,
  at: "2026-11-18T10:00:00Z",
  by: { principal_id: "https://orcid.org/0000-0002-1825-0097" },
  restorable_until: "2026-12-18T10:00:00Z",
};

function fakeApi(remove: ConversationApi["remove"]): ConversationApi {
  return {
    create: () => Promise.reject(new Error("nothing started in these tests")),
    list: () => Promise.resolve([]),
    get: () => Promise.reject(new Error("nothing opened in these tests")),
    remove,
    restore: () => Promise.resolve(),
    deleted: () => Promise.resolve([]),
  };
}

function renderList(api: ConversationApi, onDeleted: (id: string) => void) {
  return render(
    <ConversationApiContext.Provider value={api}>
      <EarlierConversations
        conversations={[SUMMARY]}
        onOpen={() => undefined}
        onDeleted={onDeleted}
        restoreDays={30}
      />
    </ConversationApiContext.Provider>,
  );
}

describe("DeleteConversation", () => {
  it("deletes a conversation once the person confirms in the dialog", async () => {
    const remove = vi.fn(() => Promise.resolve(DELETED));
    const onDeleted = vi.fn();
    const { container } = renderList(fakeApi(remove), onDeleted);
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(
      screen.getByRole("button", { name: /^Delete conversation: / }),
    );
    const dialog = screen.getByRole("dialog", { name: "Delete conversation" });
    expect(dialog).toHaveTextContent(SUMMARY.title);
    expect(remove).not.toHaveBeenCalled();

    await userEvent.click(
      screen.getByRole("button", { name: "Delete conversation" }),
    );
    expect(remove).toHaveBeenCalledWith("c1");
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("c1"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("keeps the conversation, and says why, when the server refuses", async () => {
    const onDeleted = vi.fn();
    renderList(
      fakeApi(() => Promise.reject(new Error("no"))),
      onDeleted,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /^Delete conversation: / }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Delete conversation" }),
    );
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("offers no delete where the list is given no way to report one", () => {
    render(
      <EarlierConversations
        conversations={[SUMMARY]}
        onOpen={() => undefined}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /^Delete conversation/ }),
    ).toBeNull();
  });
});
