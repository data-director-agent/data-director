/**
 * A short text question that suggests answers (docs/specs/app.md, rule 21; `question_suggestions`
 * in docs/specs/contract.md, rule 23): a one-line text box whose list offers the suggestions,
 * narrowed to those containing what has been typed. The researcher may take one or keep their own
 * words: the answer is always the text in the box.
 */

import "./SuggestedAnswer.css";

import { ChevronDown } from "lucide-react";
import {
  Button as AriaButton,
  ComboBox,
  Input,
  Label,
  ListBox,
  ListBoxItem,
  Popover,
  useFilter,
} from "react-aria-components";

import type { ReactNode } from "react";

interface Props {
  /** The id the field's parts are named from. */
  id: string;
  suggestions: string[];
  words: string;
  onWords: (words: string) => void;
  /** The count of characters left, drawn under the box and named by `${id}-count`. */
  count?: ReactNode;
  /** The id of the error shown for the question, if any: the box is then invalid. */
  errorId?: string | null;
}

export function SuggestedAnswer({ id, suggestions, words, onWords, count, errorId }: Props) {
  const { contains } = useFilter({ sensitivity: "base" });
  const typed = words.trim();
  const items = suggestions
    .filter((label) => typed === "" || contains(label, typed))
    .map((label) => ({ id: label, label }));
  return (
    <ComboBox
      className="suggested-answer"
      items={items}
      inputValue={words}
      onInputChange={onWords}
      onSelectionChange={(key) => {
        if (key !== null) onWords(String(key));
      }}
      allowsCustomValue
      menuTrigger="focus"
      // Filtered above, so that what was typed always narrows the list.
      defaultFilter={() => true}
      aria-describedby={[`${id}-suggested`, count && `${id}-count`, errorId].filter(Boolean).join(" ")}
      isInvalid={Boolean(errorId)}
    >
      <Label className="visually-hidden">Your answer</Label>
      <div className="suggested-answer-field">
        <Input id={`${id}-words`} />
        <AriaButton className="button button-secondary" aria-label="Show suggestions">
          <ChevronDown className="button-icon" size="1.125em" aria-hidden="true" />
        </AriaButton>
      </div>
      <p className="hint" id={`${id}-suggested`}>
        Choose a suggestion or answer in your own words.
      </p>
      {count}
      <Popover className="suggested-answer-popover">
        <ListBox className="suggested-answer-list">
          {(item: { id: string; label: string }) => (
            <ListBoxItem id={item.id} textValue={item.label} className="suggested-answer-option">
              {item.label}
            </ListBoxItem>
          )}
        </ListBox>
      </Popover>
    </ComboBox>
  );
}
