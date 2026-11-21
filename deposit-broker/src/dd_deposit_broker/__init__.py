"""The deposit broker: holds each researcher's own repository token, sealed, and creates a draft
deposit for the harness when it presents a deposit grant (docs/specs/deposit.md, Depositing through
an API; docs/guide/operations/deposit-broker.md).

It imports the SDK and nothing else of the workspace, and nothing imports it. The app and the
harness never see a token: the browser connects an account here directly, through the reverse
proxy, and the harness asks for a draft on the broker's loopback address.
"""
