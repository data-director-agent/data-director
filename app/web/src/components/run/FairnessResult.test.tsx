import { render, screen } from "@testing-library/react";

import { FAIRNESS_CLASS } from "../../project/fairness";
import { aReport } from "../../test/fairness";
import { ResultView } from "./ResultView";

describe("a FAIR report in a run card", () => {
  it("is laid out by its class, whichever agent returned it", () => {
    render(
      <ResultView
        payload={{ ...aReport() }}
        schema={undefined}
        className={FAIRNESS_CLASS}
        derivations={[]}
        evidence={[]}
        idPrefix="run"
      />,
    );
    expect(screen.getAllByRole("meter").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
