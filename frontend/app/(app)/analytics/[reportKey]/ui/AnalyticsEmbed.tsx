"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { models, type IEmbedConfiguration } from "powerbi-client";

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

type EmbedFieldName = "reportId" | "embedUrl" | "accessToken";

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

function getMissingEmbedFields(config: EmbedConfigResponse | null): EmbedFieldName[] {
  if (!config) {
    return ["reportId", "embedUrl", "accessToken"];
  }

  const missing: EmbedFieldName[] = [];
  if (!config.reportId?.trim()) {
    missing.push("reportId");
  }
  if (!config.embedUrl?.trim()) {
    missing.push("embedUrl");
  }
  if (!config.accessToken?.trim()) {
    missing.push("accessToken");
  }
  return missing;
}

export default function AnalyticsEmbed({ reportKey }: AnalyticsEmbedProps) {
  const normalizedReportKey = reportKey.trim();
  const reportRef = useRef<EmbeddedReportHandle | null>(null);
  const configRef = useRef<EmbedConfigResponse | null>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inFlightRefreshRef = useRef<Promise<void> | null>(null);
  const isMountedRef = useRef(true);

  const [config, setConfig] = useState<EmbedConfigResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const missingEmbedFields = useMemo(() => getMissingEmbedFields(config), [config]);
  const hasCompleteEmbedConfig = missingEmbedFields.length === 0;

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
      if (!normalizedReportKey) {
        setError("Missing report key. Return to Analytics and choose a report.");
        setIsLoading(false);
        return;
      }
      if (showLoader) {
        setIsLoading(true);
      }
      setError(null);
      try {
        const nextConfig = await fetchEmbedConfig(normalizedReportKey);
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
    [normalizedReportKey],
  );

  const refreshToken = useCallback(async () => {
    if (!normalizedReportKey) {
      return;
    }
    if (inFlightRefreshRef.current) {
      return inFlightRefreshRef.current;
    }

    const refreshPromise = (async () => {
      try {
        const nextConfig = await fetchEmbedConfig(normalizedReportKey);
        if (!isMountedRef.current) {
          return;
        }

        const missingFields = getMissingEmbedFields(nextConfig);
        if (missingFields.length > 0) {
          throw new Error(`Embed config missing required field(s): ${missingFields.join(", ")}`);
        }

        const currentConfig = configRef.current;
        const sameReport = currentConfig
          && currentConfig.reportId
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
  }, [normalizedReportKey]);

  const accessTokenProvider = useCallback(async () => {
    try {
      if (!normalizedReportKey) {
        throw new Error("Missing report key.");
      }
      const nextConfig = await fetchEmbedConfig(normalizedReportKey);
      const missingFields = getMissingEmbedFields(nextConfig);
      if (missingFields.length > 0) {
        throw new Error(`Embed config missing required field(s): ${missingFields.join(", ")}`);
      }

      if (!isMountedRef.current) {
        return nextConfig.accessToken;
      }

      const currentConfig = configRef.current;
      if (
        currentConfig
        && currentConfig.reportId
        && currentConfig.reportId === nextConfig.reportId
        && currentConfig.embedUrl === nextConfig.embedUrl
      ) {
        setConfig({
          ...currentConfig,
          accessToken: nextConfig.accessToken,
          tokenExpiry: nextConfig.tokenExpiry,
          expiresOn: nextConfig.expiresOn,
        });
      } else {
        setConfig(nextConfig);
      }
      return nextConfig.accessToken;
    } catch (providerError) {
      console.error("Power BI accessTokenProvider failed", providerError);
      throw providerError;
    }
  }, [normalizedReportKey]);

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
    if (!config || !hasCompleteEmbedConfig) {
      return undefined;
    }

    const nextEmbedConfig: IEmbedConfiguration = {
      type: "report",
      id: config.reportId!.trim(),
      embedUrl: config.embedUrl.trim(),
      accessToken: config.accessToken.trim(),
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

    (
      nextEmbedConfig as IEmbedConfiguration & {
        eventHooks?: {
          accessTokenProvider?: () => Promise<string>;
        };
      }
    ).eventHooks = {
      accessTokenProvider,
    };

    return nextEmbedConfig;
  }, [accessTokenProvider, config, hasCompleteEmbedConfig]);

  const eventHandlers = useMemo(
    () => {
      const handlers = new Map<string, (event?: unknown) => void>();
      handlers.set("error", (event) => {
        try {
          console.error("Power BI embed emitted an error event", event);
          void refreshToken();
        } catch (handlerError) {
          console.error("Power BI error handler failed", handlerError);
        }
      });
      handlers.set("loaded", () => {
        try {
          setError(null);
        } catch (handlerError) {
          console.error("Power BI loaded handler failed", handlerError);
        }
      });
      return handlers;
    },
    [refreshToken],
  );

  if (!normalizedReportKey) {
    return (
      <div className="rounded-[var(--radius-card)] border border-[color-mix(in_srgb,var(--status-critical)_30%,white)] bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] p-[var(--space-16)] shadow-[var(--shadow)]">
        <h2 className="text-base font-semibold text-[var(--status-critical)]">Analytics failed to load</h2>
        <p className="mt-[var(--space-8)] text-sm text-[var(--status-critical)]">
          Missing report key in route. Return to Analytics and select a report.
        </p>
      </div>
    );
  }

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

  if (!config || !hasCompleteEmbedConfig || !embedConfig) {
    return (
      <div className="rounded-[var(--radius-card)] border border-[color-mix(in_srgb,var(--status-critical)_30%,white)] bg-[color-mix(in_srgb,var(--status-critical)_8%,white)] p-[var(--space-16)] shadow-[var(--shadow)]">
        <h2 className="text-base font-semibold text-[var(--status-critical)]">Analytics failed to load</h2>
        <p className="mt-[var(--space-8)] text-sm text-[var(--status-critical)]">
          Embed configuration is incomplete. Missing field(s): {missingEmbedFields.join(", ")}.
        </p>
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
          try {
            reportRef.current = embedded as EmbeddedReportHandle;
          } catch (captureError) {
            console.error("Failed to capture embedded Power BI report instance", captureError);
          }
        }}
      />
    </div>
  );
}
