import { expect, test } from "@playwright/test";

const baseApi = "http://127.0.0.1:8000";

test("ERA intake page renders uploads and worklist", async ({ page }) => {
  await page.route(`${baseApi}/api/v1/auth/me`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "user-1",
        email: "user@example.com",
        full_name: "User Example",
        role: "admin",
        organization_id: "org-1",
      }),
    });
  });

  await page.route(`${baseApi}/api/v1/me/preferences`, async (route) => {
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
        granted_permissions: [],
      }),
    });
  });

  await page.route(`${baseApi}/api/v1/revenue/era-pdfs`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "era-1",
          file_name: "Sample ERA.pdf",
          status: "NORMALIZED",
          payer_name_raw: "Acme Health",
          received_date: "2026-02-18",
          created_at: "2026-02-18T12:00:00Z",
        },
      ]),
    });
  });

  await page.route(`${baseApi}/api/v1/revenue/era-worklist`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "work-1",
          type: "DENIAL",
          payer_name: "Acme Health",
          claim_ref: "CLM1001",
          dollars_cents: 12345,
          status: "OPEN",
          created_at: "2026-02-18T12:00:00Z",
        },
      ]),
    });
  });

  await page.goto("/revenue/era-intake");
  await expect(page.getByRole("heading", { name: "ERA Intake" })).toBeVisible();
  await expect(page.getByText("Sample ERA.pdf")).toBeVisible();
  await expect(page.getByText("CLM1001")).toBeVisible();
});
