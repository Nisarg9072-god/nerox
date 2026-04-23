import { Component, type ErrorInfo, type ReactNode } from 'react';

type Props = { children: ReactNode };
type State = { hasError: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo): void {
    // intentionally silent in production UI
  }

  render() {
    if (this.state.hasError) {
      return <div className="p-6 text-sm text-muted-foreground">Something went wrong. Please refresh.</div>;
    }
    return this.props.children;
  }
}

