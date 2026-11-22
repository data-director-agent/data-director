import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import {
  type ConversationApi,
  ConversationApiContext,
} from "../../conversation/api";
import type { DeletedConversation } from "../../conversation/types";
import { DeletedConversations } from "./DeletedConversations";

function deleted(over: Partial<DeletedConversation>): DeletedConversation {
  return {
    conversation_id: "c1",
    project_id: "p1",
    title: "Depositing a soil survey",
    at: "2026-11-18T10:00:00Z",
    by: {
      principal_id: "https://orcid.org/0000-0002-1825-0097",
      name: "Josiah Carberry",
      assurance: "asserted",
    },
    started_by: "https://orcid.org/0000-0002-1825-0097",
    restorable_until: "2026-12-18T10:00:00Z",
    ...over,
  };
}

function fakeApi(
  listed: DeletedConversation[][],
  restore: ConversationApi["restore"] = () => Promise.resolve(),
): ConversationApi {
  let reads = 0;
  return {
    create: () => Promise.reject(new Error("nothing started in these tests")),
    list: () => Promise.resolve([]),
    get: () => Promise.reject(new Error("nothing opened in these tests")),
    remove: () => Promise.reject(new Error("nothing deleted in these tests")),
    restore,
    deleted: () =>
      Promise.resolve(listed[Math.min(reads++, listed.length - 1)] ?? []),
  };
}

function renderSection(api: ConversationApi, onRestored = vi.fn()) {
  return render(
    <ConversationApiContext.Provider value={api}>
      <DeletedConversations projectId="p1" onRestored={onRestored} />
    </ConversationApiContext.Provider>,
  );
}

describe("DeletedConversations", () => {
  it("lists the project's deleted conversations, and restores one", async () => {
    const restore = vi.fn(() => Promise.resolve());
    const onRestored = vi.fn();
    const first = [
      deleted({}),
      deleted({
        conversation_id: "c2",
        project_id: "p2",
        title: "In another project",
      }),
    ];
    const { container } = renderSection(
      fakeApi([first, []], restore),
      onRestored,
    );
    const button = await screen.findByRole("button", {
      name: /^Restore conversation: /,
    });
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(await axe(container)).toHaveNoViolations();

    await userEvent.click(button);
    expect(restore).toHaveBeenCalledWith("c1");
    await waitFor(() => expect(onRestored).toHaveBeenCalledWith("c1"));
    await waitFor(() => expect(screen.queryByRole("heading")).toBeNull());
  });

  it("names a conversation that had no turn", async () => {
    renderSection(fakeApi([[deleted({ title: null })]]));
    expect(
      await screen.findByRole("button", { name: /^Restore conversation: / }),
    ).toBeVisible();
  });

  it("shows nothing while there is nothing to restore", async () => {
    const api = fakeApi([[]]);
    const deletedRead = vi.spyOn(api, "deleted");
    renderSection(api);
    await waitFor(() => expect(deletedRead).toHaveBeenCalled());
    expect(screen.queryByRole("heading")).toBeNull();
  });
});
