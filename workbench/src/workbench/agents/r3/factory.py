"""Entry-point factory for R3.

R3 predates the generalised agent interface (`AgentSpec`, polymorphic input and payload, declared
grounding mode) and has not yet been ported. The registry records it as unavailable rather than
loading an agent that would fail the conductor's checks. Its tests are xfailed for the same
reason.

TODO: port R3. The work is (1) an `AgentSpec` with `accepts=(DatasetProfile,)`, mode `retrieval`,
`payload_type=Recommendations`; (2) `grounded_on` on `Recommendations` and each `Recommendation`
(replacing `evidence_hashes`); (3) reading `DD_R3_RETRIEVAL`, `DD_R3_EXPLAINER`, `DD_MODEL_ID` and
`DD_SNAPSHOT_PATH` here instead of in `settings.py`; (4) an RJSF fragment for the payload. The
pre-port wiring is in git history (`settings.build_r3`, commit adb1dfa).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from workbench.settings import Settings


def build(settings: Settings) -> NoReturn:
    raise NotImplementedError("TODO: R3 is not yet ported to the generalised agent interface")
