"use client";

import React from "react";

import { Button } from "@/components/ui/button";

type AnalyticsErrorBoundaryProps = {
  title?: string;
  message?: string;
  resetKey?: string;
  children: React.ReactNode;
};

type AnalyticsErrorBoundaryState = {
  hasError: boolean;
  error: Error | null;
};

export default class AnalyticsErrorBoundary extends React.Component<
  AnalyticsErrorBoundaryProps,
  AnalyticsErrorBoundaryState
> {
  state: AnalyticsErrorBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): AnalyticsErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Keep this local: analytics failures should not bring down the app shell.
    console.error("AnalyticsErrorBoundary caught error", error, info);
  }

  componentDidUpdate(prevProps: AnalyticsErrorBoundaryProps) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, error: null });
    }
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const title = this.props.title ?? "Analytics failed to load";
    const message = this.props.message
      ?? "A client-side error occurred while rendering analytics. Retry to continue.";

    return (
      <div className="rounded-[var(--radius-card)] border border-[color-mix(in_srgb,var(--status-critical)_30%,white)] bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] p-[var(--space-16)] shadow-[var(--shadow)]">
        <h2 className="text-base font-semibold text-[var(--status-critical)]">{title}</h2>
        <p className="mt-[var(--space-8)] text-sm text-[var(--status-critical)]">{message}</p>
        {this.state.error?.message ? (
          <p className="mt-[var(--space-8)] text-xs text-[var(--status-critical)]">{this.state.error.message}</p>
        ) : null}
        <div className="mt-[var(--space-12)]">
          <Button type="button" variant="outline" onClick={this.reset}>
            Retry
          </Button>
        </div>
      </div>
    );
  }
}

