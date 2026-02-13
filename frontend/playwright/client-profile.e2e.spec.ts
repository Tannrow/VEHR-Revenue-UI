import { expect, test } from "@playwright/test";

type TaskRecord = {
  id: string;
  organization_id: string;
  title: string;
  description?: string | null;
  status: "open" | "in_progress" | "done" | "canceled";
  priority: "low" | "normal" | "high" | "urgent";
  due_at?: string | null;
  completed_at?: string | null;
  created_by_user_id: string;
  assigned_to_user_id?: string | null;
  assigned_to_user_name?: string | null;
  assigned_team_id?: string | null;
  assigned_team_label?: string | null;
  related_type?: string | null;
  related_id?: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
};

const patientId = "patient-001";
const baseApi = "http://127.0.0.1:8000";

function nowIso(): string {
  return new Date().toISOString();
}

test("client profile happy path: switch tabs, create task, verify row", async ({ page }) => {
  const tasks: TaskRecord[] = [];

  await page.route(`${baseApi}/api/v1/auth/me`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "user-1",
        email: "clinician@example.com",
        full_name: "Clinician User",
        role: "admin",
        organization_id: "org-1",
      }),
    });
  });

  await page.route(`${baseApi}/api/v1/me/preferences`, async (route) => {
    if (route.request().method() === "PATCH") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          last_active_module: "care_delivery",
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
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        last_active_module: "care_delivery",
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

  await page.route(`${baseApi}/api/v1/patients/${patientId}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: patientId,
        first_name: "Taylor",
        last_name: "Rapp",
        dob: "1985-02-12",
        phone: "555-1234",
        email: "patient@example.com",
      }),
    });
  });

  await page.route(`${baseApi}/api/v1/services?include_inactive=true`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "svc-1",
          name: "Outpatient Therapy",
          code: "OPTH",
          category: "mh",
          is_active: true,
        },
      ]),
    });
  });

  await page.route(`${baseApi}/api/v1/patients/${patientId}/enrollments`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "enr-1",
          status: "active",
          start_date: "2026-02-01",
          end_date: null,
          reporting_enabled: true,
          service: {
            id: "svc-1",
            name: "Outpatient Therapy",
            code: "OPTH",
            category: "mh",
          },
        },
      ]),
    });
  });

  await page.route(`${baseApi}/api/v1/patients/${patientId}/documents`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "doc-1",
          patient_id: patientId,
          service_id: "svc-1",
          enrollment_id: "enr-1",
          template_id: "tpl-1",
          status: "required",
          completed_at: null,
          expires_at: null,
          sent_at: null,
          created_at: nowIso(),
          updated_at: nowIso(),
          service: {
            id: "svc-1",
            name: "Outpatient Therapy",
            code: "OPTH",
            category: "mh",
          },
          template: {
            id: "tpl-1",
            name: "Consent Form",
            version: 1,
            status: "active",
          },
        },
      ]),
    });
  });

  await page.route(`${baseApi}/api/v1/patients/${patientId}/encounters`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route(`${baseApi}/api/v1/patients/${patientId}/episodes`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "ep-1",
          patient_id: patientId,
          admit_date: "2026-02-01",
          discharge_date: null,
          primary_service_category: "mh",
          court_involved: false,
          status: "active",
          referral_source: null,
          reason_for_admission: null,
          discharge_disposition: null,
        },
      ]),
    });
  });

  await page.route(`${baseApi}/api/v1/patients/${patientId}/care-team`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: "ct-1",
          patient_id: patientId,
          episode_id: "ep-1",
          role: "primary_clinician",
          user_id: "user-1",
          assigned_at: nowIso(),
          user_email: "clinician@example.com",
          user_full_name: "Clinician User",
        },
      ]),
    });
  });

  await page.route(`${baseApi}/api/v1/patients/${patientId}/requirements`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route(`${baseApi}/api/v1/patients/${patientId}/treatment-stage`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "ts-1",
        episode_id: "ep-1",
        stage: "active_treatment",
        updated_at: nowIso(),
      }),
    });
  });

  await page.route(`${baseApi}/api/v1/patients/${patientId}/treatment-stage/events`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route(new RegExp(`${baseApi}/api/v1/patients/${patientId}/notes(\\?.*)?$`), async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.route(`${baseApi}/api/v1/staff/teams`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          name: "clinical",
          members: [
            {
              id: "user-1",
              full_name: "Clinician User",
              email: "clinician@example.com",
            },
          ],
        },
      ]),
    });
  });

  await page.route(new RegExp(`${baseApi}/api/v1/tasks(\\?.*)?$`), async (route) => {
    const method = route.request().method();
    if (method === "POST") {
      const payload = route.request().postDataJSON() as {
        title: string;
        description?: string | null;
        priority?: "low" | "normal" | "high" | "urgent";
        due_at?: string | null;
        related_type?: string | null;
        related_id?: string | null;
      };
      const created: TaskRecord = {
        id: `task-${tasks.length + 1}`,
        organization_id: "org-1",
        title: payload.title,
        description: payload.description ?? null,
        status: "open",
        priority: payload.priority ?? "normal",
        due_at: payload.due_at ?? null,
        completed_at: null,
        created_by_user_id: "user-1",
        assigned_to_user_id: null,
        assigned_to_user_name: null,
        assigned_team_id: null,
        assigned_team_label: null,
        related_type: payload.related_type ?? null,
        related_id: payload.related_id ?? null,
        tags: ["client-profile"],
        created_at: nowIso(),
        updated_at: nowIso(),
      };
      tasks.unshift(created);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(created),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: tasks,
        total: tasks.length,
        limit: 200,
        offset: 0,
        counts: {},
      }),
    });
  });

  await page.goto(`/patients/${patientId}`);
  await expect(page.getByTestId("client-profile-page")).toBeVisible();

  await page.getByTestId("client-tab-notes").click();
  await expect(page.getByTestId("client-note-submit")).toBeVisible();

  await page.getByTestId("client-tab-documents").click();
  await expect(page.getByTestId("client-documents-list")).toBeVisible();

  await page.getByTestId("client-action-create-task").click();
  await expect(page).toHaveURL(/\/tasks/);
  await expect(page.getByTestId("tasks-list")).toBeVisible();

  await page.getByTestId("tasks-open-create").click();
  await page.getByTestId("tasks-create-title").fill("Call guardian for follow-up");
  await page.getByTestId("tasks-create-submit").click();

  await expect(page.getByText("Call guardian for follow-up")).toBeVisible();
});
