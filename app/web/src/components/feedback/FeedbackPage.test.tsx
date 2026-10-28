import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import {
  type About,
  type FeedbackApi,
  FeedbackApiContext,
  describeBuild,
} from "../../feedback/api";
import { FeedbackPage } from "./FeedbackPage";

const ABOUT: About = {
  app_version: "0.3.0-alpha.1",
  harness_version: "0.1.0",
  commit: "abcdef0123456789",
  feedback_enabled: true,
};

function fakeApi(overrides: Partial<FeedbackApi> = {}): FeedbackApi {
  return {
    about: () => Promise.resolve(ABOUT),
    send: () => Promise.resolve({ url: "https://github.test/issues/7", number: 7 }),
    ...overrides,
  };
}

function renderPage(api: FeedbackApi, query = "from=%2Fagents&run=r1") {
  return render(
    <FeedbackApiContext.Provider value={api}>
      <FeedbackPage query={query} />
    </FeedbackApiContext.Provider>,
  );
}

describe("describeBuild", () => {
  it("gives the version and the short commit", () => {
    expect(describeBuild(ABOUT)).toBe("v0.3.0-alpha.1 (abcdef0)");
    expect(describeBuild({ app_version: "1.0.0", commit: null })).toBe("v1.0.0");
    expect(describeBuild({ app_version: null, commit: null })).toBe("unknown version");
  });
});

describe("FeedbackPage", () => {
  it("shows the version and commit, and what will be sent", async () => {
    const { container } = renderPage(fakeApi());
    expect(await screen.findByText(/Data Director v0.3.0-alpha.1 \(abcdef0\)/)).toBeVisible();
    expect(screen.getByText("/agents")).toBeVisible();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sends the report with the page, and the run only if the reporter agrees", async () => {
    const send = vi.fn(fakeApi().send);
    const user = userEvent.setup();
    renderPage(fakeApi({ send }));
    await screen.findByText(/This is Data Director/);
    expect(screen.queryByText("r1")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Title"), "It hangs");
    await user.type(screen.getByLabelText("Details"), "Never ends.");
    await user.click(screen.getByLabelText(/Include the identifiers/));
    expect(screen.getByText("r1")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Send report" }));
    expect(send).toHaveBeenCalledWith({
      kind: "bug",
      title: "It hangs",
      description: "Never ends.",
      include_context: true,
      page: "/agents",
      run: "r1",
    });
    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("issue #7");
  });

  it("says plainly when the report was not filed, and keeps what was typed", async () => {
    const user = userEvent.setup();
    renderPage(fakeApi({ send: () => Promise.reject(new Error("GitHub answered 500.")) }), "");
    await screen.findByText(/This is Data Director/);
    await user.type(screen.getByLabelText("Title"), "t");
    await user.type(screen.getByLabelText("Details"), "d");
    await user.click(screen.getByRole("button", { name: "Send report" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("GitHub answered 500.");
    expect(screen.getByLabelText("Title")).toHaveValue("t");
  });

  it("cannot send where reports are off, and points to GitHub", async () => {
    renderPage(fakeApi({ about: () => Promise.resolve({ ...ABOUT, feedback_enabled: false }) }), "");
    expect(await screen.findByRole("link", { name: "open an issue on GitHub" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Send report" })).toBeDisabled();
  });
});
