/**
 * The one place the shell renders Markdown: an agent's reply, or a drafted document's text.
 *
 * GitHub's extensions (tables, task lists, strikethrough, autolinks) are read, since agents draft
 * data dictionaries as tables. HTML comments, such as a drafter's `<!-- dd:gap … -->` markers, are not
 * shown; other raw HTML is shown as text, not rendered. Only the rendering drops comments: the
 * document's text keeps them. A table scrolls on its own rather than widening the page (reflow at
 * 320 CSS pixels). A link to another site opens in a new tab, so that a reader can check a cited
 * source without leaving the conversation.
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

// One pass can splice a new comment together (`<!<!-- x -->--`), so repeat until the text is stable.
function stripComments(text: string): string {
  let previous: string;
  let current = text;
  do {
    previous = current;
    current = previous.replace(COMMENT, "");
  } while (current !== previous);
  return current;
}

function dropComments(node: MdNode): void {
  if (!node.children) return;
  node.children = node.children.flatMap((child) => {
    if (child.type !== "html") {
      dropComments(child);
      return [child];
    }
    const rest = stripComments(child.value ?? "");
    return rest.trim() === "" ? [] : [{ ...child, value: rest }];
  });
}

/** Removes HTML comments from the tree, leaving any other raw HTML to show as text. */
function remarkDropComments() {
  return dropComments;
}

const PLUGINS = [remarkGfm, remarkDropComments];

const EXTERNAL = /^https?:\/\//i;

const COMPONENTS: Components = {
  table: ({ children }) => (
    <div className="table-scroll">
      <table className="data-table">{children}</table>
    </div>
  ),
  // A link to another site, such as the policy or record an agent cited, opens in a new tab so
  // that the conversation stays where it is, and says so in its name for a screen reader. A link
  // within the app or a `mailto:` is left as written.
  a: ({ href, title, children }) => {
    const named = title ? { title } : {};
    return href && EXTERNAL.test(href) ? (
      <a {...named} href={href} target="_blank" rel="noreferrer">
        {children}
        <span className="visually-hidden"> (opens in a new tab)</span>
      </a>
    ) : (
      <a {...named} {...(href ? { href } : {})}>
        {children}
      </a>
    );
  },
};

export function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS}>
      {children}
    </ReactMarkdown>
  );
}
