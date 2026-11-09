/**
 * Plain-language wording for what a card and a payload say, in British English. Kept in step with
 * the LinkML descriptions in sdk/src/dd_sdk/schema/data_director.yaml.
 */

import type { DerivationHow } from "./spec/types";

export const DERIVATION: Record<DerivationHow, string> = {
  template: "Filled in from a fixed template",
  model: "Written by a language model",
  lexical: "Matched by keyword rules",
  registry: "Taken from a registry record",
};

/** Short labels for a derivation, for a badge beside the value it describes. */
export const DERIVATION_SHORT: Record<DerivationHow, string> = {
  template: "Template",
  model: "Language model",
  lexical: "Keyword rules",
  registry: "Registry",
};

/** Words for a class name such as `DatasetProfile`: "dataset profile". */
export function className(name: string): string {
  return name.replace(/([a-z0-9])([A-Z])/g, "$1 $2").toLowerCase();
}

/** Words for a slot or file name such as `media_types` or `soil-chemistry.profile`. */
export function fieldName(name: string): string {
  const words = name.replace(/[_.-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
