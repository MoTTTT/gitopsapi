"""
GITGUI-006 — Application object reader/writer.

Multi-repo layout (per cluster):
  {cluster}-apps repo:
    gitops/gitops-apps/<name>/<name>.yaml           — HelmRepository + HelmRelease
    gitops/gitops-apps/<name>/<name>-values.yaml    — chart values
    gitops/gitops-apps/<name>/kustomization.yaml
    gitops/gitops-apps/<name>/kustomizeconfig.yaml

  {cluster}-infra repo:
    clusters/<cluster>/<cluster>-apps.yaml          — Flux Kustomization entries

Disable/enable operations modify the Kustomization entry in {cluster}-infra.
create_application writes HelmRelease content to {cluster}-apps.

PR targets the repo where the change was made.
"""

import re
import textwrap
import uuid
from typing import List, Optional, Tuple

import yaml

from ..models.application import ApplicationSpec, ApplicationResponse
from .git_service import GitService
from .github_service import GitHubService
from .repo_router import git_for_apps, git_for_infra, github_for_apps, github_for_infra

_APPS_BASE = "gitops/gitops-apps"


def _app_yaml_path(name: str) -> str:
    return f"{_APPS_BASE}/{name}/{name}.yaml"


def _app_values_path(name: str) -> str:
    return f"{_APPS_BASE}/{name}/{name}-values.yaml"


def _kustomization_path(name: str) -> str:
    return f"{_APPS_BASE}/{name}/kustomization.yaml"


def _kustomizeconfig_path(name: str) -> str:
    return f"{_APPS_BASE}/{name}/kustomizeconfig.yaml"


def _render_app_yaml(spec: ApplicationSpec) -> str:
    return textwrap.dedent(f"""\
        ---
        apiVersion: v1
        kind: Namespace
        metadata:
          name: {spec.name}

        ---
        apiVersion: source.toolkit.fluxcd.io/v1
        kind: HelmRepository
        metadata:
          name: {spec.name}
          namespace: flux-system
        spec:
          interval: 24h
          url: {spec.helm_repo_url}

        ---
        apiVersion: helm.toolkit.fluxcd.io/v2
        kind: HelmRelease
        metadata:
          name: {spec.name}
          namespace: flux-system
        spec:
          targetNamespace: {spec.name}
          interval: 30m
          chart:
            spec:
              chart: {spec.chart_name}
              version: "{spec.chart_version}"
              sourceRef:
                kind: HelmRepository
                name: {spec.name}
                namespace: flux-system
              interval: 12h
          valuesFrom:
            - kind: ConfigMap
              name: {spec.name}-values
    """)


def _render_kustomization(name: str) -> str:
    return textwrap.dedent(f"""\
        apiVersion: kustomize.config.k8s.io/v1beta1
        kind: Kustomization
        resources:
          - {name}.yaml
        configMapGenerator:
          - name: {name}-values
            namespace: flux-system
            files:
              - values.yaml={name}-values.yaml
        configurations:
          - kustomizeconfig.yaml
    """)


def _cluster_apps_path(cluster: str) -> str:
    """Path of the combined kustomization file for all apps on a cluster."""
    return f"clusters/{cluster}/{cluster}-apps.yaml"


def _comment_app_block(content: str, app_name: str) -> Tuple[str, bool]:
    """Comment out the Kustomization document for app_name in a multi-doc YAML string.

    Leaves all other documents unchanged.
    Returns (updated_content, found) where found is True if the block was located.
    """
    # Split on bare '---' document separators; first element may be empty
    raw_blocks = re.split(r"(?m)^---\s*$", content)
    found = False
    result_blocks: List[str] = []

    for block in raw_blocks:
        is_target = (
            re.search(rf"^\s+name:\s+{re.escape(app_name)}\s*$", block, re.MULTILINE)
            and "kind: Kustomization" in block
        )
        if is_target:
            found = True
            commented_lines = [
                f"# {line}" if (line.strip() and not line.lstrip().startswith("#")) else line
                for line in block.splitlines()
            ]
            result_blocks.append("\n".join(commented_lines))
        else:
            result_blocks.append(block)

    # Rejoin: first block precedes the first ---, the rest follow ---
    updated = result_blocks[0] + "".join(
        "---\n" + blk.lstrip("\n") for blk in result_blocks[1:]
    )
    return updated, found


def _uncomment_app_block(content: str, app_name: str) -> Tuple[str, bool]:
    """Uncomment a previously commented Kustomization document for app_name.

    Strips the leading '# ' prefix from every commented line inside the block
    that matches app_name + kind: Kustomization.
    Returns (updated_content, found).
    """
    raw_blocks = re.split(r"(?m)^---\s*$", content)
    found = False
    result_blocks: List[str] = []

    for block in raw_blocks:
        # Match blocks where every non-empty line is commented and the block
        # contains the target name and Kustomization kind (after stripping '#')
        stripped = "\n".join(
            line[2:] if line.startswith("# ") else (line[1:] if line.startswith("#") else line)
            for line in block.splitlines()
        )
        is_target = (
            re.search(rf"^\s+name:\s+{re.escape(app_name)}\s*$", stripped, re.MULTILINE)
            and "kind: Kustomization" in stripped
        )
        if is_target:
            found = True
            uncommented_lines = [
                line[2:] if line.startswith("# ") else (line[1:] if line.startswith("#") else line)
                for line in block.splitlines()
            ]
            result_blocks.append("\n".join(uncommented_lines))
        else:
            result_blocks.append(block)

    updated = result_blocks[0] + "".join(
        "---\n" + blk.lstrip("\n") for blk in result_blocks[1:]
    )
    return updated, found


_KUSTOMIZECONFIG = textwrap.dedent("""\
    nameReference:
    - kind: ConfigMap
      version: v1
      fieldSpecs:
      - path: spec/valuesFrom/name
        kind: HelmRelease
""")


class AppService:
    def __init__(self):
        # _git / _gh are None by default — write operations derive per-cluster instances
        # via repo_router. Set these to AsyncMock in tests to override routing.
        self._git = None
        self._gh = None

    def _apps_git(self, cluster: str) -> GitService:
        """Return a GitService targeting the {cluster}-apps repo (or test override)."""
        return self._git or git_for_apps(cluster)

    def _apps_gh(self, cluster: str) -> GitHubService:
        """Return a GitHubService targeting the {cluster}-apps repo (or test override)."""
        return self._gh or github_for_apps(cluster)

    def _infra_git(self, cluster: str) -> GitService:
        """Return a GitService targeting the {cluster}-infra repo (or test override)."""
        return self._git or git_for_infra(cluster)

    def _infra_gh(self, cluster: str) -> GitHubService:
        return self._gh or github_for_infra(cluster)

    async def list_applications(self) -> List[ApplicationResponse]:
        # GAP: in the multi-repo model, apps live in {cluster}-apps repos — no single
        # listing across all clusters without a cluster registry.
        # When self._git is injected (test mode or single-repo mode) we can list.
        if self._git is None:
            return []
        names = await self._git.list_dir(_APPS_BASE)
        results = []
        for name in names:
            app = await self.get_application(name)
            if app:
                results.append(app)
        return results

    async def get_application(self, name: str) -> Optional[ApplicationResponse]:
        # GAP: requires cluster context for multi-repo routing.
        # When self._git is injected (test mode or single-repo mode) we can look up by name.
        if self._git is None:
            return None
        try:
            raw = await self._git.read_file(_app_yaml_path(name))
        except FileNotFoundError:
            return None
        # Parse multi-doc YAML: extract HelmRepository URL and HelmRelease chart spec
        helm_repo_url = ""
        chart_name = ""
        chart_version = ""
        for doc in yaml.safe_load_all(raw):
            if not doc:
                continue
            kind = doc.get("kind", "")
            if kind == "HelmRepository":
                helm_repo_url = doc.get("spec", {}).get("url", "")
            elif kind == "HelmRelease":
                chart_spec = doc.get("spec", {}).get("chart", {}).get("spec", {})
                chart_name = chart_spec.get("chart", "")
                chart_version = str(chart_spec.get("version", ""))
        spec = ApplicationSpec(
            name=name,
            cluster="",
            helm_repo_url=helm_repo_url,
            chart_name=chart_name,
            chart_version=chart_version,
        )
        return ApplicationResponse(name=name, spec=spec)

    async def create_application(self, spec: ApplicationSpec) -> ApplicationResponse:
        git = self._apps_git(spec.cluster)
        gh = self._apps_gh(spec.cluster)
        branch = f"application/add-{spec.name}-{uuid.uuid4().hex[:8]}"
        await git.create_branch(branch)

        await git.write_file(_app_yaml_path(spec.name), _render_app_yaml(spec))
        await git.write_file(_app_values_path(spec.name), spec.values_yaml or "")
        await git.write_file(_kustomization_path(spec.name), _render_kustomization(spec.name))
        await git.write_file(_kustomizeconfig_path(spec.name), _KUSTOMIZECONFIG)

        await git.commit(f"chore: add application {spec.name}")
        await git.push()

        pr_url = await gh.create_pr(
            branch=branch,
            title=f"Add application: {spec.name}",
            body=f"Add workload `{spec.name}` (chart: {spec.chart_name} {spec.chart_version}) to cluster `{spec.cluster}`.",
            labels=["application", f"stage:{spec.cluster}"],
            reviewers=[],
        )

        return ApplicationResponse(name=spec.name, spec=spec, pr_url=pr_url)

    async def disable_application(self, name: str, cluster: str) -> ApplicationResponse:
        """Comment out the app's Kustomization block in {cluster}-infra repo."""
        from fastapi import HTTPException

        git = self._infra_git(cluster)
        gh = self._infra_gh(cluster)
        apps_path = _cluster_apps_path(cluster)
        branch = f"application/disable-{name}-{uuid.uuid4().hex[:8]}"
        await git.create_branch(branch)

        try:
            current = await git.read_file(apps_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Apps file not found: {apps_path}")

        updated, found = _comment_app_block(current, name)
        if not found:
            raise HTTPException(
                status_code=404,
                detail=f"Kustomization for {name!r} not found in {apps_path}",
            )

        await git.write_file(apps_path, updated)
        await git.commit(f"chore: disable application {name} on {cluster}")
        await git.push()

        pr_url = await gh.create_pr(
            branch=branch,
            title=f"Disable application: {name} on {cluster}",
            body=(
                f"Comments out the `{name}` Kustomization block in `{apps_path}`. "
                f"The app definition in `{cluster}-apps/gitops/gitops-apps/{name}/` is retained."
            ),
            labels=["application", f"stage:{cluster}"],
            reviewers=[],
        )

        spec = ApplicationSpec(name=name, cluster=cluster, helm_repo_url="", chart_name="", chart_version="")
        return ApplicationResponse(name=name, spec=spec, pr_url=pr_url)

    async def enable_application(self, name: str, cluster: str) -> ApplicationResponse:
        """Uncomment the app's Kustomization block in {cluster}-infra repo."""
        from fastapi import HTTPException

        git = self._infra_git(cluster)
        gh = self._infra_gh(cluster)
        apps_path = _cluster_apps_path(cluster)
        branch = f"application/enable-{name}-{uuid.uuid4().hex[:8]}"
        await git.create_branch(branch)

        try:
            current = await git.read_file(apps_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Apps file not found: {apps_path}")

        updated, found = _uncomment_app_block(current, name)
        if not found:
            raise HTTPException(
                status_code=404,
                detail=f"Commented Kustomization for {name!r} not found in {apps_path}",
            )

        await git.write_file(apps_path, updated)
        await git.commit(f"chore: enable application {name} on {cluster}")
        await git.push()

        pr_url = await gh.create_pr(
            branch=branch,
            title=f"Enable application: {name} on {cluster}",
            body=f"Uncomments the `{name}` Kustomization block in `{apps_path}`.",
            labels=["application", f"stage:{cluster}"],
            reviewers=[],
        )

        spec = ApplicationSpec(name=name, cluster=cluster, helm_repo_url="", chart_name="", chart_version="")
        return ApplicationResponse(name=name, spec=spec, pr_url=pr_url)
