from fastapi import APIRouter

from app.api.v1 import tanner_ai
from app.api.v1.endpoints import (
    ai_copilot,
    admin_center,
    audit,
    auth,
    bi,
    clinical_audit,
    documents,
    encounters,
    exports,
    forms,
    health,
    integrations,
    integrations_microsoft,
    me_preferences,
    ringcentral_live,
    organization_home,
    organizations,
    paperwork,
    patient_chart,
    patients,
    portal,
    reception,
    sharepoint,
    scribe,
    staff,
    services,
    tasks,
    uploads,
    webhooks,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(me_preferences.router)
api_router.include_router(ai_copilot.router)
api_router.include_router(admin_center.router)
api_router.include_router(organizations.router)
api_router.include_router(organization_home.router)
api_router.include_router(patients.router)
api_router.include_router(patient_chart.router)
api_router.include_router(encounters.router)
api_router.include_router(documents.router)
api_router.include_router(forms.router)
api_router.include_router(paperwork.router)
api_router.include_router(exports.router)
api_router.include_router(portal.router)
api_router.include_router(audit.router)
api_router.include_router(bi.router)
api_router.include_router(clinical_audit.router)
api_router.include_router(webhooks.router)
api_router.include_router(integrations.router)
api_router.include_router(integrations_microsoft.router)
api_router.include_router(ringcentral_live.router)
api_router.include_router(services.router)
api_router.include_router(sharepoint.router)
api_router.include_router(staff.router)
api_router.include_router(tasks.router)
api_router.include_router(reception.router)
api_router.include_router(health.router)
api_router.include_router(uploads.router)
api_router.include_router(scribe.router)
api_router.include_router(tanner_ai.router)
