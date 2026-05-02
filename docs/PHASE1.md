# Phase 1: Core Application Deployment

**Status**: In Progress  
**Timeline**: 3-4 days  
**Goal**: Deploy a containerized app from an image to Kubernetes. No Ingress, no SSL — just `kubectl port-forward` or `NodePort` access.

---

## Deliverables Checklist

| # | Task | File(s) | Status |
|---|------|---------|--------|
| 1.0 | Write PHASE1.md (this file) | `docs/PHASE1.md` | 📝 In Progress |
| 1.1 | Create project registry table | `src/db/migrations/004_projects.sql` | ⏳ Pending |
| 1.2 | Create application registry tables | `src/db/migrations/005_applications.sql` | ⏳ Pending |
| 1.3 | Create project repository | `src/infrastructure/project_repo.py` | ⏳ Pending |
| 1.4 | Create application repository | `src/infrastructure/application_repo.py` | ⏳ Pending |
| 1.5 | Add `create_project` tool | `src/tools/k8s_deploy.py` | ⏳ Pending |
| 1.6 | Add `create_environment` tool | `src/tools/k8s_deploy.py` | ⏳ Pending |
| 1.7 | Add `deploy_image_app` tool | `src/tools/k8s_deploy.py` | ⏳ Pending |
| 1.8 | Add `get_app_status` tool | `src/tools/k8s_deploy.py` | ⏳ Pending |
| 1.9 | Add `scale_app` tool | `src/tools/k8s_deploy.py` | ⏳ Pending |
| 1.10 | Add `delete_app` tool | `src/tools/k8s_deploy.py` | ⏳ Pending |
| 1.11 | Add `set_env_var` tool | `src/tools/k8s_deploy.py` | ⏳ Pending |
| 1.12 | Add `set_resource_limits` tool | `src/tools/k8s_deploy.py` | ⏳ Pending |
| 1.13 | K8s resource tracking | `src/infrastructure/k8s_client.py` | ⏳ Pending |
| 1.14 | Wire into tools/__init__.py, agent prompt, MCP | Multiple | ⏳ Pending |

---

## Data Model

### Relationships
```
Project 1--* Environment 1--* Application
```

### projects
```sql
CREATE TABLE projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### environments
```sql
CREATE TABLE environments (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    namespace   TEXT NOT NULL UNIQUE,
    cluster_id  UUID REFERENCES clusters(id),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, name)
);
```

### applications
```sql
CREATE TABLE applications (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    environment_id UUID NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    app_type    TEXT, -- 'web', 'api', 'worker', 'static'
    source_type TEXT, -- 'image', 'git', 'upload'
    source_url  TEXT,
    image       TEXT,
    replicas    INT DEFAULT 1,
    status      TEXT DEFAULT 'pending',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(environment_id, name)
);
```

### k8s_resources (tracks every K8s object created)
```sql
CREATE TABLE k8s_resources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id  UUID REFERENCES applications(id) ON DELETE SET NULL,
    resource_type   TEXT NOT NULL, -- 'Deployment', 'Service', 'ConfigMap', 'Secret', 'PVC'
    resource_name   TEXT NOT NULL,
    namespace       TEXT NOT NULL,
    manifest        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   User Request  │────▶│  k8s_deploy.py   │────▶│    K8sClient    │
│  "deploy nginx" │     │   (LangChain     │     │  (kubernetes    │
│                 │     │     tools)       │     │     SDK)        │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │                         │
         ▼                       ▼                         ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  project_repo   │     │ application_repo │     │   K8s Cluster   │
│  (Postgres)     │     │    (Postgres)    │     │  (Deployment+   │
│                 │     │                  │     │   Service)      │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

---

## Tool Reference

### create_project(name, description)
Creates a project record in Postgres.

### create_environment(name, project_name)
Creates an environment under a project. Auto-generates namespace as `project-name-environment-name`.

### deploy_image_app(name, image, environment, replicas, ports)
In the target environment's namespace:
1. Creates a `Deployment` with the given image
2. Creates a `Service` (ClusterIP)
3. Stores records in `applications` and `k8s_resources` tables

### get_app_status(name, environment)
Returns pod status, restart counts, image, age.

### scale_app(name, environment, replicas)
Patches the Deployment `spec.replicas`.

### delete_app(name, environment)
Deletes Deployment + Service + DB records.

### set_env_var(app, environment, key, value)
Patches the Deployment env block. Stores in DB.

### set_resource_limits(app, environment, cpu, memory)
Patches the Deployment resources block.

---

## Definition of Done

```
You > create project webapp
🤖 Created project `webapp`. ID: prj-abc123.

You > create environment staging in webapp
🤖 Created environment `webapp-staging`. Namespace: webapp-staging.

You > deploy image nginx:latest to webapp-staging as frontend with 1 replica
🤖 Deployed `frontend` to webapp-staging.
   Pods: 1/1 running
   Image: nginx:latest
   Service: frontend (ClusterIP: 10.96.123.45:80)
   Access: kubectl port-forward -n webapp-staging svc/frontend 8080:80

You > scale frontend in webapp-staging to 3
🤖 Scaled to 3 replicas. 3/3 pods running.

You > set env var API_URL=https://api.dev.com for frontend in webapp-staging
🤖 Patched deployment. Rolling update in progress.

You > get status for frontend in webapp-staging
🤖 frontend in webapp-staging:
   Pods: 3/3 running (age: 2m)
   Restarts: 0
   Image: nginx:latest
   Service: frontend:80

You > delete app frontend in webapp-staging
🤖 Deleted frontend from webapp-staging.
```

---

## Files to Create
- `src/db/migrations/004_projects.sql`
- `src/db/migrations/005_applications.sql`
- `src/infrastructure/project_repo.py`
- `src/infrastructure/application_repo.py`
- `src/tools/k8s_deploy.py`

## Files to Modify
- `src/infrastructure/k8s_client.py` — add deployment/service helpers
- `src/tools/__init__.py` — export new tools
- `src/graph/nodes/agent.py` — update SYSTEM_PROMPT
- `src/mcp_server/server.py` — add MCP tools

---

*Next: Run `docker-compose build` after all files are in place.*
