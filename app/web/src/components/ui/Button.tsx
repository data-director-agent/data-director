/**
 * The shell's buttons: React Aria's Button and ToggleButton, styled from the tokens. Every button
 * in the shell is one of these, so that they look and behave alike (ESLint rejects a bare
 * `<button>`).
 *
 * - `primary`: the one action a form or page exists for (Run, Send). At most one per view.
 * - `secondary` (the default): every other action.
 * - `quiet`: an action beside content it acts on (Open, Copy run id), drawn without a frame
 *   until it is hovered or focused.
 * - `danger`: an action that removes something the reader entered.
 *
 * An `icon` (a Lucide icon component, ISC licence) is drawn before the label. It is decoration:
 * hidden from screen readers, so the label must still say what the button does.
 *
 * A button whose action is under way takes `isPending`: it keeps its focus, says it is busy to
 * screen readers and cannot be pressed again, where `isDisabled` would drop the focus.
 */

import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import {
  Button as AriaButton,
  ToggleButton as AriaToggleButton,
  composeRenderProps,
  type ButtonProps as AriaButtonProps,
  type ToggleButtonProps as AriaToggleButtonProps,
} from "react-aria-components";

import "./Button.css";

export type ButtonVariant = "primary" | "secondary" | "quiet" | "danger";
export type ButtonSize = "medium" | "small";

interface Look {
  variant?: ButtonVariant | undefined;
  size?: ButtonSize | undefined;
  icon?: LucideIcon | undefined;
}

function classes({ variant = "secondary", size = "medium" }: Look, extra?: string): string {
  return ["button", `button-${variant}`, size === "small" && "button-small", extra]
    .filter(Boolean)
    .join(" ");
}

export interface ButtonProps extends AriaButtonProps, Look {}

/** The icon, sized in `em` so that it follows the button's font size. */
function withIcon<T>(
  Icon: LucideIcon | undefined,
  children: ReactNode | ((values: T & { defaultChildren: ReactNode }) => ReactNode),
) {
  if (!Icon) return children;
  return composeRenderProps(children, (content) => (
    <>
      <Icon className="button-icon" size="1.125em" aria-hidden="true" />
      {content}
    </>
  ));
}

export function Button({ variant, size, icon, className, children, ...props }: ButtonProps) {
  return (
    <AriaButton
      {...props}
      className={composeRenderProps(className, (extra) => classes({ variant, size }, extra))}
    >
      {withIcon(icon, children)}
    </AriaButton>
  );
}

export interface ToggleButtonProps extends AriaToggleButtonProps, Look {}

export function ToggleButton({
  variant,
  size,
  icon,
  className,
  children,
  ...props
}: ToggleButtonProps) {
  return (
    <AriaToggleButton
      {...props}
      className={composeRenderProps(className, (extra) => classes({ variant, size }, extra))}
    >
      {withIcon(icon, children)}
    </AriaToggleButton>
  );
}
