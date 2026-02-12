import { expect, test } from "@playwright/test";

const mockSnapshot = {
  call_log: [
    {
      call_id: "call-001",
      session_id: "session-001",
      state: "disconnected",
      missed: false,
      call_date: "2026-02-12",
      from_number: "+15550001111",
      to_number: "+15550002222",
      direction: "Inbound",
      started_at: "2026-02-12T13:00:00Z",
      answered_at: "2026-02-12T13:00:05Z",
      ended_at: "2026-02-12T13:05:12Z",
      last_event_at: "2026-02-12T13:05:12Z",
      overlay_status: "RESOLVED",
      notes: "Resolved after verification.",
    },
    {
      call_id: "call-002",
      session_id: "session-002",
      state: "disconnected",
      missed: true,
      call_date: "2026-02-12",
      from_number: "+15550003333",
      to_number: "+15550004444",
      direction: "Inbound",
      started_at: "2026-02-12T14:10:00Z",
      answered_at: null,
      ended_at: "2026-02-12T14:10:24Z",
      last_event_at: "2026-02-12T14:10:24Z",
      overlay_status: "MISSED",
      notes: "Left voicemail.",
    },
  ],
  subscription_status: "ACTIVE",
};

test("call center spreadsheet visual", async ({ page }) => {
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

  await page.route("http://127.0.0.1:8000/api/v1/call-center/snapshot*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(mockSnapshot),
    });
  });

  await page.route("http://127.0.0.1:8000/api/v1/call-center/stream*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: ": ping\n\n",
    });
  });

  await page.goto("/call-center");
  await expect(page.getByTestId("call-center-title")).toHaveText("Call Center");
  await expect(page).toHaveScreenshot("call-center-table.png", { fullPage: true });
});
