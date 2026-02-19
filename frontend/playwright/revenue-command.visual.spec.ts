import { expect, test } from "@playwright/test";

const mockSnapshot = {
  snapshot_id: "snapshot-001",
  organization_id: "org-1",
  generated_at: "2026-02-12T15:00:00Z",
  total_exposure_cents: 125_000_000,
  expected_recovery_30_day_cents: 62_500_000,
  short_term_cash_opportunity_cents: 18_750_000,
  high_risk_claim_count: 7,
  critical_pre_submission_count: 2,
  top_aggressive_payers: [
    {
      payer: "Apex Payer",
      aggression_score: 88,
      aggression_tier: "high",
      aggression_drivers: ["denial velocity", "recoupments"],
    },
    {
      payer: "Boulder Mutual",
      aggression_score: 76,
      aggression_tier: "medium",
      aggression_drivers: ["downcodes", "late payments"],
    },
  ],
  top_revenue_loss_drivers: ["Denied: CO16 on ortho lines", "Underpayments on Apex Payer", "Coding variance on OP visits"],
  worklist_priority_summary: { high: 4, medium: 3, low: 2 },
  top_worklist: [
    {
      id: "task-01",
      claim_id: "claim-01",
      payer: "Apex Payer",
      status: "DENIED",
      aging_days: 105,
      dollars_per_hour_cents: 1_250_000,
      task: "Escalate denial",
      priority: "high",
    },
    {
      id: "task-02",
      claim_id: "claim-02",
      payer: "Boulder Mutual",
      status: "OPEN",
      aging_days: 70,
      dollars_per_hour_cents: 840_000,
      task: "Follow up on open balance",
      priority: "medium",
    },
  ],
  execution_plan_30_day: [
    { title: "Clear denial backlog", expected_impact: "7500000", owner: "Billing QA", priority: "high" },
  ],
  structural_moves_90_day: [
    "Tighten edit controls for recurring denial codes",
    "Bundle payer-specific policies into pre-submission templates",
  ],
  aggression_change_alerts: [{ type: "exposure_increase" }],
  scoring_versions: {
    risk_version: "1.0",
    aggression_version: "2.0",
    pre_submission_version: "1.0",
  },
};

test("revenue command center visual", async ({ page }) => {
  await page.route("http://127.0.0.1:8000/api/v1/me/preferences", async (route) => {
    if (route.request().method() === "PATCH") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          last_active_module: "revenue_cycle",
          sidebar_collapsed: false,
          copilot_enabled: false,
          allowed_modules: [
            "care_delivery",
            "call_center",
            "workforce",
            "revenue_cycle",
            "governance",
            "administration",
          ],
          granted_permissions: ["billing:read", "billing:write"],
        }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        last_active_module: "revenue_cycle",
        sidebar_collapsed: false,
        copilot_enabled: false,
        allowed_modules: [
          "care_delivery",
          "call_center",
          "workforce",
          "revenue_cycle",
          "governance",
          "administration",
        ],
        granted_permissions: ["billing:read", "billing:write"],
      }),
    });
  });

  await page.route("http://127.0.0.1:8000/api/v1/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "user-1",
        email: "visual-test@example.com",
        full_name: "Visual Test User",
        role: "admin",
        organization_id: "org-1",
      }),
    });
  });

  await page.route("http://127.0.0.1:8000/api/v1/revenue/snapshots/latest", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockSnapshot),
    });
  });

  await page.goto("/billing/revenue-command");
  await expect(page.getByRole("heading", { name: "Daily Command Snapshot" })).toBeVisible();
  await expect(page).toHaveScreenshot("revenue-command.png", { fullPage: true });
});
