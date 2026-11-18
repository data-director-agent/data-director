/**
 * The pages for when something is not there or has gone wrong: a page that does not exist (`404`),
 * and a page that failed while it was drawn. Each says in plain words what happened and what the
 * person can do next, offers a way back, and keeps the banner and navigation around it so nobody
 * is left stranded. The status code is a large numeral for the eye only: it is hidden from screen
 * readers, which hear the title, and the page has one `h1` like every other (`PageHeader`).
 */

import "./ErrorPage.css";

import { ArrowLeft, Home, RotateCw } from "lucide-react";
import type { ReactNode } from "react";

import { Link } from "../../route";
import { PageHeader } from "../frame/PageHeader";
import { Button } from "../ui/Button";

function ErrorPage({
  code,
  title,
  children,
  actions,
  alert,
}: {
  code: string;
  title: string;
  children: ReactNode;
  actions: ReactNode;
  alert?: boolean;
}) {
  return (
    <>
      <PageHeader title={title} titleHidden />
      <section className="error-page" role={alert ? "alert" : undefined}>
        <p className="error-code" aria-hidden="true">
          {code}
        </p>
        <h2 className="error-title">{title}</h2>
        <div className="error-detail">{children}</div>
        <div className="error-actions">{actions}</div>
      </section>
    </>
  );
}

/** The home link, drawn as the page's main action. */
function HomeLink() {
  return (
    <Link to="/" className="button button-primary">
      <Home className="button-icon" size="1.125em" aria-hidden="true" />
      Go to the conversation
    </Link>
  );
}

/** A page the app does not have. `path` is what was asked for, shown so a mistyped address is easy to spot. */
export function NotFoundPage({ path }: { path: string }) {
  return (
    <ErrorPage
      code="404"
      title="Page not found"
      actions={
        <>
          <HomeLink />
          <Link to="/projects" className="button">
            Your projects
          </Link>
          <Button icon={ArrowLeft} onPress={() => history.back()}>
            Go back
          </Button>
        </>
      }
    >
      <p>
        There is no page at <code className="error-path">{path}</code>. The address may be mistyped, or
        the page may have moved.
      </p>
    </ErrorPage>
  );
}

/** A page that failed while it was drawn. The cause goes to the console, not the page: it is for
 * whoever fixes it, and may name things the reader has no use for. */
export function SomethingWentWrongPage({ onRetry }: { onRetry?: () => void }) {
  return (
    <ErrorPage
      code="Oops"
      title="Something went wrong"
      alert
      actions={
        <>
          <Button variant="primary" icon={RotateCw} onPress={onRetry ?? (() => location.reload())}>
            Try again
          </Button>
          <Link to="/" className="button">
            Go to the conversation
          </Link>
        </>
      }
    >
      <p>
        Data Director could not show this page. Nothing you have saved is lost. Try again, and if it
        keeps happening, use <Link to="/feedback">Report a problem</Link> and say what you were doing.
      </p>
    </ErrorPage>
  );
}
