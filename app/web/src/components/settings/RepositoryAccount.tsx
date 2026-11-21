/**
 * The person's own repository account on the Settings page (docs/specs/deposit.md, Depositing
 * through an API).
 *
 * Data Director creates a draft in a repository only with the person's own account there. The
 * account is connected at the deposit broker, never through the app (`deposit/api.ts`): by signing
 * in at the repository and approving depositing (OAuth), which sends the browser away and back, or,
 * where the deployment has no OAuth application, by pasting a personal token, which the broker
 * checks first. The page shows only the label the broker returns. Disconnecting erases the account
 * at the broker at once.
 *
 * Coming back from the repository, the address says whether the account was connected
 * (`?repository=connected`) or why not (`?repository_error=…`), and the page says so once.
 */

import { Link2, Trash2 } from "lucide-react";
import { type FormEvent, useEffect, useId, useState } from "react";

import {
  type RepositoryAccount as Account,
  type RepositoryOption,
  RepositoryAccountRefused,
  reasonText,
  useDepositApi,
} from "../../deposit/api";
import { formatDateTime } from "../../format";
import { SignedOut } from "../../session/api";
import { Button } from "../ui/Button";

/** What a person calls a repository's API root: its host, and whether it is a sandbox. */
export function repositoryName(baseUrl: string): string {
  const host = new URL(baseUrl).hostname;
  if (host === "sandbox.zenodo.org") return "Zenodo sandbox";
  if (host === "zenodo.org") return "Zenodo";
  return host;
}

/** What coming back from the repository says, from the page's address. */
export function returned(search: string): { ok: boolean; message: string } | null {
  const params = new URLSearchParams(search);
  if (params.get("repository") === "connected") {
    return { ok: true, message: "Your repository account is connected." };
  }
  const error = params.get("repository_error");
  return error ? { ok: false, message: `Your account was not connected. ${reasonText(error)}` } : null;
}

function messageOf(error: unknown): string {
  return error instanceof RepositoryAccountRefused ? reasonText(error.reason) : reasonText("");
}

function TokenForm({ option, onSaved }: { option: RepositoryOption; onSaved: (a: Account) => void }) {
  const api = useDepositApi();
  const [token, setToken] = useState("");
  const [failed, setFailed] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const id = useId();
  const hintId = useId();
  const site = new URL(option.baseUrl).origin;

  async function save(event: FormEvent) {
    event.preventDefault();
    const typed = token.trim();
    setToken("");
    setSending(true);
    setFailed(null);
    try {
      onSaved(await api.saveToken(option.baseUrl, typed));
    } catch (error) {
      if (error instanceof SignedOut) return;
      setFailed(messageOf(error));
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={(event) => void save(event)}>
      <div className="field">
        <label htmlFor={id}>Personal access token</label>
        <p className="hint" id={hintId}>
          Create a token at{" "}
          <a
            href={`${site}/account/settings/applications/tokens/new/`}
            target="_blank"
            rel="noreferrer"
          >
            {repositoryName(option.baseUrl)}: Applications, New token
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
          , with only the <code>deposit:write</code> scope. That lets Data Director create drafts
          but not publish them. The token is checked before it is saved.
        </p>
        <input
          type="password"
          id={id}
          aria-describedby={hintId}
          autoComplete="off"
          spellCheck={false}
          required
          value={token}
          onChange={(event) => setToken(event.target.value)}
        />
      </div>
      {failed && (
        <div role="alert" className="callout status-danger">
          <p>{failed}</p>
        </div>
      )}
      <p>
        <Button type="submit" variant="primary" isPending={sending}>
          Save the token
        </Button>
      </p>
    </form>
  );
}

function Repository({ option }: { option: RepositoryOption }) {
  const api = useDepositApi();
  const [account, setAccount] = useState<Account | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const [said, setSaid] = useState("");
  const name = repositoryName(option.baseUrl);

  useEffect(() => {
    const controller = new AbortController();
    api.account(option.baseUrl, controller.signal).then(setAccount, (error: unknown) => {
      if (controller.signal.aborted || error instanceof SignedOut) return;
      setFailed(messageOf(error));
    });
    return () => controller.abort();
  }, [api, option.baseUrl]);

  async function disconnect() {
    setFailed(null);
    try {
      await api.disconnect(option.baseUrl);
      setAccount({ baseUrl: option.baseUrl, connected: false });
      setSaid(`Your ${name} account was disconnected.`);
    } catch (error) {
      if (error instanceof SignedOut) return;
      setFailed(messageOf(error));
    }
  }

  async function connect() {
    setFailed(null);
    try {
      await api.connect(option.transport, option.baseUrl);
    } catch (error) {
      if (error instanceof SignedOut) return;
      setFailed(messageOf(error));
    }
  }

  return (
    <section className="repository-account" aria-label={name}>
      <h3>{name}</h3>
      {name.endsWith("sandbox") && (
        <p className="hint">
          The sandbox is a test copy of the repository, with its own accounts. Its records and DOIs
          are not real.
        </p>
      )}
      <div role="status">{said && <p>{said}</p>}</div>
      {failed && (
        <div role="alert" className="callout status-danger">
          <p>{failed}</p>
        </div>
      )}
      {account === null && !failed && <p>Reading your account…</p>}
      {account?.connected && (
        <>
          <dl className="profile-details">
            <div>
              <dt>Account</dt>
              <dd>{account.label}</dd>
            </div>
            {account.created && (
              <div>
                <dt>Connected</dt>
                <dd>
                  <time dateTime={account.created}>{formatDateTime(account.created)}</time>
                </dd>
              </div>
            )}
          </dl>
          <p>
            <Button variant="danger" icon={Trash2} onPress={() => void disconnect()}>
              Disconnect {name}
            </Button>
          </p>
        </>
      )}
      {account && !account.connected && (
        <>
          {option.oauth && (
            <p>
              <Button variant="primary" icon={Link2} onPress={() => void connect()}>
                Connect your {name} account
              </Button>
            </p>
          )}
          {option.oauth ? (
            <details>
              <summary>Or paste a personal token</summary>
              <TokenForm option={option} onSaved={setAccount} />
            </details>
          ) : (
            <TokenForm option={option} onSaved={setAccount} />
          )}
        </>
      )}
    </section>
  );
}

export function RepositoryAccount({ search = window.location.search }: { search?: string }) {
  const api = useDepositApi();
  const [options, setOptions] = useState<RepositoryOption[] | null>(null);
  const [failed, setFailed] = useState(false);
  const back = returned(search);

  useEffect(() => {
    const controller = new AbortController();
    api.options(controller.signal).then(setOptions, (error: unknown) => {
      if (controller.signal.aborted || error instanceof SignedOut) return;
      setFailed(true);
    });
    return () => controller.abort();
  }, [api]);

  return (
    <section className="model-account" aria-labelledby="repository-account-heading">
      <h2 id="repository-account-heading">Your repository accounts</h2>
      <p>
        Data Director can create a draft of your dataset in a repository with your own account
        there, once you approve it on the project&apos;s Deposit tab. It never publishes: you add
        your data files and publish in the repository. Your account is kept by Data
        Director&apos;s deposit broker, encrypted; the rest of Data Director never sees it.
      </p>
      {back && (
        <div role={back.ok ? "status" : "alert"} className={`callout ${back.ok ? "status-ok" : "status-danger"}`}>
          <p>{back.message}</p>
        </div>
      )}
      {failed && (
        <div role="alert" className="callout status-danger">
          <p>The repositories could not be read. Reload the page to try again.</p>
        </div>
      )}
      {options?.map((option) => <Repository key={option.baseUrl} option={option} />)}
    </section>
  );
}
