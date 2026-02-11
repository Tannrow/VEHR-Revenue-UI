"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

type OrganizationSettings = {
  organization_id: string;
  name: string;
};

type UserRow = {
  id: string;
  email: string;
  full_name?: string | null;
  role: string;
  is_active: boolean;
};

type RoleRow = {
  key: string;
  name: string;
  is_system: boolean;
  permissions: string[];
};

type IntegrationStatus = {
  organization_id: string;
  items: Array<{ provider: string; connected_accounts: number }>;
};

type RingCentralStatus = {
  connected: boolean;
  scope?: string | null;
  account_id?: string | null;
  extension_id?: string | null;
  expires_at?: string | null;
};

type RingCentralConnect = {
  auth_url: string;
};

function sortPermissions(values: string[]) {
  return [...values].sort((a, b) => a.localeCompare(b));
}

function toMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError || error instanceof Error) {
    return error.message || fallback;
  }
  return fallback;
}

export default function AdminCenterPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [settings, setSettings] = useState<OrganizationSettings | null>(null);
  const [settingsName, setSettingsName] = useState("");
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState<string | null>(null);

  const [users, setUsers] = useState<UserRow[]>([]);
  const [roles, setRoles] = useState<RoleRow[]>([]);
  const [permissionCatalog, setPermissionCatalog] = useState<string[]>([]);
  const [integrationStatus, setIntegrationStatus] = useState<IntegrationStatus | null>(null);
  const [ringCentralStatus, setRingCentralStatus] = useState<RingCentralStatus | null>(null);
  const [ringCentralMessage, setRingCentralMessage] = useState<string | null>(null);
  const [isConnectingRingCentral, setIsConnectingRingCentral] = useState(false);
  const [isDisconnectingRingCentral, setIsDisconnectingRingCentral] = useState(false);

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("");
  const [inviteMessage, setInviteMessage] = useState<string | null>(null);
  const [isInviting, setIsInviting] = useState(false);

  const [pendingRoleByUser, setPendingRoleByUser] = useState<Record<string, string>>({});
  const [roleSaveMessage, setRoleSaveMessage] = useState<string | null>(null);
  const [savingRoleForUser, setSavingRoleForUser] = useState<string | null>(null);

  const [selectedRoleKey, setSelectedRoleKey] = useState("");
  const [selectedRolePermissions, setSelectedRolePermissions] = useState<string[]>([]);
  const [permissionsMessage, setPermissionsMessage] = useState<string | null>(null);
  const [isSavingPermissions, setIsSavingPermissions] = useState(false);

  const selectedRole = useMemo(
    () => roles.find((role) => role.key === selectedRoleKey) ?? null,
    [roles, selectedRoleKey],
  );

  async function loadAdminData() {
    setIsLoading(true);
    setLoadError(null);
    try {
      const [settingsRes, usersRes, rolesRes, permissionsRes, integrationsRes, ringCentralStatusRes] = await Promise.all([
        apiFetch<OrganizationSettings>("/api/v1/admin/organization/settings", { cache: "no-store" }),
        apiFetch<UserRow[]>("/api/v1/users", { cache: "no-store" }),
        apiFetch<RoleRow[]>("/api/v1/admin/roles", { cache: "no-store" }),
        apiFetch<string[]>("/api/v1/admin/permissions/catalog", { cache: "no-store" }),
        apiFetch<IntegrationStatus>("/api/v1/admin/integrations/status", { cache: "no-store" }),
        apiFetch<RingCentralStatus>("/api/v1/integrations/ringcentral/status", { cache: "no-store" }),
      ]);

      setSettings(settingsRes);
      setSettingsName(settingsRes.name);
      setUsers(usersRes);
      setRoles(rolesRes);
      setPermissionCatalog(sortPermissions(permissionsRes));
      setIntegrationStatus(integrationsRes);
      setRingCentralStatus(ringCentralStatusRes);

      if (rolesRes.length > 0) {
        const firstRoleKey = rolesRes[0].key;
        setSelectedRoleKey(firstRoleKey);
        setSelectedRolePermissions(sortPermissions(rolesRes[0].permissions));
        setInviteRole(firstRoleKey);
      }
    } catch (error) {
      setLoadError(toMessage(error, "Unable to load admin center data."));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadAdminData();
  }, []);

  useEffect(() => {
    if (!selectedRole) {
      setSelectedRolePermissions([]);
      return;
    }
    setSelectedRolePermissions(sortPermissions(selectedRole.permissions));
  }, [selectedRole]);

  async function handleSaveSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSettingsMessage(null);
    setSavingSettings(true);
    try {
      const response = await apiFetch<OrganizationSettings>("/api/v1/admin/organization/settings", {
        method: "PATCH",
        body: JSON.stringify({ name: settingsName }),
      });
      setSettings(response);
      setSettingsName(response.name);
      setSettingsMessage("Organization settings updated.");
    } catch (error) {
      setSettingsMessage(toMessage(error, "Unable to update organization settings."));
    } finally {
      setSavingSettings(false);
    }
  }

  async function handleInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setInviteMessage(null);
    setIsInviting(true);
    try {
      await apiFetch("/api/v1/admin/invites", {
        method: "POST",
        body: JSON.stringify({
          email: inviteEmail,
          allowed_roles: inviteRole ? [inviteRole] : undefined,
        }),
      });
      setInviteEmail("");
      setInviteMessage("Invite sent.");
    } catch (error) {
      setInviteMessage(toMessage(error, "Unable to send invite."));
    } finally {
      setIsInviting(false);
    }
  }

  async function handleSaveUserRole(userId: string) {
    const nextRole = pendingRoleByUser[userId];
    if (!nextRole) return;

    setRoleSaveMessage(null);
    setSavingRoleForUser(userId);
    try {
      const updated = await apiFetch<UserRow>(`/api/v1/admin/users/${userId}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role: nextRole }),
      });
      setUsers((current) => current.map((row) => (row.id === userId ? updated : row)));
      setPendingRoleByUser((current) => ({ ...current, [userId]: "" }));
      setRoleSaveMessage(`Updated role for ${updated.email}.`);
    } catch (error) {
      setRoleSaveMessage(toMessage(error, "Unable to update role."));
    } finally {
      setSavingRoleForUser(null);
    }
  }

  function togglePermission(permission: string) {
    setSelectedRolePermissions((current) =>
      current.includes(permission)
        ? current.filter((item) => item !== permission)
        : sortPermissions([...current, permission]),
    );
  }

  async function handleSaveRolePermissions() {
    if (!selectedRoleKey) return;
    setPermissionsMessage(null);
    setIsSavingPermissions(true);
    try {
      const updated = await apiFetch<RoleRow>(`/api/v1/admin/roles/${selectedRoleKey}/permissions`, {
        method: "PUT",
        body: JSON.stringify({ permissions: selectedRolePermissions }),
      });
      setRoles((current) =>
        current.map((role) => (role.key === updated.key ? updated : role)),
      );
      setSelectedRolePermissions(sortPermissions(updated.permissions));
      setPermissionsMessage(`Permissions updated for ${updated.name}.`);
    } catch (error) {
      setPermissionsMessage(toMessage(error, "Unable to update role permissions."));
    } finally {
      setIsSavingPermissions(false);
    }
  }

  async function handleConnectRingCentral() {
    setRingCentralMessage(null);
    setIsConnectingRingCentral(true);
    try {
      const response = await apiFetch<RingCentralConnect>("/api/v1/integrations/ringcentral/connect", {
        method: "POST",
      });
      window.location.assign(response.auth_url);
    } catch (error) {
      setRingCentralMessage(toMessage(error, "Unable to start RingCentral connection."));
      setIsConnectingRingCentral(false);
    }
  }

  async function handleDisconnectRingCentral() {
    setRingCentralMessage(null);
    setIsDisconnectingRingCentral(true);
    try {
      await apiFetch("/api/v1/integrations/ringcentral/disconnect", { method: "POST" });
      setRingCentralMessage("RingCentral disconnected.");
      await loadAdminData();
    } catch (error) {
      setRingCentralMessage(toMessage(error, "Unable to disconnect RingCentral."));
    } finally {
      setIsDisconnectingRingCentral(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="space-y-3">
        <p className="text-sm font-semibold text-slate-500">Admin</p>
        <h1 className="text-[2rem] font-semibold tracking-tight text-slate-900">Admin Center</h1>
        <p className="max-w-3xl text-base leading-7 text-slate-600">
          Organization settings, users, roles, permissions, and integration status.
        </p>
      </div>

      {isLoading ? <p className="text-sm text-slate-600">Loading admin center...</p> : null}
      {loadError ? <p className="text-sm text-rose-700">{loadError}</p> : null}

      {!isLoading && !loadError ? (
        <>
          <div className="grid gap-5 xl:grid-cols-[1.1fr_1fr]">
            <Card className="bg-white shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-xl text-slate-900">Organization settings</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 pt-0">
                <form className="space-y-3" onSubmit={handleSaveSettings}>
                  <div className="space-y-2">
                    <label className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500" htmlFor="org_name">
                      Organization name
                    </label>
                    <Input
                      id="org_name"
                      value={settingsName}
                      onChange={(event) => setSettingsName(event.target.value)}
                      placeholder="Organization name"
                    />
                  </div>
                  <Button type="submit" className="h-9 rounded-lg px-4" disabled={savingSettings}>
                    {savingSettings ? "Saving..." : "Save settings"}
                  </Button>
                </form>
                {settings ? (
                  <p className="text-xs text-slate-500">Organization ID: {settings.organization_id}</p>
                ) : null}
                {settingsMessage ? <p className="text-sm text-slate-700">{settingsMessage}</p> : null}
              </CardContent>
            </Card>

            <Card className="bg-white shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-xl text-slate-900">Integrations status</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 pt-0">
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-slate-900">RingCentral</p>
                      <p className="text-xs text-slate-500">
                        {ringCentralStatus?.connected ? "Connected" : "Not connected"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        type="button"
                        className="h-8 rounded-lg px-3"
                        onClick={() => void handleConnectRingCentral()}
                        disabled={isConnectingRingCentral}
                      >
                        {isConnectingRingCentral ? "Redirecting..." : "Connect RingCentral"}
                      </Button>
                      {ringCentralStatus?.connected ? (
                        <Button
                          type="button"
                          variant="outline"
                          className="h-8 rounded-lg px-3"
                          onClick={() => void handleDisconnectRingCentral()}
                          disabled={isDisconnectingRingCentral}
                        >
                          {isDisconnectingRingCentral ? "Disconnecting..." : "Disconnect"}
                        </Button>
                      ) : null}
                    </div>
                  </div>
                  {ringCentralStatus?.connected ? (
                    <p className="mt-2 text-xs text-slate-500">
                      Account: {ringCentralStatus.account_id || "n/a"} · Extension:{" "}
                      {ringCentralStatus.extension_id || "n/a"}
                    </p>
                  ) : null}
                </div>
                {integrationStatus?.items.length ? (
                  integrationStatus.items.map((item) => (
                    <div key={item.provider} className="rounded-lg bg-slate-50 px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-semibold text-slate-900">{item.provider}</span>
                        <span className="text-xs text-slate-600">{item.connected_accounts} connected</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-sm text-slate-500">No active integrations connected.</p>
                )}
                {ringCentralMessage ? <p className="text-sm text-slate-700">{ringCentralMessage}</p> : null}
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-5 xl:grid-cols-[1.1fr_1fr]">
            <Card className="bg-white shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-xl text-slate-900">Users & roles</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 pt-0">
                <form className="grid gap-2 md:grid-cols-[1.2fr_1fr_auto]" onSubmit={handleInvite}>
                  <Input
                    value={inviteEmail}
                    onChange={(event) => setInviteEmail(event.target.value)}
                    placeholder="Invite user email"
                    type="email"
                    required
                  />
                  <select
                    className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm"
                    value={inviteRole}
                    onChange={(event) => setInviteRole(event.target.value)}
                  >
                    {roles.map((role) => (
                      <option key={role.key} value={role.key}>
                        {role.name}
                      </option>
                    ))}
                  </select>
                  <Button type="submit" className="h-9 rounded-lg px-4" disabled={isInviting}>
                    {isInviting ? "Inviting..." : "Invite user"}
                  </Button>
                </form>
                {inviteMessage ? <p className="text-sm text-slate-700">{inviteMessage}</p> : null}

                <div className="space-y-2">
                  {users.map((user) => (
                    <div key={user.id} className="grid gap-2 rounded-lg bg-slate-50 px-3 py-3 md:grid-cols-[1.2fr_1fr_auto]">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-900">{user.full_name || user.email}</p>
                        <p className="truncate text-xs text-slate-500">{user.email}</p>
                      </div>
                      <select
                        className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm"
                        value={pendingRoleByUser[user.id] || user.role}
                        onChange={(event) =>
                          setPendingRoleByUser((current) => ({
                            ...current,
                            [user.id]: event.target.value,
                          }))
                        }
                      >
                        {roles.map((role) => (
                          <option key={role.key} value={role.key}>
                            {role.name}
                          </option>
                        ))}
                      </select>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-9 rounded-lg px-4"
                        onClick={() => void handleSaveUserRole(user.id)}
                        disabled={savingRoleForUser === user.id}
                      >
                        {savingRoleForUser === user.id ? "Saving..." : "Save role"}
                      </Button>
                    </div>
                  ))}
                </div>
                {roleSaveMessage ? <p className="text-sm text-slate-700">{roleSaveMessage}</p> : null}
              </CardContent>
            </Card>

            <Card className="bg-white shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-xl text-slate-900">Role permissions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 pt-0">
                <select
                  className="h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm"
                  value={selectedRoleKey}
                  onChange={(event) => setSelectedRoleKey(event.target.value)}
                >
                  {roles.map((role) => (
                    <option key={role.key} value={role.key}>
                      {role.name}
                    </option>
                  ))}
                </select>

                <div className="max-h-72 space-y-1 overflow-y-auto rounded-lg bg-slate-50 p-2">
                  {permissionCatalog.map((permission) => (
                    <label key={permission} className="flex items-center gap-2 rounded px-2 py-1.5 text-sm text-slate-700">
                      <input
                        type="checkbox"
                        checked={selectedRolePermissions.includes(permission)}
                        onChange={() => togglePermission(permission)}
                        className="h-4 w-4 rounded border-slate-300"
                      />
                      <span>{permission}</span>
                    </label>
                  ))}
                </div>

                <Button
                  type="button"
                  variant="outline"
                  className="h-9 rounded-lg px-4"
                  onClick={() => void handleSaveRolePermissions()}
                  disabled={isSavingPermissions || !selectedRoleKey}
                >
                  {isSavingPermissions ? "Saving..." : "Save permissions"}
                </Button>
                {permissionsMessage ? <p className="text-sm text-slate-700">{permissionsMessage}</p> : null}
              </CardContent>
            </Card>
          </div>
        </>
      ) : null}
    </div>
  );
}
