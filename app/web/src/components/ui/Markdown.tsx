/**
 * The one place the shell renders Markdown: an agent's reply, or a drafted document's text.
 *
 * GitHub's extensions (tables, task lists, strikethrough, autolinks) are read, since agents draft
 * data dictionaries as tables. HTML comments, such as a drafter's `<!-- dd:gap … -->` markers, are not
 * shown; other raw HTML is shown as text, not rendered. Only the rendering drops comments: the
 * document's text keeps them. A table scrolls on its own rather than widening the page (reflow at
 * 320 CSS pixels).
 */

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// The parts of an mdast node this file reads; `html` nodes hold raw HTML, comments included.
interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
}

const COMMENT = /<!--[\s\S]*?-->/g;

function dropComments(node: MdNode): void {
  if (!node.children) return;
  node.children = node.children.flatMap((child) => {
    if (child.type !== "html") {
      dropComments(child);
      return [child];
    }
    const rest = (child.value ?? "").replace(COMMENT, "");
    return rest.trim() === "" ? [] : [{ ...child, value: rest }];
  });
}

/** Removes HTML comments from the tree, leaving any other raw HTML to show as text. */
function remarkDropComments() {
  return dropComments;
}

const PLUGINS = [remarkGfm, remarkDropComments];

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
