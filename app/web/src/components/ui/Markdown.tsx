/**
 * The one place the shell renders Markdown: an agent's reply, or a drafted document's text.
 *
 * GitHub's extensions (tables, task lists, strikethrough, autolinks) are read, since agents draft
 * data dictionaries as tables. Raw HTML in the text is not rendered. A table scrolls on its own
 * rather than widening the page (reflow at 320 CSS pixels).
 */

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const PLUGINS = [remarkGfm];

const COMPONENTS: Components = {
  table: ({ children }) => (
    <div className="table-scroll">
      <table className="data-table">{children}</table>
    </div>
  ),
};

export function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS}>
      {children}
    </ReactMarkdown>
  );
}
