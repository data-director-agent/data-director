"""Email to a steward team's address, over SMTP (docs/specs/stewardship.md, invariant 13; #378).

Where the mail server is and how to sign in to it are environment variables, because they say where
things are and hold a secret; whom to tell and about what is the profile's (`StewardTeam.notify`,
`notify_on`):

- `DD_SMTP_URL`: `smtp://host:port` (STARTTLS) or `smtps://host:port` (TLS from the start);
- `DD_SMTP_USERNAME`, and `DD_SMTP_PASSWORD` (development) or `DD_SMTP_PASSWORD_FILE` (deployment,
  a systemd credential), where the server asks for them;
- `DD_MAIL_FROM`: the address messages come from;
- `DD_APP_PUBLIC_URL`: where the app is reached, which each message links to.

A message holds a subject and a link, never research content (`dd_harness.notifications`). It is
sent on a worker thread, so that a move never waits on the mail server, and one that cannot be
sent is logged with its event and nothing else: the project log stays authoritative.
"""

from __future__ import annotations

import logging
import queue
import smtplib
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol
from urllib.parse import urlsplit

from dd_harness.notifications import NULL_NOTIFIER, Notice, Notifier
from dd_harness.policy import Profile
from dd_sdk.credentials import ConfigError, api_key

log = logging.getLogger(__name__)

SCHEMES = {"smtp": 587, "smtps": 465}
TIMEOUT_S = 30.0


class SmtpSession(Protocol):
    """What a notifier asks of a connection to the mail server: `smtplib.SMTP`'s methods."""

    def starttls(self) -> object: ...
    def login(self, user: str, password: str) -> object: ...
    def send_message(self, msg: EmailMessage) -> object: ...
    def quit(self) -> object: ...


type Connect = Callable[[str, int, float], SmtpSession]


def _connect_smtp(host: str, port: int, timeout: float) -> SmtpSession:
    return smtplib.SMTP(host, port, timeout=timeout)


def _connect_smtps(host: str, port: int, timeout: float) -> SmtpSession:
    return smtplib.SMTP_SSL(host, port, timeout=timeout)


@dataclass(frozen=True)
class MailSettings:
    """Where the mail server is, how to sign in to it, whom messages come from, and the app's
    public URL that messages link to."""

    host: str
    port: int
    tls: bool
    sender: str
    public_url: str
    username: str | None = None
    password: str | None = None


def settings_from_env(env: Mapping[str, str], public_url: str | None = None) -> MailSettings | None:
    """The mail settings `env` gives, or None where `DD_SMTP_URL` is unset. `public_url` is the
    caller's default for `DD_APP_PUBLIC_URL`. Raises `ConfigError`, naming the variable and never
    a secret."""
    url = (env.get("DD_SMTP_URL") or "").strip()
    if not url:
        return None
    parts = urlsplit(url)
    if parts.scheme not in SCHEMES or not parts.hostname:
        raise ConfigError(f"DD_SMTP_URL is smtp://host:port or smtps://host:port, not {url!r}")
    if parts.username or parts.password:
        raise ConfigError("DD_SMTP_URL names no user or password: set DD_SMTP_USERNAME")
    sender = (env.get("DD_MAIL_FROM") or "").strip()
    if "@" not in sender:
        raise ConfigError("DD_SMTP_URL is set, so DD_MAIL_FROM names the address mail comes from")
    link = (env.get("DD_APP_PUBLIC_URL") or public_url or "").strip()
    if not link.startswith(("https://", "http://")):
        raise ConfigError("DD_SMTP_URL is set, so DD_APP_PUBLIC_URL names where the app is reached")
    username = (env.get("DD_SMTP_USERNAME") or "").strip() or None
    has_password = env.get("DD_SMTP_PASSWORD") or env.get("DD_SMTP_PASSWORD_FILE")
    return MailSettings(
        host=parts.hostname,
        port=parts.port or SCHEMES[parts.scheme],
        tls=parts.scheme == "smtps",
        sender=sender,
        public_url=link.rstrip("/"),
        username=username,
        password=api_key(env, "DD_SMTP_PASSWORD") if has_password else None,
    )


def message(settings: MailSettings, address: str, notice: Notice) -> EmailMessage:
    """The message for `notice`: its subject and a link to the app, and nothing more."""
    found = EmailMessage()
    found["From"] = settings.sender
    found["To"] = address
    found["Subject"] = f"Data Director: {notice.subject}"
    found.set_content(
        f"{notice.subject}.\n\n"
        f"Open it in Data Director: {settings.public_url}{notice.path}\n\n"
        "Sign in to read it. This message holds nothing more, so that no research content leaves "
        "Data Director by email.\n"
    )
    return found


class SmtpNotifier:
    """Sends each notice to its address over SMTP, on one worker thread. `background=False` sends
    in the caller's thread, for the sweep, which exits when it is done, and for tests."""

    def __init__(
        self,
        settings: MailSettings,
        *,
        background: bool = True,
        connect: Connect | None = None,
        timeout: float = TIMEOUT_S,
    ) -> None:
        self.settings = settings
        self.background = background
        self.timeout = timeout
        self._connect = connect or (_connect_smtps if settings.tls else _connect_smtp)
        self._queue: queue.Queue[tuple[str, Notice]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    def send(self, address: str, notice: Notice) -> None:
        if not self.background:
            self._deliver(address, notice)
            return
        with self._lock:
            if self._worker is None:
                self._worker = threading.Thread(target=self._drain, name="dd-mail", daemon=True)
                self._worker.start()
        self._queue.put((address, notice))

    def flush(self) -> None:
        """Wait until every notice queued has been sent or has failed."""
        self._queue.join()

    def _drain(self) -> None:
        while True:
            address, notice = self._queue.get()
            try:
                self._deliver(address, notice)
            finally:
                self._queue.task_done()

    def _deliver(self, address: str, notice: Notice) -> None:
        settings = self.settings
        try:
            smtp = self._connect(settings.host, settings.port, self.timeout)
            try:
                if not settings.tls:
                    smtp.starttls()
                if settings.username:
                    smtp.login(settings.username, settings.password or "")
                smtp.send_message(message(settings, address, notice))
            finally:
                smtp.quit()
        except (OSError, smtplib.SMTPException) as exc:
            log.warning(
                "could not email the %s notice for event %s to team %s: %s",
                notice.kind,
                notice.event_id,
                notice.team_id,
                type(exc).__name__,
            )
            return
        log.info(
            "emailed the %s notice for event %s to team %s",
            notice.kind,
            notice.event_id,
            notice.team_id,
        )


def notifier_for(
    profile: Profile,
    env: Mapping[str, str],
    public_url: str | None = None,
    *,
    background: bool = True,
) -> Notifier:
    """The notifier for a deployment: SMTP where `DD_SMTP_URL` is set, none otherwise. A profile
    that names a team's `notify` address with no mail server is refused, so that a team that
    expects mail is not left waiting for it. Raises `ConfigError`."""
    settings = settings_from_env(env, public_url)
    if settings is None:
        if named := [t.team_id for t in profile.stewardship.teams if t.notify]:
            raise ConfigError(
                f"the profile names an address for the steward team {', '.join(named)}, and "
                "DD_SMTP_URL names no mail server to send to it"
            )
        return NULL_NOTIFIER
    return SmtpNotifier(settings, background=background)
