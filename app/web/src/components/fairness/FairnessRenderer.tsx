/**
 * The renderer `PayloadView` uses for a `FairnessReport`, recognised by its class and not by the
 * agent that returned it (docs/specs/app.md): the report laid out as on the project's FAIR feedback
 * tab, without a question to ask, since a run card is a record of what was said.
 */

import type { PayloadRendererProps } from "@data-director/agent-view/react";

import { readFairness } from "../../project/fairness";
import { FairnessReportView } from "./FairnessReportView";

export function FairnessRenderer({ payload }: PayloadRendererProps) {
  const report = readFairness(payload);
  if (!report)
    return <pre className="json-view">{JSON.stringify(payload, null, 2)}</pre>;
  return <FairnessReportView report={report} />;
}
