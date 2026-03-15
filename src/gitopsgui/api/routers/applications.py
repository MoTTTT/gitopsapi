from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List

from ...models.application import ApplicationSpec, ApplicationResponse, DisableApplicationRequest
from ...models.status import UndeployStatus
from ...services.app_service import AppService
from ...services.k8s_service import K8sService
from ..auth import require_role

router = APIRouter(tags=["applications"])


@router.post("/applications", response_model=ApplicationResponse, status_code=202)
async def add_application(
    spec: ApplicationSpec,
    _=require_role("cluster_operator"),
):
    svc = AppService()
    return await svc.create_application(spec)


@router.get("/applications", response_model=List[ApplicationResponse])
async def list_applications(_=require_role("cluster_operator", "build_manager", "senior_developer")):
    svc = AppService()
    return await svc.list_applications()


@router.get("/applications/{name}", response_model=ApplicationResponse)
async def get_application(
    name: str,
    _=require_role("cluster_operator", "build_manager", "senior_developer"),
):
    svc = AppService()
    result = await svc.get_application(name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Application {name!r} not found")
    return result


@router.post("/applications/{name}/disable", response_model=ApplicationResponse, status_code=202)
async def disable_application(
    name: str,
    body: DisableApplicationRequest,
    _=require_role("cluster_operator"),
):
    """Comment out the application's kustomization entry on the specified cluster.

    The app definition in gitops/gitops-apps/ is preserved; Flux stops reconciling
    the workload once the PR is merged.
    """
    svc = AppService()
    return await svc.disable_application(name, body.cluster)


@router.post("/applications/{name}/enable", response_model=ApplicationResponse, status_code=202)
async def enable_application(
    name: str,
    body: DisableApplicationRequest,
    _=require_role("cluster_operator"),
):
    """Uncomment the application's kustomization entry on the specified cluster.

    Reverses a previous disable. Flux resumes reconciling the workload once the PR is merged.
    """
    svc = AppService()
    return await svc.enable_application(name, body.cluster)


@router.get("/applications/{name}/undeploy-status", response_model=UndeployStatus)
async def get_undeploy_status(
    name: str,
    cluster: str = Query(..., description="Target cluster name"),
    _=require_role("cluster_operator", "build_manager", "senior_developer"),
):
    """GITGUI-027 — Check whether the application namespace has been removed from the cluster.

    Returns namespace_phase: gone (undeploy confirmed) | active | terminating | unknown.
    When terminating, surfaces namespace finalizers and any in-namespace resources
    still carrying finalizers that may be blocking deletion.
    """
    svc = K8sService()
    return await svc.get_undeploy_status(name, cluster)
