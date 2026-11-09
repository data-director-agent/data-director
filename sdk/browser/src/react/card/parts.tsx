/**
 * The pieces a card is drawn with. A card is the agent's own text, so nothing in it becomes markup,
 * and only an http(s) URL becomes a link.
 */

import type { ReactNode } from "react";

import { isEmpty } from "../../payload/context";

export type HeadingLevel = 2 | 3 | 4 | 5 | 6;

export function Heading({ level, id, children }: { level: HeadingLevel; id?: string; children: ReactNode }) {
  const H = `h${level}` as const;
  return <H id={id}>{children}</H>;
}

export function None() {
  return <span className="dd-none">none</span>;
}

export function Code({ children }: { children: string }) {
  return <code>{children}</code>;
}

export function UrlLink({ url }: { url: string }) {
  return /^https?:\/\//i.test(url) ? (
    <a href={url} rel="noopener noreferrer">
      {url}
    </a>
  ) : (
    <code>{url}</code>
  );
}

export function Chips({ items }: { items: readonly string[] | undefined }) {
  if (!items?.length) return <None />;
  return (
    <ul className="dd-chips">
      {items.map((t, i) => (
        <li key={`${t}-${i}`} className="dd-chip">
          {t}
        </li>
      ))}
    </ul>
  );
}

/** A description list of the pairs whose value is present. */
export function KeyValues({ pairs }: { pairs: [string, ReactNode][] }) {
  const shown = pairs.filter(([, v]) => !isEmpty(v) && v !== false && v !== "");
  if (shown.length === 0) return null;
  return (
    <dl className="dd-kvs">
      {shown.map(([k, v]) => (
        <div key={k} className="dd-kv">
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Items<T>({
  list,
  render,
  itemKey,
}: {
  list: readonly T[] | undefined;
  render: (item: T) => ReactNode;
  itemKey: (item: T, index: number) => string;
}) {
  if (!list?.length) return <None />;
  return (
    <ul className="dd-items">
      {list.map((item, i) => (
        <li key={itemKey(item, i)}>{render(item)}</li>
      ))}
    </ul>
  );
}

/** Any JSON value, for an extension or field this library does not know. */
export function JsonValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <None />;
  if (typeof value === "string") return <>{value}</>;
  if (typeof value === "number" || typeof value === "boolean") return <>{String(value)}</>;
  if (Array.isArray(value) && value.every((v) => typeof v === "string")) return <Chips items={value} />;
  if (typeof value === "object" && !Array.isArray(value)) {
    return (
      <KeyValues
        pairs={Object.entries(value).map(([k, v]): [string, ReactNode] => [k, <JsonValue key={k} value={v} />])}
      />
    );
  }
  return <pre className="json-view">{JSON.stringify(value, null, 2)}</pre>;
}

/** A value's JSON, folded away until asked for. */
export function RawJson({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="dd-raw">
      <summary>{label}</summary>
      <pre className="json-view">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
