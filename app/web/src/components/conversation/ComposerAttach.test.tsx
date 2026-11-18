import { render } from "@testing-library/react";

import { ComposerAttach } from "./ComposerAttach";

function accepted(documents: boolean): string[] {
  const { container } = render(
    <ComposerAttach
      attached={null}
      attachedDocument={null}
      documents={documents}
      busy={false}
      onAttachFile={vi.fn()}
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

  it("takes only an inventory where the profile refuses documents", () => {
    const types = accepted(false);
    expect(types).toContain(".json");
    expect(types).not.toContain(".md");
    expect(types).not.toContain(".pdf");
    expect(types).not.toContain("text/markdown");
  });
});
