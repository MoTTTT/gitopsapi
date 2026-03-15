from fastapi import APIRouter, HTTPException
from typing import List, Optional

from ...models.application_config import (
    ApplicationClusterConfig,
    ApplicationClusterConfigResponse,
    PatchApplicationClusterConfig,
)
from ...services.app_config_service import AppConfigService
from ..auth import require_role

router = APIRouter(tags=["application-configs"])


@router.post("/application-configs", response_model=ApplicationClusterConfigResponse, status_code=202)
async def assign_application_to_cluster(
    spec: ApplicationClusterConfig,
    _=require_role("cluster_operator", "security_admin"),
):
    svc = AppConfigService()
    return await svc.create(spec)


@router.get("/application-configs", response_model=List[ApplicationClusterConfigResponse])
async def list_application_configs(
    application: Optional[str] = None,
    cluster: Optional[str] = None,
    _=require_role("cluster_operator", "build_manager", "senior_developer", "security_admin"),
):
    if not application and not cluster:
        raise HTTPException(
            status_code=400,
            detail="Provide ?application=<name> or ?cluster=<name>",
        )
    svc = AppConfigService()
    if cluster:
        return await svc.list_by_cluster(cluster)
    return await svc.list_by_application(application)


@router.patch("/application-configs/{config_id}", response_model=ApplicationClusterConfigResponse, status_code=202)
async def patch_application_config(
    config_id: str,
    body: PatchApplicationClusterConfig,
    _=require_role("cluster_operator", "build_manager", "security_admin"),
):
    svc = AppConfigService()
    return await svc.patch(config_id, body)


@router.delete("/application-configs/{config_id}", response_model=ApplicationClusterConfigResponse, status_code=202)
async def remove_application_from_cluster(
    config_id: str,
    _=require_role("cluster_operator", "security_admin"),
):
    svc = AppConfigService()
    return await svc.delete(config_id)
