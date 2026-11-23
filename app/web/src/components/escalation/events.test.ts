import transferredFixture from "../../../fixtures/escalation-transferred.json";
import type { Escalation } from "../../project/escalations";
import { eventSaid, stewardEvents } from "./events";

const TRANSFERRED = transferredFixture as Escalation;

describe("a request passed between data stewards, as its researchers read it", () => {
  it("names the team a transfer sent it to", () => {
    const events = stewardEvents([TRANSFERRED], []);
    const moved = events.find((event) => event.kind === "transfer");
    if (!moved) throw new Error("no transfer");
    expect(moved.fromSteward).toBe(true);
    expect(moved.target).toBe(TRANSFERRED.team_name);
    expect(eventSaid(moved)).toContain(TRANSFERRED.team_name);
  });

  it("names the colleague a reassignment passed it to", () => {
    const colleague = { ...TRANSFERRED.opened_by, name: "Grace Example" };
    const [opened] = TRANSFERRED.history;
    if (!opened) throw new Error("no history");
    const reassigned: Escalation = {
      ...TRANSFERRED,
      history: [
        ...TRANSFERRED.history,
        { ...opened, move: "reassign", acting_as: "steward", to_steward: colleague },
      ],
    };
    const moved = stewardEvents([reassigned], []).find((event) => event.kind === "reassign");
    expect(moved?.target).toBe(colleague.name);
  });
});
