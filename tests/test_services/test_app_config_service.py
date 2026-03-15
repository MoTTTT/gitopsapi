"""
Unit tests for AppConfigService — mocks GitService and GitHubService.
"""

import pytest
import textwrap
from unittest.mock import AsyncMock

from gitopsgui.models.application_config import ApplicationClusterConfig, PatchApplicationClusterConfig
from gitopsgui.services.app_config_service import (
    AppConfigService,
    _config_id,
    _cluster_apps_path,
    _values_override_path,
    _render_kustomization_entry,
    _find_kustomization_block,
    _remove_kustomization_block,
    _comment_kustomization_block,
)


_SPEC = ApplicationClusterConfig(
    app_id="keycloak",
    cluster_id="security",
    chart_version_override=None,
    values_override="replicaCount: 1\n",
    enabled=True,
    pipeline_stage=None,
    gitops_source_ref=None,
)

_APPS_YAML = textwrap.dedent("""\
    ---
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: existing-app
      namespace: flux-system
    spec:
      interval: 1h
      sourceRef:
        kind: GitRepository
        name: security-apps
      path: ./gitops/gitops-apps/existing-app
      prune: true
    ---
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: keycloak
      namespace: flux-system
    spec:
      interval: 1h
      sourceRef:
        kind: GitRepository
        name: security-apps
      path: ./gitops/gitops-apps/keycloak
      prune: true
""")


def _svc() -> AppConfigService:
    svc = AppConfigService()
    svc._git = AsyncMock()
    svc._gh = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# path helpers
# ---------------------------------------------------------------------------

def test_config_id():
    assert _config_id("keycloak", "security") == "keycloak-security"


def test_cluster_apps_path():
    assert _cluster_apps_path("security") == "clusters/security/security-apps.yaml"


def test_values_override_path():
    assert _values_override_path("keycloak", "security") == "gitops/gitops-apps/keycloak/keycloak-values-security.yaml"


# ---------------------------------------------------------------------------
# render helpers
# ---------------------------------------------------------------------------

def test_render_kustomization_entry_default_source_ref():
    rendered = _render_kustomization_entry(_SPEC)
    assert "name: security-apps" in rendered
    assert "name: keycloak" in rendered
    assert "path: ./gitops/gitops-apps/keycloak" in rendered


def test_render_kustomization_entry_external_source_ref():
    spec = _SPEC.model_copy(update={"gitops_source_ref": "bitnami-charts"})
    rendered = _render_kustomization_entry(spec)
    assert "name: bitnami-charts" in rendered


# ---------------------------------------------------------------------------
# block manipulation
# ---------------------------------------------------------------------------

def test_find_kustomization_block_found():
    block = _find_kustomization_block(_APPS_YAML, "keycloak")
    assert block is not None
    assert "keycloak" in block


def test_find_kustomization_block_not_found():
    block = _find_kustomization_block(_APPS_YAML, "missing-app")
    assert block is None


def test_remove_kustomization_block_found():
    updated, found = _remove_kustomization_block(_APPS_YAML, "keycloak")
    assert found
    assert "keycloak" not in updated
    assert "existing-app" in updated


def test_remove_kustomization_block_not_found():
    updated, found = _remove_kustomization_block(_APPS_YAML, "nonexistent")
    assert not found
    assert "existing-app" in updated


def test_comment_kustomization_block():
    updated, found = _comment_kustomization_block(_APPS_YAML, "keycloak")
    assert found
    assert "existing-app" in updated
    # The keycloak block lines should now be commented
    for line in updated.splitlines():
        if "keycloak" in line and "existing" not in line and "---" not in line:
            assert line.lstrip().startswith("#"), f"Expected commented line: {line!r}"


# ---------------------------------------------------------------------------
# service: create
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_writes_apps_yaml_and_values():
    svc = _svc()
    svc._git.read_file = AsyncMock(return_value="")
    svc._git.list_dir = AsyncMock(return_value=[])
    svc._gh.create_pr = AsyncMock(return_value="https://github.com/test/repo/pull/10")

    result = await svc.create(_SPEC)

    assert result.id == "keycloak-security"
    assert result.pr_url == "https://github.com/test/repo/pull/10"
    # write_file called at least twice: apps.yaml + values override
    assert svc._git.write_file.call_count >= 2


@pytest.mark.asyncio
async def test_create_no_values_override_skips_values_file():
    spec = _SPEC.model_copy(update={"values_override": ""})
    svc = _svc()
    svc._git.read_file = AsyncMock(return_value="")
    svc._gh.create_pr = AsyncMock(return_value="https://github.com/test/repo/pull/11")

    await svc.create(spec)

    # Only the apps.yaml write; no values file
    assert svc._git.write_file.call_count == 1


# ---------------------------------------------------------------------------
# service: delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_removes_block():
    svc = _svc()
    svc._git.read_file = AsyncMock(return_value=_APPS_YAML)
    svc._gh.create_pr = AsyncMock(return_value="https://github.com/test/repo/pull/12")

    result = await svc.delete("keycloak-security")

    assert result.id == "keycloak-security"
    written = svc._git.write_file.call_args[0][1]
    assert "keycloak" not in written
    assert "existing-app" in written
