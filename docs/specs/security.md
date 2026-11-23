# Security baseline

## Intent and scope

Blueprint requirement C1 asks for encryption in transit and at rest, access that is role-based,
token-verified and auditable, and a recognised framework as the compliance baseline. This spec is
that baseline for Data Director. It lists each control the project relies on, maps it to
**NIST SP 800-53 Rev. 5**, and says whether the control is met, partly met, left to the
deployment, or open, and what shows it.

The scope is the harness and what it depends on to keep a record safe: the model broker, agents
as A2A services, the run and project stores, and the deployment in `deploy/`. The app, the
workbench and the admin service are clients of the harness. They are in scope only where they hold
a secret the harness relies on or expose a store.

This spec does not cover:

- the threat model that these controls answer to (TODO(#37));
- guardrails on model input and output (C2), or personal data held about the people who use the
  app (TODO(#156));
- who may do what in a project, or what roles a deployment defines. These are in
  [Projects](projects.md) and [Policy and identity](policy-and-identity.md).

C1 is assessed by review, not by a test lane ([Evaluation and conformance](evaluation.md)). A
reviewer reads the control table below against the code and the deployment.

## Invariants

1. **The secure path needs no configuration.** Every service binds to loopback by default.
   NGINX is the only listener a deployment exposes, with TLS 1.3 only and HSTS. An insecure or
   ambiguous identity setting stops start-up rather than running with a weaker one
   ([Policy and identity](policy-and-identity.md)). Serving beyond loopback with no sign-in only
   warns today; it should refuse unless explicitly allowed (TODO(#882)).
2. **A secret never reaches a record.** No key, password, token, grant or session cookie may
   appear in an envelope, evidence, span, RO-Crate, project log, export or log line. This holds
   by construction: a secret goes only to the client that uses it, and the harness writes no
   secret-bearing attribute. It is checked by a sentinel test for each kind of secret, which runs
   a real invocation with a recognisable value and searches everything stored. Spans imported
   from remote agents are the one place the harness does not control what is written, so it
   drops any attribute there that could hold a secret before storing them
   ([Transport and tracing](transport.md), invariant 11).
3. **A secret is read from a file, not from configuration.** Each secret has a `NAME_FILE` form
   read by `dd_sdk.credentials.api_key`, relative to `$CREDENTIALS_DIRECTORY` under systemd
   `LoadCredential=`. A deployment's `.env` files hold no secret values. The harness refuses a
   PostgreSQL URL that carries a password, so libpq reads it from `PGPASSFILE`. The FAIRsharing
   password in advisor-standards is the exception today (TODO(#883)).
4. **An error names a setting, never its value.** A misconfigured secret is reported by the name
   of its variable. A store location is printed through `redact_location`.
5. **Two audit streams, kept apart.** The run envelope and its provenance (C13) record what an
   agent did and for whom, in the run store. Security events record who signed in and in which
   deployment roles, who was refused, which profile a service loaded, what a data steward read or
   did in another person's project, which grants were minted and which accounts were enrolled, in
   a structured log of their own. They are not mixed into run provenance, because they have different readers,
   retention and integrity needs. Security events are one JSON line each on the `dd.security`
   logger (Security events, below).
6. **Anything downloaded at run time is pinned by hash.** A data snapshot, model weight or
   detector that the system fetches rather than installs as a locked package is recorded with
   its source URL and SHA-256, and checked on load, as the re3data snapshot is
   (`scripts/pin_re3data.py`). Nothing downloads model weights today.

## Control baseline

The status column uses four values:

- **Met:** the project implements the control and the evidence column shows it.
- **Partial:** part is implemented; the rest is an open issue.
- **Deployment:** the control is the operator's, and the operations guide says how.
- **Open:** not yet implemented.

| NIST SP 800-53 | Control in Data Director | Status | Evidence |
|---|---|---|---|
| AC-3, AC-6 | Project access is enforced by the harness: only owners and members reach a project's records. A deployment's roles (researcher, steward, administrator) come from the profile ([Data stewards](stewardship.md), invariant 1); a steward's path to a project is specified but not built. | Partial, TODO(#374) | `harness/src/dd_harness/project_access.py` and its tests |
| AC-2, AC-3 | Who may use a deployment is the profile's `access` key: anyone the provider vouches for, or only those listed and the deployment's roles, with named iDs blocked. It is checked at sign-in and on every request, and a person no longer admitted loses their session at their next request. | Met | `harness/src/dd_harness/access.py`, `harness/tests/test_access.py`, `app/tests/test_sign_in.py` |
| AC-17, SC-7 | Every service binds to loopback by default. NGINX is the only exposed edge. The admin service refuses a non-loopback `Host`. | Partial, TODO(#882) | `harness/src/dd_harness/server.py`, `deploy/systemd/`, `deploy/nginx/data-director.conf`, `admin/tests/test_admin.py` |
| IA-2, IA-8 | A person signs in with ORCID through OpenID Connect. A program presents an ID token, checked with RS256 only. | Met | `harness/src/dd_harness/signin.py`, `harness/src/dd_harness/identity.py` and their tests |
| IA-3, IA-9 | Calls between the harness and its agents are not authenticated in either direction. | Open, TODO(#17) | [Transport and tracing](transport.md) |
| IA-5, IA-5(7) | Secrets are read from credential files, never hard-coded or committed. Setting both a value and its file is an error. | Partial, TODO(#883) | `sdk/src/dd_sdk/credentials.py`, `sdk/tests/test_credentials.py`, `deploy/credentials.sh` |
| SC-8 | TLS 1.3 from the browser to NGINX. Behind NGINX, traffic is plain HTTP on loopback. The broker requires `https` for a person's own provider. TLS to a remote PostgreSQL is not configured. | Partial, TODO(#887) | `deploy/nginx/data-director.conf`, `broker/src/dd_broker/guard.py` |
| SC-12, SC-28 | People's own model keys are sealed by the broker with a key-encryption key. Other data at rest is encrypted by the deployment's disk or volume. | Partial; Deployment, TODO(#887) | `broker/src/dd_broker/seal.py`, [A person's own model account](model-accounts.md) |
| SC-28, SI-12 | No secret reaches a stored record (invariant 2), including spans imported from remote agents. | Met | `harness/tests/test_span_scrub.py`, `agents/advisor-standards/tests/test_key_not_stored.py`, `agents/orchestrator-model/tests/test_orchestrator_key_not_stored.py`, `agents/advisor-documentation/tests/test_grant_not_stored.py`, `agents/advisor-rights/tests/test_rights_grant_not_stored.py`, `agents/advisor-fairness/tests/test_fairness_grant_not_stored.py`, `broker/tests/test_broker_key_not_leaked.py` |
| AC-3, CM-7 | Store directories and files are private to the service. The shipped units set umask 0027 (0077 for the broker), and the installer creates state directories 0750 and credential directories 0700. The harness does not yet set modes itself. | Partial, TODO(#886) | `deploy/systemd/`, `deploy/install.sh` |
| AU-2, AU-3, AU-12 | Run provenance records each invocation, the person it acted for and whose account paid (C13). Sign-in, sign-out, sessions ended for a person no longer admitted, the access policy in force, refused callers, minted grants, broker-bypass refusals, secrets dropped from an agent's spans and broker enrolment are security events: one JSON record each, with time, event, outcome, principal and reason code. Calls between the harness and its agents are not yet authenticated, so they raise no event. | Partial, TODO(#17) | `sdk/src/dd_sdk/security_log.py`, `sdk/tests/test_security_log.py`, `app/tests/test_sign_in.py`, `harness/tests/test_model_grants.py`, `broker/tests/test_broker_security_events.py` |
| AU-9, AU-11 | A run is written once and never changed. Retention is not yet set. | Partial, TODO(#156) | [Storage](storage.md), invariant 2 |
| CM-6 | An ambiguous identity configuration, an anonymous principal, and grant settings without keys all stop start-up. | Met | `harness/src/dd_harness/settings.py` and its tests |
| SI-11 | An error names a setting, not its value (invariant 4). | Met | `harness/src/dd_harness/settings.py` (`redact_location`), `harness/tests/test_storage.py` |
| RA-5, SI-2 | Dependencies are audited daily and on every lock-file change. Pull requests run dependency review. CodeQL scans Python, JavaScript and the workflows. Dependabot proposes updates. | Met | `.github/workflows/audit.yml`, `.github/workflows/ci.yml`, `.github/workflows/codeql.yml`, `.github/dependabot.yml` |
| SR-3, SR-4, SR-11 | Actions are pinned to a commit SHA and linted with zizmor. Base images are pinned by digest. Released images carry an SBOM and build provenance. Runtime dependencies are tiered with a fallback each. Downloaded data is pinned by hash (invariant 6). | Met | `.github/workflows/images.yml`, `docker/`, [Dependencies](dependencies.md), `scripts/pin_re3data.py` |

## Security events

Each service that authenticates a caller or mints a credential writes its security events with
`dd_sdk.security_log.emit` to the `dd.security` logger. `configure()`, called at start-up by
`data-director`, `dd-harness serve` and `dd-model-broker serve`, writes them to standard error as
one JSON object per line, apart from free-text lines. Under systemd the journal keeps them, under
each unit's `SyslogIdentifier`.

### Record

| Field | Value |
|---|---|
| `time` | UTC, ISO 8601 with milliseconds and `Z`. |
| `event` | One of the events below. |
| `outcome` | `success` or `failure`. |
| `service` | The component that recorded it: `app`, `harness` or `model-broker`. |
| `principal` | The person's identifier (their ORCID iD URL) in the app and the harness. In the broker, which knows nobody by name, the person's pseudonym (see [A person's own model account](model-accounts.md)). `null` where nobody has been verified. |
| `reason` | A reason code for a failure, or `null`. Never a message. |
| `agent_id`, `invocation_id`, `conversation_id`, `profile_id`, `profile_version`, `project_id`, `action`, `roles`, `provider`, `models`, `account`, `transport` | Present where they apply. No other field can be written. |

### Events

| Event | Recorded by | When | Reason codes |
|---|---|---|---|
| `sign-in.succeeded` | app | A session is opened, with the deployment `roles` the profile gives the person. | |
| `sign-in.failed` | app | A sign-in could not start, was declined at the provider, or opened no session. | `dd_harness.identity.RefusalReason` |
| `sign-out` | app | A person ends their session. | |
| `session.ended` | app | A session is ended because the profile no longer admits its person (Admission in [Policy and identity](policy-and-identity.md)). | `not-admitted` |
| `access.loaded` | app | The app starts signing people in under a profile, named by `profile_id` (its identifier and version), so the record shows which access policy was in force from then. | |
| `caller.refused` | app, harness | A request through A2A or AG-UI is refused for its credential, or an app request carries a session cookie that names no session. A request with no cookie at all is someone not yet signed in and is not recorded. | `RefusalReason` |
| `profile.loaded` | app, harness | A service starts under a profile, with its `profile_id` and `profile_version`. A deployment role changes only with the profile, so a role change shows as a new version ([Data stewards](stewardship.md), invariant 1). | |
| `steward.viewed` | harness | A data steward opens, reads or lists a project through the steward path, with its `project_id`; at most once a day for each steward and project, as `steward_viewed` in the project's log. | |
| `steward.acted` | harness | A data steward takes an action of the closed list in a project, with its `project_id` and `action` (`message`, `pause`, `resume`, `clear_gate`, `refuse_gate`, `propose_edit`). A note's text is never recorded. A refused action is not a security event; it is answered as an outcome. | |
| `grant.minted` | harness | A model grant is minted, with its agent, invocation, models and account. | |
| `agent.span-secret-dropped` | harness | A remote agent's span carried an attribute that could hold a secret, and the harness dropped it before storing the span ([Transport and tracing](transport.md), invariant 11). One event per reason in a run, with its `agent_id` and `invocation_id`; never the attribute's name or value. | `dd_harness.span_scrub.Reason` |
| `case.exported` | harness | An operator exports a run, conversation or project as a case for debugging ([Case files](casefile.md)), on the command line or from the admin service (whose principal is `urn:dd:deployment:admin`), with `action` the scope and the `invocation_id`, `conversation_id` or `project_id` it names. | |
| `agent.broker-bypass-refused` | harness | An agent is refused because it does not call through the model broker. | `model-broker-bypassed` |
| `broker.enrolled`, `broker.account-removed` | model-broker | A person adds, replaces or removes their own model account. | |
| `broker.enrolment-refused`, `broker.call-refused` | model-broker | A request is refused for its ticket, grant, agent credential or base URL (`dd_broker.reasons.ACCESS`). A refusal about a provider or an account is not a security event. | `dd_broker.reasons.Reason` |

### Rules

1. A record has only the fields above, so a token, key, cookie or grant has no field to travel in
   (invariant 2). The app's sign-in tests check this with a recognisable value of each.
2. A refusal names a principal only when the provider has vouched for them (`not-admitted`).
   Otherwise whatever a caller claims is not believed, and is not recorded.
3. The log is read by the deployment's operators, who have access to the host's journal. No
   deployment role reads it through the app or the workbench, and the admin service does not
   show it. Each project's own log already shows its researchers what a steward did there.
4. Retention, and whether the client's address is recorded, are the deployment's until
   TODO(#156) decides them. The journal's integrity (AU-9) is the deployment's, for example
   journald `Seal=yes` or forwarding to a separate host.

## Rationale

NIST SP 800-53 is the framework the Blueprint names for C1. Its control families map directly
onto the parts C1 lists: AC and IA for access, SC for encryption, AU for audit, CM for defaults,
and SR and RA for the supply chain. A recognised identifier on each row lets an institution's
security team read the table against its own control set without translating it. This baseline
selects only the controls that a piece of software can meet or show evidence for. Controls about
people, premises and organisational process belong to the deploying institution.

Invariant 2 relies on secrets never being handed to a writer, checked by sentinel tests, rather
than on a redaction pass over records. A redaction pass can only remove values it recognises, so
it hides a leak instead of preventing it. A sentinel test fails on any path the value takes. The
one boundary where the harness does not control what is written, spans from another process, is
where the scrubbing step is (`dd_harness.span_scrub`).

Security events and run provenance are separate (invariant 5) because C1 scopes its audit trail
to infrastructure and access control, and C13 scopes its trail to agent actions. The two are
read by different people (an operator or security team, and a researcher or steward). They are
kept for different lengths of time. A failed sign-in has no invocation to belong to.

## Rejected alternatives

- **OWASP ASVS or NIST CSF as the baseline.** ASVS is detailed at the level of web-application
  controls but is not the framework the Blueprint names. CSF 2.0 states outcomes too broadly to
  name a test against each. The OWASP Top 10 for Agentic Applications, which the Blueprint's
  evaluation criteria also cite, belongs to the threat model (TODO(#37)), not to this baseline.
- **A redaction step on every export path.** Rejected for the reasons in the Rationale. It would
  be a second, weaker version of invariant 2.
- **Security events as entries in the run store.** Rejected because many events have no run, and
  because run provenance is written once per invocation and published in RO-Crates. A sign-in
  record must not be.

## Non-functional requirements

- A deployment that follows `deploy/README.md` meets every row marked Met or Deployment without
  further configuration.
- The control table stays current. A change that adds, removes or weakens a control updates its
  row in the same pull request.

## Open questions

- TODO(#37): the threat model these controls answer to, including where the broker's
  key-encryption key is kept apart from backups.
- TODO(#882): refuse to serve beyond loopback with no sign-in unless explicitly allowed.
- TODO(#883): the FAIRsharing password read from a credential file, and a sentinel test for it.
- TODO(#886): store directories and files private to the service whatever the umask.
- TODO(#887): operations guidance on encryption at rest and TLS to a remote PostgreSQL.
- TODO(#17): authentication between the harness and its agents.
- TODO(#374): the security events a steward's actions raise ([Data stewards](stewardship.md)).
