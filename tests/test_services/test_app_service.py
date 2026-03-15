"""
Unit tests for AppService — mocks GitService and GitHubService.
"""

import pytest
import yaml
import textwrap
from unittest.mock import AsyncMock

from gitopsgui.models.application import ApplicationSpec
from gitopsgui.services.app_service import (
    AppService,
    _app_yaml_path,
    _app_values_path,
    _kustomization_path,
    _cluster_apps_path,
    _comment_app_block,
    _render_app_yaml,
    _render_kustomization,
)


_SPEC = ApplicationSpec(
    name="my-app",
    cluster="production",
    helm_repo_url="https://charts.example.com",
    chart_name="my-chart",
    chart_version="2.3.4",
    values_yaml="replicaCount: 2\n",
)


def _svc() -> AppService:
    svc = AppService()
    svc._git = AsyncMock()
    svc._gh = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# path helpers
# ---------------------------------------------------------------------------

def test_app_yaml_path():
    assert _app_yaml_path("my-app") == "gitops/gitops-apps/my-app/my-app.yaml"


def test_app_values_path():
    assert _app_values_path("my-app") == "gitops/gitops-apps/my-app/my-app-values.yaml"


def test_kustomization_path():
    assert _kustomization_path("my-app") == "gitops/gitops-apps/my-app/kustomization.yaml"


# ---------------------------------------------------------------------------
# render helpers
# ---------------------------------------------------------------------------

def test_render_app_yaml_contains_helm_release():
    out = _render_app_yaml(_SPEC)
    assert "HelmRelease" in out
    assert "my-app" in out
    assert "https://charts.example.com" in out
    assert "my-chart" in out
    assert "2.3.4" in out


def test_render_app_yaml_contains_namespace():
    out = _render_app_yaml(_SPEC)
    assert "kind: Namespace" in out


def test_render_app_yaml_references_values_configmap():
    out = _render_app_yaml(_SPEC)
    assert "my-app-values" in out


def test_render_kustomization_references_name():
    out = _render_kustomization("my-app")
    assert "my-app.yaml" in out
    assert "my-app-values" in out
    assert "kustomizeconfig.yaml" in out


# ---------------------------------------------------------------------------
# get_application
# ---------------------------------------------------------------------------

async def test_get_application_not_found_returns_none():
    svc = _svc()
    svc._git.read_file = AsyncMock(side_effect=FileNotFoundError)
    result = await svc.get_application("missing")
    assert result is None


async def test_get_application_parses_multi_doc_yaml():
    svc = _svc()
    multi_doc = textwrap.dedent("""\
        ---
        apiVersion: v1
        kind: Namespace
        metadata:
          name: my-app
        ---
        apiVersion: source.toolkit.fluxcd.io/v1
        kind: HelmRepository
        metadata:
          name: my-app
          namespace: flux-system
        spec:
          interval: 24h
          url: https://charts.example.com
        ---
        apiVersion: helm.toolkit.fluxcd.io/v2
        kind: HelmRelease
        metadata:
          name: my-app
          namespace: flux-system
        spec:
          targetNamespace: production
          interval: 30m
          chart:
            spec:
              chart: my-chart
              version: "2.3.4"
              sourceRef:
                kind: HelmRepository
                name: my-app
                namespace: flux-system
          valuesFrom:
            - kind: ConfigMap
              name: my-app-values
    """)
    svc._git.read_file = AsyncMock(return_value=multi_doc)
    result = await svc.get_application("my-app")
    assert result is not None
    assert result.spec.chart_name == "my-chart"
    assert result.spec.chart_version == "2.3.4"
    assert result.spec.helm_repo_url == "https://charts.example.com"


# ---------------------------------------------------------------------------
# list_applications
# ---------------------------------------------------------------------------

async def test_list_applications_returns_all_found():
    svc = _svc()
    svc._git.list_dir = AsyncMock(return_value=["app-a", "app-b"])
    # Both apps found (get_application returns non-None)
    multi_doc_a = _render_app_yaml(ApplicationSpec(
        name="app-a", cluster="dev", helm_repo_url="https://repo.example.com",
        chart_name="chart-a", chart_version="1.0.0",
    ))
    multi_doc_b = _render_app_yaml(ApplicationSpec(
        name="app-b", cluster="ete", helm_repo_url="https://repo.example.com",
        chart_name="chart-b", chart_version="2.0.0",
    ))
    svc._git.read_file = AsyncMock(side_effect=[multi_doc_a, multi_doc_b])
    results = await svc.list_applications()
    assert len(results) == 2


async def test_list_applications_skips_missing():
    svc = _svc()
    svc._git.list_dir = AsyncMock(return_value=["app-a", "broken"])
    multi_doc_a = _render_app_yaml(ApplicationSpec(
        name="app-a", cluster="dev", helm_repo_url="https://repo.example.com",
        chart_name="chart-a", chart_version="1.0.0",
    ))
    svc._git.read_file = AsyncMock(side_effect=[multi_doc_a, FileNotFoundError])
    results = await svc.list_applications()
    assert len(results) == 1


# ---------------------------------------------------------------------------
# create_application
# ---------------------------------------------------------------------------

async def test_create_application_writes_four_files_and_opens_pr():
    svc = _svc()
    svc._git.create_branch = AsyncMock()
    svc._git.write_file = AsyncMock()
    svc._git.commit = AsyncMock(return_value="sha")
    svc._git.push = AsyncMock()
    svc._gh.create_pr = AsyncMock(return_value="https://github.com/test/repo/pull/9")

    result = await svc.create_application(_SPEC)

    assert svc._git.write_file.call_count == 4  # app.yaml + values + kustomization + kustomizeconfig
    svc._gh.create_pr.assert_called_once()
    assert result.pr_url == "https://github.com/test/repo/pull/9"


async def test_create_application_pr_labelled_application_and_cluster():
    svc = _svc()
    svc._git.create_branch = AsyncMock()
    svc._git.write_file = AsyncMock()
    svc._git.commit = AsyncMock(return_value="sha")
    svc._git.push = AsyncMock()
    svc._gh.create_pr = AsyncMock(return_value="https://github.com/test/repo/pull/10")

    await svc.create_application(_SPEC)

    labels = svc._gh.create_pr.call_args.kwargs.get("labels") or svc._gh.create_pr.call_args.args[3]
    assert "application" in labels
    assert "stage:production" in labels


async def test_create_application_writes_values_yaml():
    svc = _svc()
    svc._git.create_branch = AsyncMock()
    svc._git.write_file = AsyncMock()
    svc._git.commit = AsyncMock(return_value="sha")
    svc._git.push = AsyncMock()
    svc._gh.create_pr = AsyncMock(return_value="https://github.com/test/repo/pull/11")

    await svc.create_application(_SPEC)

    all_paths = [call.args[0] for call in svc._git.write_file.call_args_list]
    assert any("my-app-values.yaml" in p for p in all_paths)


# ---------------------------------------------------------------------------
# _cluster_apps_path helper
# ---------------------------------------------------------------------------

def test_cluster_apps_path():
    assert _cluster_apps_path("openclaw") == "clusters/openclaw/openclaw-apps.yaml"


# ---------------------------------------------------------------------------
# _comment_app_block — pure function tests with realistic openclaw content
# ---------------------------------------------------------------------------

# The combined apps file as it exists in clusters/openclaw/openclaw-apps.yaml
_OPENCLAW_APPS_YAML = textwrap.dedent("""\
    ---
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: openclaw
      namespace: flux-system
    spec:
      interval: 1h
      retryInterval: 1m
      timeout: 5m
      sourceRef:
        kind: GitRepository
        name: flux-system
      path: ./gitops/gitops-apps/openclaw
      prune: true

    ---
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: ollama
      namespace: flux-system
    spec:
      interval: 1h
      retryInterval: 1m
      timeout: 5m
      sourceRef:
        kind: GitRepository
        name: flux-system
      path: ./gitops/gitops-apps/ollama
      prune: true

    ---
    apiVersion: kustomize.toolkit.fluxcd.io/v1
    kind: Kustomization
    metadata:
      name: qdrant
      namespace: flux-system
    spec:
      interval: 1h
      retryInterval: 1m
      timeout: 5m
      sourceRef:
        kind: GitRepository
        name: flux-system
      path: ./gitops/gitops-apps/qdrant
      prune: true
""")


def test_comment_app_block_ollama_found():
    _, found = _comment_app_block(_OPENCLAW_APPS_YAML, "ollama")
    assert found is True


def test_comment_app_block_ollama_comments_only_ollama_block():
    updated, _ = _comment_app_block(_OPENCLAW_APPS_YAML, "ollama")
    # openclaw and qdrant blocks must still have active lines
    assert "path: ./gitops/gitops-apps/openclaw" in updated
    assert "path: ./gitops/gitops-apps/qdrant" in updated
    # no active (uncommented) line may reference ollama
    active_ollama = [l for l in updated.splitlines() if "ollama" in l and not l.lstrip().startswith("#")]
    assert active_ollama == [], f"Uncommented lines reference ollama: {active_ollama}"


def test_comment_app_block_qdrant_found():
    _, found = _comment_app_block(_OPENCLAW_APPS_YAML, "qdrant")
    assert found is True


def test_comment_app_block_qdrant_comments_only_qdrant_block():
    updated, _ = _comment_app_block(_OPENCLAW_APPS_YAML, "qdrant")
    assert "path: ./gitops/gitops-apps/openclaw" in updated
    assert "path: ./gitops/gitops-apps/ollama" in updated
    active_qdrant = [l for l in updated.splitlines() if "qdrant" in l and not l.lstrip().startswith("#")]
    assert active_qdrant == [], f"Uncommented lines reference qdrant: {active_qdrant}"


def test_comment_app_block_not_found():
    _, found = _comment_app_block(_OPENCLAW_APPS_YAML, "nonexistent")
    assert found is False


def test_comment_app_block_no_double_comment():
    """Already-commented lines must not gain a second # prefix."""
    already = "---\nkind: Kustomization\n  name: ollama\n# already: commented\n"
    updated, _ = _comment_app_block(already, "ollama")
    assert "## " not in updated


# ---------------------------------------------------------------------------
# disable_application — service-level unit tests
# ---------------------------------------------------------------------------

def _disable_svc(apps_yaml: str) -> AppService:
    """Return a fully-wired AppService mock for a disable_application call."""
    svc = _svc()
    svc._git.create_branch = AsyncMock()
    svc._git.write_file = AsyncMock()
    svc._git.commit = AsyncMock(return_value="sha")
    svc._git.push = AsyncMock()
    svc._gh.create_pr = AsyncMock(return_value="https://github.com/test/repo/pull/99")
    # read_file: first call → combined apps yaml; second call (get_application) → not found
    svc._git.read_file = AsyncMock(side_effect=[apps_yaml, FileNotFoundError])
    return svc


async def test_disable_ollama_reads_cluster_apps_file():
    svc = _disable_svc(_OPENCLAW_APPS_YAML)
    await svc.disable_application("ollama", "openclaw")
    read_path = svc._git.read_file.call_args_list[0].args[0]
    assert read_path == "clusters/openclaw/openclaw-apps.yaml"


async def test_disable_qdrant_reads_cluster_apps_file():
    svc = _disable_svc(_OPENCLAW_APPS_YAML)
    await svc.disable_application("qdrant", "openclaw")
    read_path = svc._git.read_file.call_args_list[0].args[0]
    assert read_path == "clusters/openclaw/openclaw-apps.yaml"


async def test_disable_ollama_writes_only_ollama_commented():
    svc = _disable_svc(_OPENCLAW_APPS_YAML)
    await svc.disable_application("ollama", "openclaw")
    written = svc._git.write_file.call_args.args[1]
    assert "path: ./gitops/gitops-apps/openclaw" in written
    assert "path: ./gitops/gitops-apps/qdrant" in written
    active_ollama = [l for l in written.splitlines() if "ollama" in l and not l.lstrip().startswith("#")]
    assert active_ollama == [], f"Uncommented lines reference ollama: {active_ollama}"


async def test_disable_qdrant_writes_only_qdrant_commented():
    svc = _disable_svc(_OPENCLAW_APPS_YAML)
    await svc.disable_application("qdrant", "openclaw")
    written = svc._git.write_file.call_args.args[1]
    assert "path: ./gitops/gitops-apps/openclaw" in written
    assert "path: ./gitops/gitops-apps/ollama" in written
    active_qdrant = [l for l in written.splitlines() if "qdrant" in l and not l.lstrip().startswith("#")]
    assert active_qdrant == [], f"Uncommented lines reference qdrant: {active_qdrant}"


async def test_disable_opens_pr_with_correct_labels():
    svc = _disable_svc(_OPENCLAW_APPS_YAML)
    await svc.disable_application("ollama", "openclaw")
    labels = (
        svc._gh.create_pr.call_args.kwargs.get("labels")
        or svc._gh.create_pr.call_args.args[3]
    )
    assert "application" in labels
    assert "stage:openclaw" in labels


async def test_disable_returns_pr_url():
    svc = _disable_svc(_OPENCLAW_APPS_YAML)
    result = await svc.disable_application("ollama", "openclaw")
    assert result.pr_url == "https://github.com/test/repo/pull/99"


async def test_disable_apps_file_not_found_raises_404():
    from fastapi import HTTPException
    svc = _svc()
    svc._git.create_branch = AsyncMock()
    svc._git.read_file = AsyncMock(side_effect=FileNotFoundError)
    with pytest.raises(HTTPException) as exc_info:
        await svc.disable_application("ollama", "openclaw")
    assert exc_info.value.status_code == 404


async def test_disable_app_not_in_file_raises_404():
    from fastapi import HTTPException
    svc = _svc()
    svc._git.create_branch = AsyncMock()
    svc._git.read_file = AsyncMock(return_value=_OPENCLAW_APPS_YAML)
    with pytest.raises(HTTPException) as exc_info:
        await svc.disable_application("nonexistent", "openclaw")
    assert exc_info.value.status_code == 404
