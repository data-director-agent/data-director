import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import type { AttachedDocument, DocumentCheck } from "../../conversation/documentation";
import { DocumentReviewDialog } from "./DocumentReviewDialog";

const NOTES: AttachedDocument = {
  name: "notes.md",
  media_type: "text/markdown",
  text: "Write to the survey team before the visit.\n",
  size: 44,
};

const FOUND: DocumentCheck = {
  findings: [
    { kind: "email address", places: "1", confidence: "high" },
    { kind: "secret", detail: "AWS Access Key", places: "1", confidence: "high" },
  ],
  kinds: ["AWS Access Key", "email address"],
  checked_with: "presidio-analyzer; detect-secrets",
};

const NOTHING: DocumentCheck = { findings: [], kinds: [], checked_with: "presidio-analyzer" };

function dialog(): HTMLElement {
  return screen.getByRole("dialog", { name: "Check the document before attaching it" });
}

function checkSection(): HTMLElement {
  return within(dialog()).getByRole("region", { name: "Possible personal data or secrets" });
}

describe("DocumentReviewDialog", () => {
  it("names what was found and attaches the document only once the researcher confirms", async () => {
    const onAttach = vi.fn();
    render(
      <DocumentReviewDialog
        pending={NOTES}
        onAttach={onAttach}
        onDiscard={vi.fn()}
        check={() => Promise.resolve(FOUND)}
      />,
    );
    const items = await within(checkSection()).findAllByRole("listitem");
    expect(items).toHaveLength(FOUND.findings.length);
    const attach = within(dialog()).getByRole("button", { name: "Attach anyway" });
    expect(attach).toBeDisabled();
    await userEvent.click(within(checkSection()).getByRole("checkbox"));
    expect(attach).toBeEnabled();
    expect(await axe(dialog())).toHaveNoViolations();
    await userEvent.click(attach);
    expect(onAttach).toHaveBeenCalledWith({ ...NOTES, confirmed: FOUND.kinds });
  });

  it("attaches a document in which nothing was found without a confirmation", async () => {
    const onAttach = vi.fn();
    render(
      <DocumentReviewDialog
        pending={NOTES}
        onAttach={onAttach}
        onDiscard={vi.fn()}
        check={() => Promise.resolve(NOTHING)}
      />,
    );
    const attach = within(dialog()).getByRole("button", { name: "Attach this document" });
    expect(attach).toBeDisabled();
    await within(checkSection()).findByText(/Nothing was found/);
    expect(within(checkSection()).queryByRole("checkbox")).toBeNull();
    await userEvent.click(attach);
    expect(onAttach).toHaveBeenCalledWith(NOTES);
  });

  it("says when the text could not be checked, and leaves the server to check it", async () => {
    render(
      <DocumentReviewDialog
        pending={NOTES}
        onAttach={vi.fn()}
        onDiscard={vi.fn()}
        check={() => Promise.reject(new Error("the server answered 502"))}
      />,
    );
    expect(await within(checkSection()).findByRole("alert")).toBeVisible();
    expect(within(dialog()).getByRole("button", { name: "Attach this document" })).toBeEnabled();
  });

  it("asks again for a document chosen after one that was confirmed", async () => {
    const check = () => Promise.resolve(FOUND);
    const { rerender } = render(
      <DocumentReviewDialog pending={NOTES} onAttach={vi.fn()} onDiscard={vi.fn()} check={check} />,
    );
    await userEvent.click(await within(checkSection()).findByRole("checkbox"));
    rerender(
      <DocumentReviewDialog
        pending={{ ...NOTES, name: "other.md" }}
        onAttach={vi.fn()}
        onDiscard={vi.fn()}
        check={check}
      />,
    );
    expect(await within(checkSection()).findByRole("checkbox")).not.toBeChecked();
    expect(within(dialog()).getByRole("button", { name: "Attach anyway" })).toBeDisabled();
  });

  describe("names the file a document's text was read from", () => {
    const TEXT = "Sediment cores were taken monthly.";
    const source = (pending: AttachedDocument) => {
      render(
        <DocumentReviewDialog
          pending={pending}
          onAttach={vi.fn()}
          onDiscard={vi.fn()}
          check={() => Promise.resolve(NOTHING)}
        />,
      );
      return dialog();
    };

    it("a PDF", () => {
      const shown = source({
        name: "plan.pdf",
        media_type: "application/pdf",
        text: TEXT,
        size: TEXT.length,
        data: "JVBERi0=",
      });
      expect(shown).toHaveTextContent("PDF");
      expect(shown).toHaveTextContent(TEXT);
    });

    it("a Word document", () => {
      const shown = source({
        name: "plan.docx",
        media_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        text: TEXT,
        size: TEXT.length,
        data: "UEsDBA==",
      });
      expect(shown).toHaveTextContent("Word document");
    });

    it("but none for a document attached as text", () => {
      const shown = source(NOTES);
      expect(shown).not.toHaveTextContent("Word document");
      expect(shown).not.toHaveTextContent("PDF");
    });
  });
});
