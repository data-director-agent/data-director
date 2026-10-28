/** How a value was derived, read from the record's own `recorded_in` field when there is one. */

import type { Derivation } from "../../../manifest/normalise";
import type { DerivationHow } from "../../../manifest/types";
import { DERIVATION, DERIVATION_SHORT } from "../../../manifest/wording";

export function Badge({ derivation, record }: { derivation: Derivation; record: Record<string, unknown> }) {
  const recorded = derivation.recordedIn ? record[derivation.recordedIn] : undefined;
  const how = (typeof recorded === "string" ? recorded : derivation.how) as DerivationHow;
  return (
    <span className="derivation" title={DERIVATION[how] ?? how}>
      {DERIVATION_SHORT[how] ?? how}
    </span>
  );
}
