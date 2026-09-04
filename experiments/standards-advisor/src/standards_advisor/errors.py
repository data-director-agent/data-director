"""Exceptions.

The rule this module exists to enforce: **an exception means a programmer or configuration
error, never a content outcome.** A recommendation that fails the grounding check, a model
response that will not parse, a registry that returns nothing — those are results, recorded in
`state["failures"]` and in the output document, and the run still completes with a valid
document and exit code 0. §5.5 is explicit that a run which finds nothing is a good run, and a
node that raises at the last stage would destroy the audit trail the run exists to produce.
"""


class StandardsAdvisorError(Exception):
    """Base class, so a caller can distinguish our failures from anyone else's."""


class ConfigError(StandardsAdvisorError):
    """Settings or a configuration file are missing, unreadable or inconsistent."""


class PromptNotFound(StandardsAdvisorError):
    """A prompt named in the manifest is absent, or its content no longer matches its hash.

    Raised rather than tolerated: §5.4 requires the prompt version be recorded with every run,
    which means nothing if the text can drift from the version that names it.
    """


class RegistryUnavailable(StandardsAdvisorError):
    """A registry route cannot answer.

    Deliberately raised by `list_terms` rather than returning an empty list. §5.2 says to fail
    noisily on an unrecognised or unavailable term list rather than quietly drop a filter — an
    empty list would let a caller conclude "the registry has no subjects", which is a very
    different statement from "we could not ask".
    """
