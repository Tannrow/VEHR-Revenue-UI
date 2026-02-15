"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type BIEmbedConfig = {
  type: "report";
  reportId: string;
  embedUrl: string;
  accessToken: string;
  expiresOn: string;
};

type EmbeddedReport = {
  on: (eventName: string, handler: (event?: unknown) => void) => void;
  off: (eventName: string, handler?: (event?: unknown) => void) => void;
  setAccessToken: (token: string) => Promise<void>;
};

type EmbeddedReportRef = {
  reportId: string;
  embedUrl: string;
};

type PowerBIService = {
  embed: (element: HTMLElement, config: Record<string, unknown>) => EmbeddedReport;
  reset: (element: HTMLElement) => void;
};

const TOKEN_REFRESH_BUFFER_MS = 60_000;
const MIN_REFRESH_DELAY_MS = 10_000;

function toErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

function isAuthRelatedPowerBIError(event: unknown): boolean {
  if (!event || typeof event !== "object") {
    return false;
  }
  const maybeDetail = (event as { detail?: unknown }).detail;
  if (!maybeDetail || typeof maybeDetail !== "object") {
    return false;
  }

  const message = String((maybeDetail as { message?: unknown }).message ?? "").toLowerCase();
  const detailed = String((maybeDetail as { detailedMessage?: unknown }).detailedMessage ?? "").toLowerCase();
  const errorCode = String((maybeDetail as { errorCode?: unknown }).errorCode ?? "").toLowerCase();
  const source = `${message} ${detailed} ${errorCode}`;
  return source.includes("token")
    || source.includes("unauthorized")
    || source.includes("forbidden")
    || source.includes("401")
    || source.includes("403");
}

type PowerBIReportEmbedProps = {
  reportKey: string;
  className?: string;
};

export function PowerBIReportEmbed({ reportKey, className }: PowerBIReportEmbedProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const moduleRef = useRef<typeof import("powerbi-client") | null>(null);
  const serviceRef = useRef<PowerBIService | null>(null);
  const reportRef = useRef<EmbeddedReport | null>(null);
  const reportInfoRef = useRef<EmbeddedReportRef | null>(null);
  const reportErrorHandlerRef = useRef<((event?: unknown) => void) | null>(null);
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const refreshInFlightRef = useRef<Promise<void> | null>(null);
  const unmountedRef = useRef(false);
  const refreshTokenRef = useRef<() => Promise<void>>(async () => undefined);

  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const clearRefreshTimer = useCallback(() => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = null;
    }
  }, []);

  const scheduleTokenRefresh = useCallback(
    (expiresOn: string) => {
      clearRefreshTimer();
      const expiresAtMs = new Date(expiresOn).getTime();
      if (Number.isNaN(expiresAtMs)) {
        return;
      }
      const delay = Math.max(expiresAtMs - Date.now() - TOKEN_REFRESH_BUFFER_MS, MIN_REFRESH_DELAY_MS);
      refreshTimerRef.current = setTimeout(() => {
        void refreshTokenRef.current();
      }, delay);
    },
    [clearRefreshTimer],
  );

  const fetchEmbedConfig = useCallback(async () => {
    return apiFetch<BIEmbedConfig>(
      `/api/v1/bi/embed-config?report_key=${encodeURIComponent(reportKey)}`,
      { cache: "no-store" },
    );
  }, [reportKey]);

  const ensurePowerBI = useCallback(async (): Promise<typeof import("powerbi-client")> => {
    if (moduleRef.current) {
      return moduleRef.current;
    }
    const powerBI = await import("powerbi-client");
    moduleRef.current = powerBI;
    if (!serviceRef.current) {
      serviceRef.current = new powerBI.service.Service(
        powerBI.factories.hpmFactory,
        powerBI.factories.wpmpFactory,
        powerBI.factories.routerFactory,
      ) as unknown as PowerBIService;
    }
    return powerBI;
  }, []);

  const embedOrUpdateReport = useCallback(
    async (config: BIEmbedConfig, forceReEmbed: boolean) => {
      const powerBI = await ensurePowerBI();
      const container = containerRef.current;
      const service = serviceRef.current;
      if (!container || !service) {
        return;
      }

      const current = reportInfoRef.current;
      const sameReport = current
        && current.reportId === config.reportId
        && current.embedUrl === config.embedUrl;

      if (reportRef.current && sameReport && !forceReEmbed) {
        await reportRef.current.setAccessToken(config.accessToken);
        scheduleTokenRefresh(config.expiresOn);
        return;
      }

      if (reportRef.current) {
        if (reportErrorHandlerRef.current) {
          reportRef.current.off("error", reportErrorHandlerRef.current);
        }
        reportRef.current = null;
        reportErrorHandlerRef.current = null;
      }
      service.reset(container);

      const embedConfig: Record<string, unknown> = {
        type: "report",
        id: config.reportId,
        embedUrl: config.embedUrl,
        accessToken: config.accessToken,
        tokenType: powerBI.models.TokenType.Embed,
        settings: {
          panes: {
            filters: { visible: false },
            pageNavigation: { visible: true },
          },
        },
      };
      const report = service.embed(container, embedConfig);
      reportInfoRef.current = {
        reportId: config.reportId,
        embedUrl: config.embedUrl,
      };
      reportRef.current = report;

      const onReportError = (event?: unknown) => {
        if (isAuthRelatedPowerBIError(event)) {
          void refreshTokenRef.current();
        }
      };
      report.on("error", onReportError);
      reportErrorHandlerRef.current = onReportError;
      scheduleTokenRefresh(config.expiresOn);
    },
    [ensurePowerBI, scheduleTokenRefresh],
  );

  const refreshToken = useCallback(async () => {
    if (refreshInFlightRef.current) {
      return refreshInFlightRef.current;
    }

    const currentRefresh = (async () => {
      try {
        const config = await fetchEmbedConfig();
        await embedOrUpdateReport(config, false);
        if (!unmountedRef.current) {
          setErrorMessage(null);
          setIsLoading(false);
        }
      } catch (error) {
        if (!unmountedRef.current) {
          setErrorMessage(toErrorMessage(error, "Unable to refresh report access token."));
        }
      } finally {
        refreshInFlightRef.current = null;
      }
    })();
    refreshInFlightRef.current = currentRefresh;
    return currentRefresh;
  }, [embedOrUpdateReport, fetchEmbedConfig]);

  useEffect(() => {
    refreshTokenRef.current = refreshToken;
  }, [refreshToken]);

  useEffect(() => {
    let cancelled = false;
    unmountedRef.current = false;
    setIsLoading(true);
    setErrorMessage(null);
    const containerElement = containerRef.current;

    async function initializeEmbed() {
      try {
        const config = await fetchEmbedConfig();
        if (cancelled) {
          return;
        }
        await embedOrUpdateReport(config, true);
        if (!cancelled) {
          setIsLoading(false);
        }
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(toErrorMessage(error, "Unable to load report embed configuration."));
          setIsLoading(false);
        }
      }
    }

    void initializeEmbed();

    return () => {
      cancelled = true;
      unmountedRef.current = true;
      clearRefreshTimer();
      const service = serviceRef.current;
      const report = reportRef.current;
      if (report && reportErrorHandlerRef.current) {
        report.off("error", reportErrorHandlerRef.current);
      }
      if (containerElement && service) {
        service.reset(containerElement);
      }
      reportRef.current = null;
      reportInfoRef.current = null;
      reportErrorHandlerRef.current = null;
    };
  }, [clearRefreshTimer, embedOrUpdateReport, fetchEmbedConfig]);

  return (
    <div className={cn("space-y-[var(--space-12)]", className)}>
      {errorMessage ? (
        <div className="rounded-[var(--radius-6)] border border-[color-mix(in_srgb,var(--status-critical)_30%,white)] bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] px-[var(--space-12)] py-[var(--space-10)] text-sm text-[var(--status-critical)]">
          <p>{errorMessage}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-[var(--space-8)]"
            onClick={() => {
              setIsLoading(true);
              setErrorMessage(null);
              void refreshToken();
            }}
          >
            Retry
          </Button>
        </div>
      ) : null}

      <div
        className="relative min-h-[640px] overflow-hidden rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] shadow-[var(--shadow)]"
        data-testid="powerbi-report-container"
      >
        {isLoading ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-[color-mix(in_srgb,var(--surface)_90%,white)] text-sm text-[var(--neutral-muted)]">
            Loading chart audit report...
          </div>
        ) : null}
        <div ref={containerRef} className="h-[640px] w-full" />
      </div>
    </div>
  );
}
