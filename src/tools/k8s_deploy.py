"""
Kubernetes application deployment tools — Phase 1.

All K8s operations are sent to the Go agent via MQTT (k8s.* task types).
Python only manages DB state (projects, environments, applications).

Tools:
  create_project          → DB row in `projects`
  create_environment      → DB row in `environments` + k8s.create_namespace
  deploy_image_app        → DB row in `applications`  + k8s.deploy_image
  get_app_status          → k8s.get_status (live from agent)
  scale_app               → DB update replicas       + k8s.scale
  delete_app              → DB cleanup               + k8s.delete_app
  set_env_var             → k8s.set_env_var
  set_resource_limits     → k8s.set_resource_limits
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool

from src.infrastructure.project_repo import PostgresProjectRepository
from src.infrastructure.application_repo import PostgresApplicationRepository
from src.tools.agent_task import _send_task_impl


# ── Helpers ───────────────────────────────────────────────────────────────────


def _slug(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")


async def _k8s(server_id: str, task_type: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    """Send a k8s task to the Go agent and parse the JSON result."""
    raw = await _send_task_impl(server_id, task_type, payload, wait_timeout=timeout)
    try:
        outer = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {"error": raw or "no response from agent"}

    # outer shape: {"status": "success"|"error", "result": {...}, "error": null|"msg"}
    if outer.get("status") == "error" or outer.get("error"):
        return {"error": outer.get("error") or "task failed"}

    # Unwrap the nested result (agent ActionResult data lives in outer["result"])
    inner = outer.get("result") or {}
    if isinstance(inner, dict) and inner.get("status") == "error":
        return {"error": inner.get("error") or "agent reported error"}

    # Return the agent's data payload directly
    return inner.get("data") or inner


def _resolve_server(env) -> str:
    """Return the server_id for an environment — used as the MQTT target."""
    if not env.server_id:
        raise ValueError(f"Environment '{env.name}' has no server_id. Was it created during enrollment?")
    return env.server_id


# ── Project tools ─────────────────────────────────────────────────────────────


@tool
def create_project(name: str, description: str | None = None) -> str:
    """Create a new project (top-level grouping for environments and applications)."""
    repo = PostgresProjectRepository()
    try:
        proj = repo.get_or_create_project(name, description)
        return f"Project '{proj.name}' ready (id: {proj.id})."
    except Exception as exc:
        return f"ERROR: {exc}"


# ── Environment tools ─────────────────────────────────────────────────────────


@tool
async def create_environment(
    project_name: str,
    environment_name: str,
    server_name: str,
) -> str:
    """Create an environment under a project and provision its Kubernetes namespace.

    Args:
        project_name: Name of the parent project (created automatically if missing).
        environment_name: Environment label, e.g. "staging" or "production".
        server_name: Server hostname or name that will host this environment.
    """
    from src.fleet.repository import PostgresServerRepository

    # Resolve server
    srv_repo = PostgresServerRepository()
    server = srv_repo.get_by_identifier(server_name)
    if not server:
        return f"Server '{server_name}' not found."

    proj_repo = PostgresProjectRepository()
    proj = proj_repo.get_or_create_project(project_name)
    namespace = f"{_slug(project_name)}-{_slug(environment_name)}"

    # Idempotent — if namespace already in DB, return early
    existing = proj_repo.get_environment(namespace)
    if existing:
        return (
            f"Environment '{environment_name}' already exists "
            f"(namespace: {namespace})."
        )

    # Tell Go agent to create the namespace
    result = await _k8s(server.server_id, "k8s.create_namespace", {"namespace": namespace})
    if result.get("error"):
        return f"ERROR: Failed to create namespace on agent: {result['error']}"

    # Persist DB record
    env = proj_repo.get_or_create_environment(
        project_id=str(proj.id),
        name=environment_name,
        namespace=namespace,
        server_id=server.server_id,
        is_default=False,
    )

    return (
        f"Created environment '{env.name}' in project '{project_name}'.\n"
        f"  Namespace:  {env.namespace}\n"
        f"  Server:     {server_name} ({server.server_id})"
    )


# ── Application deployment tools ──────────────────────────────────────────────


@tool
async def deploy_image_app(
    name: str,
    image: str,
    environment: str = "default",
    server_name: str | None = None,
    replicas: int = 1,
    ports: str | None = None,
    env_vars: str | None = None,
    cpu: str | None = None,
    memory: str | None = None,
) -> str:
    """Deploy a container image to a Kubernetes environment.

    Args:
        name: Application name, e.g. "frontend".
        image: Docker image reference, e.g. "nginx:latest".
        environment: Namespace/environment name. Use "default" for the standard namespace (default).
        server_name: Server hostname or name — required when environment="default" and no
                     default environment exists yet for this server.
        replicas: Number of pod replicas (default 1).
        ports: Comma-separated container ports, e.g. "80,443".
        env_vars: Semicolon-separated KEY=VALUE pairs, e.g. "DEBUG=true;PORT=8080".
        cpu: CPU limit, e.g. "500m".
        memory: Memory limit, e.g. "512Mi".
    """
    from src.fleet.repository import PostgresServerRepository

    proj_repo = PostgresProjectRepository()
    app_repo = PostgresApplicationRepository()

    env = proj_repo.get_environment(environment)
    if not env:
        # Auto-bootstrap the "default" environment for this server so the
        # user doesn't need to run create_project / create_environment first.
        if environment == "default" and server_name:
            srv_repo = PostgresServerRepository()
            server = srv_repo.get_by_identifier(server_name)
            if not server:
                return f"Server '{server_name}' not found."
            proj = proj_repo.get_or_create_project("default", "Default project")
            env = proj_repo.get_or_create_environment(
                project_id=str(proj.id),
                name="default",
                namespace="default",
                server_id=server.server_id,
                is_default=True,
            )
        else:
            return (
                f"Environment '{environment}' not found. "
                "Pass server_name to auto-create it, or run create_environment first."
            )

    server_id = _resolve_server(env)

    # Parse ports
    port_list: list[int] = []
    if ports:
        port_list = [int(p.strip()) for p in ports.split(",") if p.strip()]

    # Parse env vars
    env_dict: dict[str, str] = {}
    if env_vars:
        for pair in env_vars.split(";"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                env_dict[k.strip()] = v.strip()

    # Create DB record first (so we can update status on failure)
    app_rec = app_repo.create_app(
        name=name,
        environment_id=str(env.id),
        image=image,
        replicas=replicas,
    )

    # Build agent payload
    payload: dict[str, Any] = {
        "name": name,
        "namespace": env.namespace,
        "image": image,
        "replicas": replicas,
        "ports": port_list,
        "env_vars": env_dict,
    }
    if cpu:
        payload["cpu"] = cpu
    if memory:
        payload["memory"] = memory

    result = await _k8s(server_id, "k8s.deploy_image", payload, timeout=120)
    if result.get("error"):
        app_repo.update_status(str(app_rec.id), "failed")
        return f"ERROR: Deployment failed: {result['error']}"

    app_repo.update_status(str(app_rec.id), "running")
    app_repo.track_resource(str(app_rec.id), "Deployment", name, env.namespace)
    if port_list:
        app_repo.track_resource(str(app_rec.id), "Service", name, env.namespace)

    lines = [f"Deployed '{name}' to {env.namespace}."]
    lines.append(f"  Image:     {image}")
    lines.append(f"  Replicas:  {replicas}")
    if result.get("cluster_ip"):
        lines.append(f"  ClusterIP: {result['cluster_ip']}")
    lines.append(f"  Status:    {result.get('status', 'deployed')}")
    return "\n".join(lines)


@tool
async def get_app_status(name: str, environment: str) -> str:
    """Check the live status of a deployed application (pods + deployment replicas)."""
    proj_repo = PostgresProjectRepository()

    env = proj_repo.get_environment(environment)
    if not env:
        return f"Environment '{environment}' not found."

    server_id = _resolve_server(env)
    result = await _k8s(server_id, "k8s.get_status", {"name": name, "namespace": env.namespace})

    if result.get("error"):
        return f"ERROR: {result['error']}"

    dep = result.get("deployment", {})
    pods = result.get("pods", [])
    image = result.get("image", "unknown")

    lines = [f"App '{name}' in {environment}"]
    lines.append(f"  Image:     {image}")
    lines.append(
        f"  Replicas:  {dep.get('ready', 0)}/{dep.get('desired', 0)} ready  "
        f"(available: {dep.get('available', 0)}, updated: {dep.get('updated', 0)})"
    )
    if pods:
        lines.append("  Pods:")
        for p in pods:
            lines.append(
                f"    • {p['name']}: {p['status']}  "
                f"(node: {p.get('node', '?')}, restarts: {p.get('restarts', 0)})"
            )
    else:
        lines.append("  Pods: none found")

    return "\n".join(lines)


@tool
async def scale_app(name: str, environment: str, replicas: int) -> str:
    """Scale a deployed application to the given number of replicas."""
    proj_repo = PostgresProjectRepository()
    app_repo = PostgresApplicationRepository()

    env = proj_repo.get_environment(environment)
    if not env:
        return f"Environment '{environment}' not found."

    app = app_repo.get_app(name, str(env.id))
    if not app:
        return f"App '{name}' not found in '{environment}'."

    server_id = _resolve_server(env)
    result = await _k8s(server_id, "k8s.scale", {
        "name": name,
        "namespace": env.namespace,
        "replicas": replicas,
    })

    if result.get("error"):
        return f"ERROR: Scale failed: {result['error']}"

    app_repo.update_replicas(str(app.id), replicas)
    return f"Scaled '{name}' in '{environment}' to {replicas} replica(s)."


@tool
async def delete_app(name: str, environment: str) -> str:
    """Delete an application and remove its Kubernetes Deployment and Service."""
    proj_repo = PostgresProjectRepository()
    app_repo = PostgresApplicationRepository()

    env = proj_repo.get_environment(environment)
    if not env:
        return f"Environment '{environment}' not found."

    app = app_repo.get_app(name, str(env.id))
    if not app:
        return f"App '{name}' not found in '{environment}'."

    server_id = _resolve_server(env)
    result = await _k8s(server_id, "k8s.delete_app", {
        "name": name,
        "namespace": env.namespace,
    })

    if result.get("error"):
        return f"ERROR: Delete failed: {result['error']}"

    app_repo.delete_resources_for_app(str(app.id))
    app_repo.delete_app(str(app.id))

    return f"Deleted app '{name}' from '{environment}'."


@tool
async def set_env_var(app: str, environment: str, key: str, value: str) -> str:
    """Set (or update) an environment variable on a deployed application.

    Triggers a rolling restart of the Deployment.
    """
    proj_repo = PostgresProjectRepository()
    app_repo = PostgresApplicationRepository()

    env = proj_repo.get_environment(environment)
    if not env:
        return f"Environment '{environment}' not found."

    if not app_repo.get_app(app, str(env.id)):
        return f"App '{app}' not found in '{environment}'."

    server_id = _resolve_server(env)
    result = await _k8s(server_id, "k8s.set_env_var", {
        "name": app,
        "namespace": env.namespace,
        "key": key,
        "value": value,
    })

    if result.get("error"):
        return f"ERROR: {result['error']}"

    return f"Set {key}={value} on '{app}' in '{environment}'. Rolling update in progress."


@tool
async def set_resource_limits(
    app: str,
    environment: str,
    cpu: str | None = None,
    memory: str | None = None,
) -> str:
    """Set CPU and/or memory resource limits on a deployed application.

    Args:
        app: Application name.
        environment: Namespace name.
        cpu: CPU limit e.g. "500m" or "1".
        memory: Memory limit e.g. "512Mi" or "1Gi".
    """
    if not cpu and not memory:
        return "No limits provided. Specify at least one of cpu/memory."

    proj_repo = PostgresProjectRepository()
    app_repo = PostgresApplicationRepository()

    env = proj_repo.get_environment(environment)
    if not env:
        return f"Environment '{environment}' not found."

    if not app_repo.get_app(app, str(env.id)):
        return f"App '{app}' not found in '{environment}'."

    server_id = _resolve_server(env)
    payload: dict[str, Any] = {"name": app, "namespace": env.namespace}
    if cpu:
        payload["cpu"] = cpu
    if memory:
        payload["memory"] = memory

    result = await _k8s(server_id, "k8s.set_resource_limits", payload)

    if result.get("error"):
        return f"ERROR: {result['error']}"

    parts = []
    if cpu:
        parts.append(f"cpu={cpu}")
    if memory:
        parts.append(f"memory={memory}")
    return f"Updated resource limits on '{app}': {', '.join(parts)}. Rolling update in progress."


@tool
async def list_deployments(server_name: str, namespace: str | None = None) -> str:
    """List all Kubernetes pods and deployments on a server across all namespaces.

    Use this to find what applications are running before deleting or managing them.

    Args:
        server_name: Server hostname or name.
        namespace: Filter by namespace (optional). Omit to list all namespaces.
    """
    from src.fleet.repository import PostgresServerRepository

    srv_repo = PostgresServerRepository()
    server = srv_repo.get_by_identifier(server_name)
    if not server:
        return f"Server '{server_name}' not found."

    script = (
        f"/usr/local/bin/k3s kubectl get pods,deployments -n {namespace} -o wide"
        if namespace
        else "/usr/local/bin/k3s kubectl get pods,deployments -A -o wide"
    )
    raw = await _send_task_impl(server.server_id, "exec.run", {"script": script}, wait_timeout=30)
    try:
        outer = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw or "No response from agent."

    if outer.get("status") == "error":
        return f"ERROR: {outer.get('error')}"

    result = outer.get("result") or {}
    stdout = result.get("stdout") or result.get("data", {}).get("stdout", "")
    stderr = result.get("stderr") or result.get("data", {}).get("stderr", "")

    if not stdout.strip():
        return f"No pods found{f' in namespace {namespace}' if namespace else ''}.\nstderr: {stderr}"
    return stdout


@tool
async def delete_k8s_app(server_name: str, app_name: str, namespace: str) -> str:
    """Delete a Kubernetes application (Deployment + Service) directly by name and namespace.

    Use this when the app may not be tracked in the database (e.g. deployed outside this system).
    For DB-tracked apps use delete_app instead.

    Args:
        server_name: Server hostname or name.
        app_name: Name of the Kubernetes Deployment to delete.
        namespace: Kubernetes namespace the app lives in.
    """
    from src.fleet.repository import PostgresServerRepository

    srv_repo = PostgresServerRepository()
    server = srv_repo.get_by_identifier(server_name)
    if not server:
        return f"Server '{server_name}' not found."

    result = await _k8s(server.server_id, "k8s.delete_app", {
        "name": app_name,
        "namespace": namespace,
    })

    if result.get("error"):
        return f"ERROR: Delete failed: {result['error']}"

    # Also clean up DB record if it exists
    from src.infrastructure.project_repo import PostgresProjectRepository
    from src.infrastructure.application_repo import PostgresApplicationRepository
    proj_repo = PostgresProjectRepository()
    app_repo = PostgresApplicationRepository()
    env = proj_repo.get_environment(namespace)
    if env:
        app = app_repo.get_app(app_name, str(env.id))
        if app:
            app_repo.delete_resources_for_app(str(app.id))
            app_repo.delete_app(str(app.id))

    return f"Deleted '{app_name}' from namespace '{namespace}' on server '{server_name}'."


__all__ = [
    "create_project",
    "create_environment",
    "deploy_image_app",
    "list_deployments",
    "get_app_status",
    "scale_app",
    "delete_app",
    "delete_k8s_app",
    "set_env_var",
    "set_resource_limits",
]
