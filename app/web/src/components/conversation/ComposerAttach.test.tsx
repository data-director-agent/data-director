import { fireEvent, render } from "@testing-library/react";

import { ComposerAttach } from "./ComposerAttach";

function accepted(documents: boolean): string[] {
  const { container } = render(
    <ComposerAttach
      attached={null}
      attachedDocument={null}
      documents={documents}
      busy={false}
      onAttachFiles={vi.fn()}
      onAttachMade={vi.fn()}
      onRemoveInventory={vi.fn()}
      onRemoveDocument={vi.fn()}
    />,
  );
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  return (input?.accept ?? "").split(",");
}

describe("ComposerAttach", () => {
  it("takes an inventory or a document where the profile allows documents", () => {
    const types = accepted(true);
    expect(types).toContain(".json");
    expect(types).toContain(".md");
    expect(types).toContain(".pdf");
    expect(types).toContain(".docx");
  });

  it("passes on every file picked, so that those not attached can be named (#1170)", () => {
    const onAttachFiles = vi.fn();
    const { container } = render(
      <ComposerAttach
        attached={null}
        attachedDocument={null}
        documents
        busy={false}
        onAttachFiles={onAttachFiles}
        onAttachMade={vi.fn()}
        onRemoveInventory={vi.fn()}
        onRemoveDocument={vi.fn()}
      />,
    );
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    if (!input) throw new Error("no file input");
    const picked = [new File(["a"], "protocol.md"), new File(["b"], "codebook.md")];
    // The picker asks for one file, but what the browser hands over is passed on whole.
    fireEvent.change(input, { target: { files: picked } });
    expect(onAttachFiles).toHaveBeenCalledTimes(1);
    const files = onAttachFiles.mock.calls[0]?.[0] as FileList;
    expect(Array.from(files).map((file) => file.name)).toEqual(["protocol.md", "codebook.md"]);
  });

  it("takes only an inventory where the profile refuses documents", () => {
    const types = accepted(false);
    expect(types).toContain(".json");
    expect(types).not.toContain(".md");
    expect(types).not.toContain(".pdf");
    expect(types).not.toContain("text/markdown");
  });
});
