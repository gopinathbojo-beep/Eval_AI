import { Component, type ErrorInfo, type ReactNode } from "react";

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Application rendering failed", error, info.componentStack);
  }
  render() {
    if (this.state.failed) return (
      <main role="alert" className="mx-auto max-w-lg p-8 text-ink">
        <h1 className="text-xl font-semibold">The workspace could not load</h1>
        <p className="my-4">Reload the page to try again. Your saved work is still on the server.</p>
        <button className="rounded bg-pen px-4 py-2 text-on-pen" onClick={() => window.location.reload()}>Reload page</button>
      </main>
    );
    return this.props.children;
  }
}
