import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { App } from "../../App";
import reference from "../../../fixtures/agents.json";
import { normalise } from "../../manifest/normalise";
import type { RawAgentsResponse } from "../../manifest/types";
import {
  SIGNED_OUT as SIGNED_OUT_EVENT,
  SignedOut,
  assuranceText,
  checkSignedIn,
  fromRaw,
  providerName,
  signInHref,
} from "../../session/api";
import { DEVELOPMENT, SIGNED_OUT, WithSession, fakeSessionApi, signedIn } from "../../test/session";
import { SessionTimeout } from "./SessionTimeout";

const directory = normalise(reference as unknown as RawAgentsResponse);

function at(path: string) {
  history.pushState(null, "", path);
}

/** The page's banner (a page header is a `<header>` too). */
function banner(): HTMLElement {
  const found = document.querySelector<HTMLElement>("header.app-header");
  if (!found) throw new Error("no banner");
  return found;
}

describe("signing in", () => {
  it("shows the sign-in page, and loads nothing, when nobody is signed in", async () => {
    at("/agents?agent=advisor.standards");
    const load = vi.fn(() => Promise.resolve(directory));
    const { container } = render(
      <WithSession api={fakeSessionApi(SIGNED_OUT)}>
        <App load={load} />
      </WithSession>,
    );
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in to Data Director" })).toBeVisible();
    const link = screen.getByRole("link", { name: "Sign in with ORCID" });
    expect(link).toHaveAttribute("href", signInHref("/agents?agent=advisor.standards"));
    expect(screen.getByText(/not for your email address/)).toBeVisible();
    expect(load).not.toHaveBeenCalled();
    expect(within(banner()).queryByText("Sign out")).toBeNull();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("is reached by keyboard: the sign-in link is in the tab order", async () => {
    at("/");
    render(
      <WithSession api={fakeSessionApi(SIGNED_OUT)}>
        <App load={() => Promise.resolve(directory)} />
      </WithSession>,
    );
    const link = await screen.findByRole("link", { name: "Sign in with ORCID" });
    for (let i = 0; i < 20 && document.activeElement !== link; i++) await userEvent.tab();
    expect(link).toHaveFocus();
  });

  it.each([
    ["declined", "You did not sign in"],
    ["failed", "Signing in did not work"],
    ["anything", "Signing in did not work"],
  ])("says why a sign-in that came back with %s opened no session", async (problem, text) => {
    at(`/sign-in?problem=${problem}`);
    render(
      <WithSession api={fakeSessionApi(SIGNED_OUT)}>
        <App load={() => Promise.resolve(directory)} />
      </WithSession>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.getByRole("link", { name: "Sign in with ORCID" })).toHaveAttribute(
      "href",
      signInHref("/"),
    );
  });

  it("names the signed-in person in the banner and whom runs act for", async () => {
    at("/agents");
    const load = () =>
      Promise.resolve({
        ...directory,
        actingFor: {
          name: "Josiah Carberry",
          assurance: "authenticated",
          vouchedBy: "https://sandbox.orcid.org",
        },
      });
    const { container } = render(
      <WithSession api={fakeSessionApi(signedIn())}>
        <App load={load} />
      </WithSession>,
    );
    const header = banner();
    expect(await within(header).findByText("Josiah Carberry")).toBeVisible();
    expect(within(header).getByRole("button", { name: "Sign out" })).toBeVisible();
    expect(await screen.findByText(/authenticated by sandbox\.orcid\.org/)).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("signs out on the server, then says the person may still be signed in at ORCID", async () => {
    at("/");
    const signOut = vi.fn(() => Promise.resolve());
    render(
      <WithSession api={fakeSessionApi(signedIn(), { signOut })}>
        <App load={() => Promise.resolve(directory)} />
      </WithSession>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(signOut).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("heading", { level: 1, name: "You have signed out" })).toBeVisible();
    expect(screen.getByText(/still be signed in at ORCID/)).toBeVisible();
    expect(location.pathname).toBe("/signed-out");
    expect(within(banner()).queryByText("Josiah Carberry")).toBeNull();
  });

  it("says when signing out did not work", async () => {
    at("/");
    render(
      <WithSession api={fakeSessionApi(signedIn(), { signOut: () => Promise.reject(new Error("down")) })}>
        <App load={() => Promise.resolve(directory)} />
      </WithSession>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    expect(await screen.findByText(/Signing out did not work/)).toHaveAttribute("role", "alert");
  });

  it("brings the sign-in page back when the server says the session has ended", async () => {
    at("/agents");
    const load = () => {
      checkSignedIn(new Response(null, { status: 401 }));
      return Promise.resolve(directory);
    };
    render(
      <WithSession api={fakeSessionApi(signedIn())}>
        <App load={async () => load()} />
      </WithSession>,
    );
    expect(await screen.findByRole("link", { name: "Sign in with ORCID" })).toHaveAttribute(
      "href",
      signInHref("/agents"),
    );
  });

  it("says on every page of a development server that it signs nobody in", async () => {
    at("/agents");
    render(
      <WithSession api={fakeSessionApi(DEVELOPMENT)}>
        <App load={() => Promise.resolve(directory)} />
      </WithSession>,
    );
    const header = banner();
    expect(await within(header).findByText("Not signing anyone in")).toBeVisible();
    expect(within(header).queryByRole("button", { name: "Sign out" })).toBeNull();
    expect(await screen.findByText(/asserted by the operator, not authenticated/)).toBeVisible();
  });

  it("reports a failure to learn who is signed in as an alert", async () => {
    at("/");
    render(
      <WithSession api={fakeSessionApi(SIGNED_OUT, { get: () => Promise.reject(new Error("down")) })}>
        <App load={() => Promise.resolve(directory)} />
      </WithSession>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("could not say who is signed in");
  });
});

describe("SessionTimeout", () => {
  it("warns before the session ends and keeps it going when asked", async () => {
    const ending = signedIn(new Date(Date.now() + 60_000).toISOString());
    const later = signedIn();
    const stay = vi.fn(() => Promise.resolve(later));
    const onChange = vi.fn();
    const { container } = render(
      <WithSession api={fakeSessionApi(ending, { stay })}>
        <SessionTimeout session={ending} onChange={onChange} />
      </WithSession>,
    );
    expect(await screen.findByText(/You will be signed out at/)).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("nothing has been done here");
    expect(await axe(container)).toHaveNoViolations();
    await userEvent.click(screen.getByRole("button", { name: "Stay signed in" }));
    expect(stay).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith(later);
  });

  it("looks again rather than warn when the session was used since", async () => {
    const stale = signedIn(new Date(Date.now() + 60_000).toISOString());
    const fresh = signedIn();
    const onChange = vi.fn();
    render(
      <WithSession api={fakeSessionApi(fresh)}>
        <SessionTimeout session={stale} onChange={onChange} />
      </WithSession>,
    );
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(fresh));
    expect(screen.queryByText(/You will be signed out at/)).toBeNull();
  });

  it("says the session has ended when it does", async () => {
    const ending = signedIn(new Date(Date.now() + 50).toISOString());
    const ended = vi.fn();
    window.addEventListener(SIGNED_OUT_EVENT, ended);
    render(
      <WithSession api={fakeSessionApi(ending)}>
        <SessionTimeout session={ending} onChange={() => undefined} />
      </WithSession>,
    );
    await waitFor(() => expect(ended).toHaveBeenCalled());
    window.removeEventListener(SIGNED_OUT_EVENT, ended);
  });

  it("shows nothing when the session is far from its end", () => {
    render(
      <WithSession api={fakeSessionApi(signedIn())}>
        <SessionTimeout session={signedIn()} onChange={() => undefined} />
      </WithSession>,
    );
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });
});

describe("the session API", () => {
  it("reads the server's session", () => {
    expect(
      fromRaw({
        signs_in: true,
        issuer: "https://orcid.org",
        principal: {
          principal_id: "https://orcid.org/0000-0002-1825-0097",
          name: "Josiah Carberry",
          assurance: "authenticated",
          vouched_by: "https://orcid.org",
        },
        expires_at: "2026-10-29T18:00:00Z",
      }),
    ).toEqual({
      signsIn: true,
      issuer: "https://orcid.org",
      principal: {
        principalId: "https://orcid.org/0000-0002-1825-0097",
        name: "Josiah Carberry",
        assurance: "authenticated",
        vouchedBy: "https://orcid.org",
      },
      expiresAt: "2026-10-29T18:00:00Z",
    });
  });

  it("treats a 401 as signed out, and nothing else", () => {
    const ended = vi.fn();
    window.addEventListener(SIGNED_OUT_EVENT, ended);
    expect(() => checkSignedIn(new Response(null, { status: 200 }))).not.toThrow();
    expect(() => checkSignedIn(new Response(null, { status: 403 }))).not.toThrow();
    expect(ended).not.toHaveBeenCalled();
    expect(() => checkSignedIn(new Response(null, { status: 401 }))).toThrow(SignedOut);
    expect(ended).toHaveBeenCalledTimes(1);
    window.removeEventListener(SIGNED_OUT_EVENT, ended);
  });

  it("says who vouched, in words", () => {
    expect(assuranceText({ assurance: "asserted" })).toBe("asserted by the operator, not authenticated");
    expect(assuranceText({ assurance: "authenticated", vouchedBy: "https://orcid.org" })).toBe(
      "authenticated by orcid.org",
    );
    expect(assuranceText({ assurance: "authenticated" })).toBe("authenticated");
  });

  it("names ORCID and its sandbox as ORCID, and any other provider by its host", () => {
    expect(providerName("https://orcid.org")).toBe("ORCID");
    expect(providerName("https://sandbox.orcid.org")).toBe("ORCID");
    expect(providerName("https://login.example.ac.uk/realms/x")).toBe("login.example.ac.uk");
    expect(providerName(null)).toBe("your identity provider");
  });
});
