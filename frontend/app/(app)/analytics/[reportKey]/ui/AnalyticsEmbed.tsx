"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { models } from "powerbi-client";

import { fetchEmbedConfig, type EmbedConfigResponse } from "@/lib/bi";

const PowerBIEmbed = dynamic(
  () => import("powerbi-client-react").then((mod) => mod.PowerBIEmbed),
  { ssr: false },
);

const REFRESH_BUFFER_MS = 2 * 60 * 1000;
const FALLBACK_REFRESH_MS = 50 * 60 * 1000;
const MIN_DELAY_MS = 5 * 1000;

type AnalyticsEmbedProps = {
  reportKey: string;
};

type EmbeddedReportHandle = {
  setAccessToken: (token: string) => Promise<void>;
};

function expiryIso(config: EmbedConfigResponse | null): string | null {
  if (!config) {
    return null;
  }
  if (config.tokenExpiry && config.tokenExpiry.trim()) {
    return config.tokenExpiry;
  }
  if (config.expiresOn && config.expiresOn.trim()) {
    return config.expiresOn;
  }
  return null;
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }
  return "Unable to load analytics report.";
}

export default function AnalyticsEmbed({ reportKey }: AnalyticsEmbedProps) {
  const reportRef = useRef<EmbeddedReportHandle | null>(null);
  const configRef = useRef<EmbedConfigResponse | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inFlightRefreshRef = useRef<Promise<void> | null>(null);
  const isMountedRef = useRef(true);

  const [config, setConfig] = useState<EmbedConfigResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    configRef.current = config;
  }, [config]);

  const clearSchedules = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const loadConfig = useCallback(
    async (showLoader: boolean) => {
      if (showLoader) {
        setIsLoading(true);
      }
      setError(null);
      try {
        const nextConfig = await fetchEmbedConfig(reportKey);
        if (!isMountedRef.current) {
          return;
        }
        setConfig(nextConfig);
      } catch (err) {
        if (!isMountedRef.current) {
          return;
        }
        setError(toErrorMessage(err));
      } finally {
        if (isMountedRef.current && showLoader) {
          setIsLoading(false);
        }
      }
    },
    [reportKey],
  );

  const refreshToken = useCallback(async () => {
    if (inFlightRefreshRef.current) {
      return inFlightRefreshRef.current;
    }

    const refreshPromise = (async () => {
      try {
        const nextConfig = await fetchEmbedConfig(reportKey);
        if (!isMountedRef.current) {
          return;
        }

        const currentConfig = configRef.current;
        const sameReport = currentConfig
          && currentConfig.reportId === nextConfig.reportId
          && currentConfig.embedUrl === nextConfig.embedUrl;

        if (sameReport && reportRef.current) {
          await reportRef.current.setAccessToken(nextConfig.accessToken);
          setConfig({
            ...currentConfig,
            accessToken: nextConfig.accessToken,
            tokenExpiry: nextConfig.tokenExpiry,
            expiresOn: nextConfig.expiresOn,
          });
        } else {
          setConfig(nextConfig);
        }
        setError(null);
      } catch (err) {
        if (isMountedRef.current) {
          setError(toErrorMessage(err));
        }
      } finally {
        inFlightRefreshRef.current = null;
      }
    })();

    inFlightRefreshRef.current = refreshPromise;
    return refreshPromise;
  }, [reportKey]);

  useEffect(() => {
    isMountedRef.current = true;
    void loadConfig(true);
    return () => {
      isMountedRef.current = false;
      clearSchedules();
    };
  }, [clearSchedules, loadConfig]);

  useEffect(() => {
    clearSchedules();
    if (!config) {
      return;
    }

    const expiresAt = expiryIso(config);
    if (expiresAt) {
      const expiresAtMs = new Date(expiresAt).getTime();
      if (!Number.isNaN(expiresAtMs)) {
        const delayMs = Math.max(expiresAtMs - Date.now() - REFRESH_BUFFER_MS, MIN_DELAY_MS);
        timeoutRef.current = setTimeout(() => {
          void refreshToken();
        }, delayMs);
        return;
      }
    }

    intervalRef.current = setInterval(() => {
      void refreshToken();
    }, FALLBACK_REFRESH_MS);
  }, [clearSchedules, config, refreshToken]);

  const embedConfig = useMemo(() => {
    if (!config) {
      return undefined;
    }
    return {
      type: "report",
      id: config.reportId,
      embedUrl: config.embedUrl,
      accessToken: config.accessToken,
      tokenType: models.TokenType.Embed,
      settings: {
        panes: {
          filters: {
            visible: false,
          },
          pageNavigation: {
            visible: true,
          },
        },
        background: models.BackgroundType.Transparent,
      },
    };
  }, [config]);

  const eventHandlers = useMemo(
    () =>
      new Map([
        [
          "error",
          () => {
            void refreshToken();
          },
        ],
      ]),
    [refreshToken],
  );

  if (isLoading) {
    return (
      <div className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-16)] shadow-[var(--shadow)]">
        <div className="h-6 w-44 animate-pulse rounded bg-[var(--surface-muted)]" />
        <div className="mt-[var(--space-12)] h-[560px] w-full animate-pulse rounded bg-[var(--surface-muted)]" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-[var(--radius-card)] border border-[color-mix(in_srgb,var(--status-critical)_30%,white)] bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] p-[var(--space-16)] shadow-[var(--shadow)]">
        <h2 className="text-base font-semibold text-[var(--status-critical)]">Unable to load analytics report</h2>
        <p className="mt-[var(--space-8)] text-sm text-[var(--status-critical)]">{error}</p>
        <button
          type="button"
          onClick={() => {
            void loadConfig(true);
          }}
          className="mt-[var(--space-12)] rounded-[var(--radius-6)] border border-[var(--status-critical)] px-3 py-1.5 text-sm font-medium text-[var(--status-critical)] transition-colors hover:bg-[color-mix(in_srgb,var(--status-critical)_10%,white)]"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!config || !embedConfig) {
    return (
      <div className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-16)] shadow-[var(--shadow)]">
        <div className="h-6 w-44 animate-pulse rounded bg-[var(--surface-muted)]" />
        <div className="mt-[var(--space-12)] h-[560px] w-full animate-pulse rounded bg-[var(--surface-muted)]" />
      </div>
    );
  }

  return (
    <div className="rounded-[var(--radius-card)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-12)] shadow-[var(--shadow)]">
      <PowerBIEmbed
        embedConfig={embedConfig}
        cssClassName="h-[72vh] w-full"
        eventHandlers={eventHandlers}
        getEmbeddedComponent={(embedded) => {
          reportRef.current = embedded as EmbeddedReportHandle;
        }}
      />
    </div>
  );
}
