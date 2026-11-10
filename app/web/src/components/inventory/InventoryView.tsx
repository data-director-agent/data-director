/**
 * An inventory in readable form (#472): what it amounts to, what it leaves out, its formats, its
 * files as folders, and the columns of its tables. Every fact comes from
 * `@data-director/inventory`; this component only lays them out.
 *
 * Given `editing`, as in the inventory editor, each file, folder and column has an Include
 * checkbox, each file can be described, given a part it plays and, where the command could not
 * tell, a format, and each column can be described. What the researcher stated is shown in place,
 * marked as theirs, and a status line counts what changed. Without `editing` the view is
 * read-only. A folder left out leaves out every file beneath it, opened or not, so a large folder
 * is left out with one choice.
 *
 * An inventory may list thousands of files, so a folder draws its contents only while it is open,
 * and a search shows at most `SHOWN` matches.
 */

import "./InventoryView.css";

import {
  applyEdits,
  canChooseFormat,
  countEdits,
  DESCRIPTION_LIMIT,
  describeEdits,
  FILE_ROLES,
  files as filesOf,
  folderTree,
  formatBytes,
  formatDate,
  formatFileCount,
  identificationLabel,
  IDENTIFICATION_METHODS,
  isOmitted,
  NO_EDITS,
  pronomUrl,
  searchFiles,
  summarise,
  type EditAction,
  type FileInventory,
  type FileRole,
  type FolderNode,
  type FormatGroup,
  type InventoryEdits,
  type InventoryFile,
  type TableField,
  type TableSummary,
  type TreeNode,
} from "@data-director/inventory";
import { createContext, useContext, useId, useMemo, useState } from "react";

/** The most search results drawn at once; the rest are counted. */
export const SHOWN = 200;

/** What the researcher changed, and how to change it, while the view is editing. */
export interface Editing {
  edits: InventoryEdits;
  dispatch: (action: EditAction) => void;
  /** Files that are new since the inventory this one replaces, to be marked so. */
  newPaths?: ReadonlySet<string> | undefined;
}

interface EditingState extends Editing {
  /** The files as the command found them, by path: the choices a format is chosen from. */
  found: ReadonlyMap<string, InventoryFile>;
}

/** The editing state, or null when the view is read-only. */
const EditingContext = createContext<EditingState | null>(null);

/** The words for each part a file may play. */
export const ROLE_LABELS: Record<FileRole, string> = {
  data: "Data",
  documentation: "Documentation",
  code: "Code",
  other: "Other",
};

export function InventoryView({
  inventory,
  editing,
}: {
  inventory: FileInventory;
  editing?: Editing | undefined;
}) {
  // While editing, the view shows what the researcher stated, and leaves nothing out of sight:
  // what is left out is shown unticked, so that it can be included again.
  const shown = useMemo(
    () => (editing ? applyEdits(inventory, { ...editing.edits, omitted: NO_EDITS.omitted }) : inventory),
    [inventory, editing],
  );
  const summary = useMemo(() => summarise(shown), [shown]);
  const made = formatDate(inventory.inventory_made_at);
  const state = useMemo<EditingState | null>(
    () =>
      editing
        ? { ...editing, found: new Map(filesOf(inventory).map((f) => [f.file_path, f])) }
        : null,
    [inventory, editing],
  );
  const changed = editing ? describeEdits(countEdits(inventory, editing.edits)) : null;
  return (
    <EditingContext.Provider value={state}>
      <div className="inventory-view">
        <p className="callout">
          This is everything the inventory holds, and so everything Data Director keeps and agents
          are shown: file names and folders, sizes, digests, formats and the column headings of
          tables{editing ? ", and anything you describe here" : ""}. It holds nothing else from
          inside the files.
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

        {editing && (
          <p role="status" className="inventory-left-out">
            {changed ? `Changes: ${changed}.` : "Nothing is left out or changed."}
          </p>
        )}

        <Formats formats={summary.formats} />
        <Files inventory={shown} />
        <Tables tables={summary.tables} />
      </div>
    </EditingContext.Provider>
  );
}

/**
 * An Include checkbox for a file or folder at `path`. One inside a folder that is left out is
 * shown unticked and cannot be changed until the folder is included again.
 */
function IncludePath({ path, label }: { path: string; label: string }) {
  const editing = useContext(EditingContext);
  if (!editing) return null;
  const { omitted } = editing.edits;
  const left = isOmitted(path, omitted.paths);
  return (
    <input
      type="checkbox"
      className="inventory-include"
      aria-label={`Include ${label}`}
      checked={!left}
      disabled={left && !omitted.paths.has(path)}
      onChange={(e) => editing.dispatch({ kind: e.currentTarget.checked ? "include" : "omit", path })}
    />
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

type Filter = "all" | "attention" | "new";

/** Whether the researcher would do well to look at `file`: its format is in doubt, or it is a table no one has described. */
function needsAttention(file: InventoryFile): boolean {
  const doubtful = file.file_identified_by === "none" || (file.file_pronom_ids?.length ?? 0) > 1;
  return doubtful || (Boolean(file.file_fields?.length) && !file.file_description);
}

function Files({ inventory }: { inventory: FileInventory }) {
  const searchId = useId();
  const filterId = useId();
  const editing = useContext(EditingContext);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const all = filesOf(inventory);
  const tree = useMemo(() => folderTree(all), [all]);
  const newPaths = editing?.newPaths;
  const found = useMemo(() => {
    const narrowed =
      filter === "attention"
        ? all.filter(needsAttention)
        : filter === "new" && newPaths
          ? all.filter((f) => newPaths.has(f.file_path))
          : null;
    if (!query.trim()) return narrowed;
    return searchFiles(narrowed ?? all, query);
  }, [all, query, filter, newPaths]);
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
      <div className="inventory-find">
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
        {editing && (
          <div className="field">
            <label htmlFor={filterId}>Show</label>
            <select
              id={filterId}
              value={filter}
              onChange={(e) => setFilter(e.currentTarget.value as Filter)}
            >
              <option value="all">Every file, as folders</option>
              <option value="attention">Files to look at</option>
              {newPaths && newPaths.size > 0 && <option value="new">Files new in this scan</option>}
            </select>
          </div>
        )}
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
            <li key={file.file_path} className="inventory-row">
              <IncludePath path={file.file_path} label={file.file_path} />
              <FileLine file={file} name={file.file_path} />
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

/** Every file beneath `node`, however deep. */
function filesUnder(node: FolderNode): string[] {
  return node.children.flatMap((child) => (child.kind === "file" ? [child.file.file_path] : filesUnder(child)));
}

/** A folder's contents: its subfolders, closed unless one is all there is, and its files. */
function Folder({ node }: { node: FolderNode }) {
  const only = node.children.length === 1;
  return (
    <ul className="inventory-tree">
      {node.children.map((child) => (
        <li key={child.path} className="inventory-row">
          <IncludePath
            path={child.path}
            label={child.kind === "folder" ? `the folder ${child.path}/` : child.path}
          />
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
      {isOpen && (
        <>
          <FolderRole node={node} />
          <Folder node={node} />
        </>
      )}
    </details>
  );
}

/** While editing, one choice of the part every file in a folder plays. */
function FolderRole({ node }: { node: FolderNode }) {
  const editing = useContext(EditingContext);
  const id = useId();
  if (!editing || isOmitted(node.path, editing.edits.omitted.paths)) return null;
  return (
    <div className="inventory-folder-role">
      <label htmlFor={id}>Part every file in {node.name}/ plays</label>{" "}
      <select
        id={id}
        value=""
        onChange={(e) => {
          const value = e.currentTarget.value;
          if (!value) return;
          editing.dispatch({
            kind: "role",
            paths: filesUnder(node),
            role: value === "none" ? null : (value as FileRole),
          });
        }}
      >
        <option value="">Choose…</option>
        {FILE_ROLES.map((role) => (
          <option key={role} value={role}>
            {ROLE_LABELS[role]}
          </option>
        ))}
        <option value="none">Not stated</option>
      </select>
    </div>
  );
}

function columns(count: number): string {
  return count === 1 ? "1 column" : `${count} columns`;
}

function FileLine({ file, name }: { file: InventoryFile; name: string }) {
  const editing = useContext(EditingContext);
  const ids = file.file_pronom_ids ?? [];
  const doubtful = file.file_identified_by === "none" || ids.length > 1;
  const isNew = editing?.newPaths?.has(file.file_path) ?? false;
  return (
    <span className="inventory-file">
      <span className="inventory-file-name">{name}</span>{" "}
      {isNew && <span className="status status-warn">New in this scan</span>}{" "}
      <span className="muted">
        {formatBytes(file.file_size)}
        {file.file_media_type && <>, {file.file_media_type}</>}
        {file.file_fields?.length ? <>, a table of {columns(file.file_fields.length)}</> : null}
      </span>{" "}
      {doubtful ? (
        <span className="status status-warn">
          {ids.length > 1 ? `Could be any of ${ids.length} formats` : identificationLabel("none")}
        </span>
      ) : file.file_identified_by === "researcher" ? (
        <span className="status status-ok">Format chosen by you</span>
      ) : (
        <span className="muted">({identificationLabel(file.file_identified_by).toLowerCase()})</span>
      )}
      {file.file_role && (
        <>
          {" "}
          <span className="inventory-role">{ROLE_LABELS[file.file_role]}</span>
        </>
      )}
      {file.file_description && <span className="inventory-description">{file.file_description}</span>}
      {editing && !isOmitted(file.file_path, editing.edits.omitted.paths) && (
        <FileEditor file={file} />
      )}
    </span>
  );
}

/**
 * What the researcher may state about one file, behind a disclosure so that a long list stays
 * short. A description is recorded when the field is left; a role or a format when it is chosen.
 */
function FileEditor({ file }: { file: InventoryFile }) {
  const editing = useContext(EditingContext);
  const id = useId();
  const [open, setOpen] = useState(false);
  if (!editing) return null;
  const path = file.file_path;
  const found = editing.found.get(path) ?? file;
  return (
    <details className="inventory-edit" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        Describe<span className="visually-hidden"> {path}</span>
      </summary>
      {open && (
        <div className="inventory-edit-fields">
          <div className="field">
            <label htmlFor={`${id}-description`}>What this file is</label>
            <textarea
              id={`${id}-description`}
              rows={2}
              maxLength={DESCRIPTION_LIMIT}
              defaultValue={file.file_description ?? ""}
              onBlur={(e) => editing.dispatch({ kind: "describe", path, text: e.currentTarget.value })}
            />
          </div>
          <div className="field">
            <label htmlFor={`${id}-role`}>Part it plays</label>
            <select
              id={`${id}-role`}
              value={file.file_role ?? ""}
              onChange={(e) =>
                editing.dispatch({
                  kind: "role",
                  paths: [path],
                  role: (e.currentTarget.value || null) as FileRole | null,
                })
              }
            >
              <option value="">Not stated</option>
              {FILE_ROLES.map((role) => (
                <option key={role} value={role}>
                  {ROLE_LABELS[role]}
                </option>
              ))}
            </select>
          </div>
          {canChooseFormat(found) && <FormatChoice file={found} id={id} />}
        </div>
      )}
    </details>
  );
}

/** The format of a file the command could not be sure of: one of its matches, a media type, or both. */
function FormatChoice({ file, id }: { file: InventoryFile; id: string }) {
  const editing = useContext(EditingContext);
  if (!editing) return null;
  const path = file.file_path;
  const stated = editing.edits.files.get(path)?.format;
  const ids = file.file_pronom_ids ?? [];
  function choose(pronomId: string | undefined, mediaType: string | undefined) {
    editing?.dispatch({
      kind: "format",
      path,
      format: pronomId || mediaType ? { ...(pronomId ? { pronomId } : {}), ...(mediaType ? { mediaType } : {}) } : null,
    });
  }
  return (
    <fieldset className="inventory-format">
      <legend>Format</legend>
      {ids.length > 1 && (
        <div role="radiogroup" aria-label="Which of the formats found it is">
          {[undefined, ...ids].map((puid, index) => (
            <span key={puid ?? ""} className="inventory-choice">
              <input
                id={`${id}-puid-${index}`}
                type="radio"
                name={`${id}-puid`}
                checked={stated?.pronomId === puid}
                onChange={() => choose(puid, stated?.mediaType)}
              />
              <label htmlFor={`${id}-puid-${index}`}>{puid ? <code>{puid}</code> : "Not chosen"}</label>
            </span>
          ))}
        </div>
      )}
      <div className="field">
        <label htmlFor={`${id}-media`}>Media type</label>
        <p className="hint muted" id={`${id}-media-hint`}>
          Such as <code>text/csv</code> or <code>application/x-hdf5</code>.
        </p>
        <input
          id={`${id}-media`}
          type="text"
          aria-describedby={`${id}-media-hint`}
          defaultValue={stated?.mediaType ?? file.file_media_type ?? ""}
          onBlur={(e) => {
            const value = e.currentTarget.value.trim();
            const mediaType = value && value !== file.file_media_type ? value : undefined;
            if (mediaType !== stated?.mediaType) choose(stated?.pronomId, mediaType);
          }}
        />
      </div>
    </fieldset>
  );
}

/** An Include checkbox for the column `name` of the table at `path`. */
function IncludeColumn({ path, name }: { path: string; name: string }) {
  const editing = useContext(EditingContext);
  if (!editing) return null;
  const { omitted } = editing.edits;
  const tableOmitted = isOmitted(path, omitted.paths);
  const left = tableOmitted || (omitted.columns.get(path)?.has(name) ?? false);
  return (
    <input
      type="checkbox"
      className="inventory-include"
      aria-label={`Include the column ${name} of ${path}`}
      checked={!left}
      disabled={tableOmitted}
      onChange={(e) =>
        editing.dispatch({
          kind: e.currentTarget.checked ? "include-column" : "omit-column",
          path,
          column: name,
        })
      }
    />
  );
}

/** A column's description: a field while editing, its text otherwise. */
function ColumnDescription({ path, field }: { path: string; field: TableField }) {
  const editing = useContext(EditingContext);
  if (!editing) return <>{field.field_description ?? ""}</>;
  const left =
    isOmitted(path, editing.edits.omitted.paths) ||
    (editing.edits.omitted.columns.get(path)?.has(field.name) ?? false);
  if (left) return null;
  return (
    <input
      type="text"
      className="inventory-column-description"
      aria-label={`Describe the column ${field.name} of ${path}`}
      maxLength={DESCRIPTION_LIMIT}
      defaultValue={field.field_description ?? ""}
      onBlur={(e) =>
        editing.dispatch({ kind: "describe-column", path, column: field.name, text: e.currentTarget.value })
      }
    />
  );
}

function Tables({ tables }: { tables: readonly TableSummary[] }) {
  const editing = useContext(EditingContext) !== null;
  if (tables.length === 0) return null;
  const described = editing || tables.some((t) => t.fields.some((f) => f.field_description));
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
                  {editing && <th scope="col">Include</th>}
                  <th scope="col">Column</th>
                  <th scope="col">Type</th>
                  <th scope="col">Format</th>
                  {described && <th scope="col">Description</th>}
                </tr>
              </thead>
              <tbody>
                {table.fields.map((field, index) => (
                  <tr key={`${index}-${field.name}`}>
                    {editing && (
                      <td>
                        <IncludeColumn path={table.path} name={field.name} />
                      </td>
                    )}
                    <td>
                      <code>{field.name}</code>
                    </td>
                    <td>{field.field_type ?? <span className="muted">Not known</span>}</td>
                    <td>{field.field_format ?? ""}</td>
                    {described && (
                      <td>
                        <ColumnDescription path={table.path} field={field} />
                      </td>
                    )}
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
