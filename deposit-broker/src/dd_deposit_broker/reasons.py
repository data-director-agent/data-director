"""Refusals: a status and a reason code (`dd_sdk.deposit_grant.DepositReason`), sent in
`X-DD-Reason`. Never a message that might quote a token, an item or a repository's answer."""

from __future__ import annotations

from dd_sdk.deposit_grant import DepositReason


class Refused(Exception):  # noqa: N818 - a refusal, not an error in the broker
    def __init__(self, status: int, reason: DepositReason) -> None:
        super().__init__(reason.value)
        self.status = status
        self.reason = reason
