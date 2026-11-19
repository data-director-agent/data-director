/**
 * Catches a page that throws while it is drawn, so the person sees the "something went wrong"
 * page inside the app frame rather than a blank window. It resets when `resetKey` changes (the
 * address), so leaving the broken page by any link or Back works.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

import { SomethingWentWrongPage } from "./ErrorPage";

interface Props {
  resetKey: string;
  children: ReactNode;
}

export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("A page failed while it was drawn:", error, info.componentStack);
  }

  override componentDidUpdate(previous: Props): void {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) this.setState({ failed: false });
  }

  override render(): ReactNode {
    if (this.state.failed) return <SomethingWentWrongPage onRetry={() => this.setState({ failed: false })} />;
    return this.props.children;
  }
}
