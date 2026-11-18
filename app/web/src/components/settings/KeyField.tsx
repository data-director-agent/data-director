/**
 * The key field of the Settings page's AI account form (docs/specs/model-accounts.md, Enrolment).
 *
 * It links to the provider's own page for creating a key, and, if the typed key's prefix belongs
 * to another provider the profile allows, offers to switch to it. Neither decides anything: the
 * broker checks every key with the provider before it is saved.
 */

import { useId } from "react";

import { Button } from "../ui/Button";
import { COMPATIBLE, describe, guessProvider } from "./modelProviders";

export function KeyField({
  provider,
  offered,
  value,
  onChange,
  onSwitch,
}: {
  /** The provider the person has chosen. */
  provider: string;
  /** The providers the profile allows. */
  offered: string[];
  value: string;
  onChange: (value: string) => void;
  /** Choose another provider, keeping the typed key. */
  onSwitch: (provider: string) => void;
}) {
  const keyId = useId();
  const hintId = useId();
  const mismatchId = useId();
  const described = describe(provider);
  const guess = provider === COMPATIBLE ? null : guessProvider(value);
  const mismatch = guess !== null && guess !== provider && offered.includes(guess) ? guess : null;

  return (
    <div className="field">
      <label htmlFor={keyId}>{described.key}</label>
      <p className="hint" id={hintId}>
        {described.hint} It is checked with one free request before it is saved.
        {described.keysUrl && (
          <>
            {" "}
            <a href={described.keysUrl} target="_blank" rel="noreferrer">
              Create a key with {described.name}
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>
            . You can set a spending limit there too.
          </>
        )}
      </p>
      <input
        type="password"
        id={keyId}
        aria-describedby={mismatch ? `${hintId} ${mismatchId}` : hintId}
        autoComplete="off"
        spellCheck={false}
        required
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {mismatch && (
        <div className="model-account-mismatch" id={mismatchId}>
          <p>This looks like a key for {describe(mismatch).name}.</p>
          <Button variant="quiet" onPress={() => onSwitch(mismatch)}>
            Use {describe(mismatch).name} instead
          </Button>
        </div>
      )}
    </div>
  );
}
