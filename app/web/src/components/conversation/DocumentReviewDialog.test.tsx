import { render, screen } from "@testing-library/react";

import type { AttachedDocument } from "../../conversation/documentation";
import { DocumentReviewDialog } from "./DocumentReviewDialog";

const TEXT = "Sediment cores were taken monthly.";

function show(pending: AttachedDocument) {
  render(
    <DocumentReviewDialog
      pending={pending}
      onAttach={vi.fn()}
      onDiscard={vi.fn()}
    />,
  );
  return screen.getByRole("dialog");
}

describe("DocumentReviewDialog", () => {
  it("says a document's text was read from the PDF it came from", () => {
    const dialog = show({
      name: "plan.pdf",
      media_type: "application/pdf",
      text: TEXT,
      size: TEXT.length,
      data: "JVBERi0=",
    });
    expect(dialog).toHaveTextContent("PDF");
    expect(dialog).toHaveTextContent(TEXT);
  });

  it("says a document's text was read from the Word document it came from", () => {
    const dialog = show({
      name: "plan.docx",
      media_type:
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      text: TEXT,
      size: TEXT.length,
      data: "UEsDBA==",
    });
    expect(dialog).toHaveTextContent("Word document");
  });

  it("names no source for a document attached as text", () => {
    const dialog = show({
      name: "notes.md",
      media_type: "text/markdown",
      text: TEXT,
      size: 10,
    });
    expect(dialog).not.toHaveTextContent("Word document");
    expect(dialog).not.toHaveTextContent("PDF");
  });
});
