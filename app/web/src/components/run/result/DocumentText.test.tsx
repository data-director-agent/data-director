import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import type { JsonSchema } from "@data-director/agent-view";
import { ResultView } from "../ResultView";
import { fileName } from "../../../project/media";

// The parts of the contract's Document that the result view reads.
const SCHEMA: JsonSchema = {
  type: "object",
  properties: {
    document_kind: { type: "string", enum: ["readme", "data_dictionary"] },
    document_title: { type: ["string", "null"] },
    media_type: { type: "string" },
    document_text: { type: "string" },
  },
};

const README = [
  "# Soil survey",
  "",
  "## Files",
  "",
  "- raw/plots.csv",
  "- raw/samples.csv",
  "",
  "| file | field | type |",
  "| --- | --- | --- |",
  "| raw/plots.csv | plot_id | string |",
  "| raw/plots.csv | ph | number |",
  "",
].join("\n");

function show(payload: Record<string, unknown>) {
  return render(
    <ResultView payload={payload} schema={SCHEMA} derivations={[]} evidence={[]} idPrefix="r" />,
  );
}

describe("DocumentText", () => {
  it("renders a Markdown document's headings, lists and tables", async () => {
    const { container } = show({ document_kind: "readme", media_type: "text/markdown", document_text: README });

    const document = screen.getByRole("region", { name: "README" });
    expect(within(document).getByRole("heading", { name: "Soil survey" })).toBeInTheDocument();
    expect(within(document).getByRole("heading", { name: "Files" })).toBeInTheDocument();
    expect(within(document).getAllByRole("listitem")).toHaveLength(2);
    const table = within(document).getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getByRole("columnheader", { name: "field" })).toBeInTheDocument();
    expect(document).not.toHaveTextContent("| --- |");
    // The text is not repeated among the facts.
    expect(container.querySelector("dl.facts")).not.toHaveTextContent("# Soil survey");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("keeps the line breaks of a document that is not Markdown", () => {
    const csv = "file,field\nraw/plots.csv,plot_id\n";
    show({ document_kind: "data_dictionary", media_type: "text/csv", document_text: csv });
    const document = screen.getByRole("region", { name: "Data dictionary" });
    const pre = document.querySelector("pre");
    expect(pre?.textContent).toBe(csv);
    expect(within(document).queryByRole("table")).not.toBeInTheDocument();
  });

  it("copies the text exactly and offers it as a file", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    show({
      document_kind: "readme",
      document_title: "README for raw/",
      media_type: "text/markdown",
      document_text: README,
    });

    await user.click(screen.getByRole("button", { name: "Copy the text" }));
    expect(writeText).toHaveBeenCalledWith(README);
    expect(screen.getByRole("status")).toHaveTextContent("Copied the text of README for raw/.");

    const link = screen.getByRole("link", { name: "Download readme-for-raw.md" });
    expect(link).toHaveAttribute("download", "readme-for-raw.md");
    const href = link.getAttribute("href") ?? "";
    expect(href.startsWith("data:text/markdown;charset=utf-8,")).toBe(true);
    expect(decodeURIComponent(href.slice(href.indexOf(",") + 1))).toBe(README);
  });

  it.each([
    ["README", "text/markdown", "readme.md"],
    ["Data dictionary", "text/csv; charset=utf-8", "data-dictionary.csv"],
    ["???", "application/octet-stream", "document.txt"],
  ])("names %s (%s) %s", (title, mediaType, expected) => {
    expect(fileName(title, mediaType)).toBe(expected);
  });
});
