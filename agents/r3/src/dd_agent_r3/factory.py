"""Factory and console script for R3.

R3 predates the generalised agent interface (`AgentSpec`, polymorphic input and payload, declared
grounding mode) and has not yet been ported. `build` raises, so `dd-r3 serve` exits without
serving, and the workbench records R3 as unavailable because its card cannot be read. Its tests
are xfailed for the same reason.

TODO: port R3. The work is (1) an `AgentSpec` with `accepts=(DatasetProfile,)`, mode `retrieval`,
`payload_type=Recommendations`; (2) `grounded_on` on `Recommendations` and each `Recommendation`
(replacing `evidence_hashes`); (3) reading `DD_R3_RETRIEVAL`, `DD_R3_EXPLAINER`, `DD_MODEL_ID` and
`DD_SNAPSHOT_PATH` here; (4) an RJSF fragment for the payload. The pre-port wiring is in git
history (`settings.build_r3`, commit adb1dfa).
"""

from __future__ import annotations

from typing import NoReturn

from dd_sdk import serve


def build() -> NoReturn:
    raise NotImplementedError("TODO: R3 is not yet ported to the generalised agent interface")


def main() -> int:
    """Console script: serve R3 over A2A. Exits with the TODO until R3 is ported."""
    return serve.main(build)
