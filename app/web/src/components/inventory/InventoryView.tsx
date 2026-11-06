/**
 * An inventory in readable form (#472): what it amounts to, what it leaves out, its formats, its
 * files as folders, and the columns of its tables. Every fact comes from
 * `@data-director/inventory`; this component only lays them out. The view is read-only: leaving
 * out a file or a column before the inventory is added is still to come (#472).
 *
 * An inventory may list thousands of files, so a folder draws its contents only while it is open,
 * and a search shows at most `SHOWN` matches.
 */

import "./InventoryView.css";

import {
  files as filesOf,
  folderTree,
  formatBytes,
  formatDate,
  formatFileCount,
  identificationLabel,
  IDENTIFICATION_METHODS,
  pronomUrl,
  searchFiles,
  summarise,
  type FileInventory,
  type FolderNode,
  type FormatGroup,
  type InventoryFile,
  type TableSummary,
  type TreeNode,
} from "@data-director/inventory";
import { useId, useMemo, useState } from "react";

/** The most search results drawn at once; the rest are counted. */
export const SHOWN = 200;

export function InventoryView({ inventory }: { inventory: FileInventory }) {
  const summary = useMemo(() => summarise(inventory), [inventory]);
  const made = formatDate(inventory.inventory_made_at);
  return (
    <div className="inventory-view">
      <p className="callout">
        This is everything the inventory holds, and so everything Data Director keeps and agents
        are shown: file names and folders, sizes, digests, formats and the column headings of
        tables. It holds nothing else from inside the files.
      </p>

      <dl className="facts">
        <div>
          <dt>Files</dt>
          <dd>
            {formatFileCount(summary.fileCount)}, {formatBytes(summary.bytes)} in all
          </dd>
        </div>
        <div>
          <dt>Made</dt>
          <dd>
            {made ? `${made} ` : ""}by {inventory.inventory_tool} {inventory.inventory_tool_version}
          </dd>
        </div>
        {inventory.inventory_identified_with && (
          <div>
            <dt>Formats found with</dt>
            <dd>{inventory.inventory_identified_with}</dd>
          </div>
        )}
        <div>
          <dt>How formats were found</dt>
          <dd>
            <ul className="plain-list">
              {IDENTIFICATION_METHODS.filter((m) => summary.identification[m] > 0).map((m) => (
                <li key={m}>
                  {identificationLabel(m)}: {formatFileCount(summary.identification[m])}
                </li>
              ))}
            </ul>
          </dd>
        </div>
      </dl>

      {summary.limitations.length > 0 && (
        <section aria-labelledby="inventory-limits">
          <h3 id="inventory-limits">What it leaves out</h3>
          <ul>
            {summary.limitations.map((limit) => (
              <li key={limit}>{limit}</li>
            ))}
          </ul>
        </section>
      )}

      <Formats formats={summary.formats} />
      <Files inventory={inventory} />
      <Tables tables={summary.tables} />
    </div>
  );
}

function Formats({ formats }: { formats: readonly FormatGroup[] }) {
  if (formats.length === 0) return null;
  return (
    <section aria-labelledby="inventory-formats">
      <h3 id="inventory-formats">Formats</h3>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Media type</th>
              <th scope="col">PRONOM</th>
              <th scope="col">Files</th>
              <th scope="col">Size</th>
            </tr>
          </thead>
          <tbody>
            {formats.map((format) => (
              <tr key={format.mediaType ?? ""}>
                <td>{format.mediaType ? <code>{format.mediaType}</code> : "Not known"}</td>
                <td>
                  <Puids ids={format.pronomIds} />
                </td>
                <td>{format.fileCount}</td>
                <td>{formatBytes(format.bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Puids({ ids }: { ids: readonly string[] }) {
  if (ids.length === 0) return <span className="muted">None</span>;
  return (
    <>
      {ids.map((id, index) => (
        <span key={id}>
          {index > 0 && ", "}
          <a href={pronomUrl(id)}>{id}</a>
        </span>
      ))}
    </>
  );
}

function Files({ inventory }: { inventory: FileInventory }) {
  const searchId = useId();
  const [query, setQuery] = useState("");
  const all = filesOf(inventory);
  const tree = useMemo(() => folderTree(all), [all]);
  const found = useMemo(() => (query.trim() ? searchFiles(all, query) : null), [all, query]);
  if (all.length === 0) {
    return (
      <section aria-labelledby="inventory-files">
        <h3 id="inventory-files">Files</h3>
        <p>The inventory lists no files.</p>
      </section>
    );
  }
  return (
    <section aria-labelledby="inventory-files">
      <h3 id="inventory-files">Files</h3>
      <div className="field">
        <label htmlFor={searchId}>Find files</label>
        <p className="hint muted" id={`${searchId}-hint`}>
          By name, folder, format or column heading.
        </p>
        <input
          id={searchId}
          type="text"
          aria-describedby={`${searchId}-hint`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {found ? <Found files={found} /> : <Folder node={tree} />}
    </section>
  );
}

function Found({ files }: { files: InventoryFile[] }) {
  return (
    <>
      <p role="status">
        {files.length === 0
          ? "No file matches."
          : files.length > SHOWN
            ? `${formatFileCount(files.length)} match; the first ${SHOWN} are shown.`
            : `${formatFileCount(files.length)} ${files.length === 1 ? "matches" : "match"}.`}
      </p>
      {files.length > 0 && (
        <ul className="inventory-tree">
          {files.slice(0, SHOWN).map((file) => (
            <li key={file.file_path}>
              <FileLine file={file} name={file.file_path} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** A folder's contents: its subfolders, closed unless one is all there is, and its files. */
function Folder({ node }: { node: FolderNode }) {
  const only = node.children.length === 1;
  return (
    <ul className="inventory-tree">
      {node.children.map((child) => (
        <li key={child.path}>
          <Node node={child} open={only} />
        </li>
      ))}
    </ul>
  );
}

function Node({ node, open }: { node: TreeNode; open: boolean }) {
  const [isOpen, setOpen] = useState(open);
  if (node.kind === "file") return <FileLine file={node.file} name={node.name} />;
  return (
    <details open={isOpen} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <span className="inventory-folder">{node.name}/</span>{" "}
        <span className="muted">
          {formatFileCount(node.fileCount)}, {formatBytes(node.bytes)}
        </span>
      </summary>
      {isOpen && <Folder node={node} />}
    </details>
  );
}

function columns(count: number): string {
  return count === 1 ? "1 column" : `${count} columns`;
}

function FileLine({ file, name }: { file: InventoryFile; name: string }) {
  const ids = file.file_pronom_ids ?? [];
  const doubtful = file.file_identified_by === "none" || ids.length > 1;
  return (
    <span className="inventory-file">
      <span className="inventory-file-name">{name}</span>{" "}
      <span className="muted">
        {formatBytes(file.file_size)}
        {file.file_media_type && <>, {file.file_media_type}</>}
        {file.file_fields?.length ? <>, a table of {columns(file.file_fields.length)}</> : null}
      </span>{" "}
      {doubtful ? (
        <span className="status status-warn">
          {ids.length > 1 ? `Could be any of ${ids.length} formats` : identificationLabel("none")}
        </span>
      ) : (
        <span className="muted">({identificationLabel(file.file_identified_by).toLowerCase()})</span>
      )}
    </span>
  );
}

function Tables({ tables }: { tables: readonly TableSummary[] }) {
  if (tables.length === 0) return null;
  return (
    <section aria-labelledby="inventory-tables">
      <h3 id="inventory-tables">Tables</h3>
      <p>
        The columns of each table, with the type inferred from a sample of its rows. Column
        headings are kept and shown to agents.
      </p>
      {tables.map((table) => (
        <details key={table.path} className="inventory-table">
          <summary>
            <span className="inventory-file-name">{table.path}</span>{" "}
            <span className="muted">{columns(table.fields.length)}</span>
          </summary>
          <div className="table-scroll">
            <table className="data-table">
              <caption className="visually-hidden">Columns of {table.path}</caption>
              <thead>
                <tr>
                  <th scope="col">Column</th>
                  <th scope="col">Type</th>
                  <th scope="col">Format</th>
                </tr>
              </thead>
              <tbody>
                {table.fields.map((field, index) => (
                  <tr key={`${index}-${field.name}`}>
                    <td>
                      <code>{field.name}</code>
                    </td>
                    <td>{field.field_type ?? <span className="muted">Not known</span>}</td>
                    <td>{field.field_format ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </section>
  );
}
