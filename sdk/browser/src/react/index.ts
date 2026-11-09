/** The React components of `@data-director/agent-view`. Import its styles once from `../styles.css`. */

export {
  AgentViewProvider,
  type AgentViewOptions,
  type DocumentProps,
  type ExtensionViewProps,
  type PayloadRendererProps,
  type Slots,
  useAgentView,
} from "./Provider";
export { AgentCardView } from "./card/AgentCardView";
export { AgentSpecView } from "./card/AgentSpecView";
export { BUILT_IN_EXTENSIONS, ExtensionView } from "./card/ExtensionView";
export { ManifestView } from "./card/ManifestView";
export type { HeadingLevel } from "./card/parts";
export { PayloadView } from "./payload/PayloadView";
export { Badge } from "./payload/Badge";
export { Facts } from "./payload/Facts";
export { RecordsTable } from "./payload/RecordsTable";
export { RestsOn } from "./payload/RestsOn";
export { Scalar } from "./payload/Scalar";
export { Section } from "./payload/Section";
