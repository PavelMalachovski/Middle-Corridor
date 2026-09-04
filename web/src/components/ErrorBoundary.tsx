import { Component, type ErrorInfo, type ReactNode } from "react";

/**
 * Граница ошибок: падение одной части интерфейса (карта, панель, управление)
 * не гасит остальные. fallback получает ошибку и reset — повторный монтаж
 * детей с чистого листа.
 */

interface Props {
  children: ReactNode;
  fallback: (error: Error, reset: () => void) => ReactNode;
  /** Подпись в консоли: какая часть упала. */
  scope: string;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[${this.props.scope}] упал:`, error, info.componentStack);
  }

  reset = (): void => this.setState({ error: null });

  render(): ReactNode {
    if (this.state.error) return this.props.fallback(this.state.error, this.reset);
    return this.props.children;
  }
}
