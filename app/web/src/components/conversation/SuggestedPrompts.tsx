/**
 * Ways to start an empty conversation, chosen from where the project is: the step the harness
 * suggests next, then the open steps after it (`startablePrompts`). Each is the step's `prompt`,
 * which a press puts in the message box for the researcher to edit and send; nothing is sent
 * until they do (docs/specs/app.md, "The phases").
 */

import "./SuggestedPrompts.css";

import { MessageSquarePlus } from "lucide-react";
import { useId } from "react";

import type { FlowStep } from "../../flow/types";
import { Button } from "../ui/Button";

export function SuggestedPrompts({
  steps,
  onChoose,
}: {
  steps: FlowStep[];
  onChoose: (step: FlowStep) => void;
}) {
  const id = useId();
  if (steps.length === 0) return null;
  return (
    <div role="group" aria-labelledby={id} className="suggested-prompts">
      <p id={id} className="suggested-prompts-heading">
        Suggested ways to start
      </p>
      <ul>
        {steps.map((step) => (
          <li key={step.id}>
            <Button
              size="small"
              icon={MessageSquarePlus}
              onPress={() => onChoose(step)}
            >
              {step.prompt}
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
