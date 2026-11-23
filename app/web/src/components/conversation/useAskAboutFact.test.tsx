import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";

import fixture from "../../../fixtures/project-facts.json";
import { type FactsApi, FactsApiContext, type ProjectFacts } from "../../project/facts";
import { homePath } from "../../route";
import { describeFact } from "../project/factWording";
import { askAboutFact, useAskAboutFact } from "./useAskAboutFact";

// Two proposals from the files check (app/tests/test_project_facts.py): the first with a reason.
const OFFERED = fixture as ProjectFacts;
const [WITH_REASON, WITHOUT_REASON] = OFFERED.proposals;
if (!WITH_REASON?.fact.proposed_because || !WITHOUT_REASON) throw new Error("the fixture changed");
const PROJECT = "01900000-0000-7000-8000-000000000001";

function ask(fact: string, projectId: string | null = PROJECT) {
  history.replaceState(null, "", homePath({ fact }));
  const facts = vi.fn<FactsApi["facts"]>(() => Promise.resolve(OFFERED));
  const api: FactsApi = { facts, decideFact: () => Promise.reject(new Error("not here")) };
  const setText = vi.fn();
  const box = { current: document.createElement("textarea") };
  const wrapper = ({ children }: { children: ReactNode }) => (
    <FactsApiContext.Provider value={api}>{children}</FactsApiContext.Provider>
  );
  renderHook(() => useAskAboutFact(projectId, { setText, box, keep: { conversation: null, run: null } }), {
    wrapper,
  });
  return { setText, facts };
}

describe("askAboutFact", () => {
  it("states the fact, who proposed it and why", () => {
    const text = askAboutFact(WITH_REASON);
    expect(text).toContain(describeFact(WITH_REASON.fact));
    expect(text).toContain(WITH_REASON.agent_id);
    expect(text).toContain(WITH_REASON.fact.proposed_because);
  });

  it("states who proposed a fact that gives no reason", () => {
    const text = askAboutFact(WITHOUT_REASON);
    expect(text).toContain(describeFact(WITHOUT_REASON.fact));
    expect(text).toContain(WITHOUT_REASON.agent_id);
    expect(text).not.toContain("because");
  });
});

describe("useAskAboutFact", () => {
  it("puts the proposal in the message box once the facts are read, then drops it from the address", async () => {
    const { setText } = ask(WITH_REASON.proposal);
    await waitFor(() => expect(setText).toHaveBeenCalledTimes(1));
    expect(setText).toHaveBeenCalledWith(askAboutFact(WITH_REASON));
    await waitFor(() => expect(location.search).toBe(""));
  });

  it("ignores a proposal no longer waiting for a decision", async () => {
    const { setText, facts } = ask("01900000-0000-7000-8000-00000000ffff");
    await waitFor(() => expect(location.search).toBe(""));
    expect(facts).toHaveBeenCalled();
    expect(setText).not.toHaveBeenCalled();
  });

  it("reads no facts when none is asked about", () => {
    history.replaceState(null, "", homePath({}));
    const facts = vi.fn<FactsApi["facts"]>(() => Promise.resolve(OFFERED));
    const api: FactsApi = { facts, decideFact: () => Promise.reject(new Error("not here")) };
    const wrapper = ({ children }: { children: ReactNode }) => (
      <FactsApiContext.Provider value={api}>{children}</FactsApiContext.Provider>
    );
    renderHook(() => useAskAboutFact(PROJECT, { setText: vi.fn(), box: { current: null }, keep: { conversation: null, run: null } }), {
      wrapper,
    });
    expect(facts).not.toHaveBeenCalled();
  });
});
