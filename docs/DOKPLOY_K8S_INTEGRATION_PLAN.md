# DeployAI + Dokploy-K8s Integration Plan

## 1. Executive Summary

**Goal**: Port every Dokploy feature into DeployAI, replacing Docker Swarm with **Kubernetes** as the orchestration layer. The user interacts via natural language ("deploy my Next.js app from GitHub", "scale the API to 5 replicas", "backup the PostgreSQL database").

---

## 2. Architecture Decision: Swarm → Kubernetes Mapping

| Dokploy (Swarm) | Kubernetes Equivalent | Notes |
|-----------------|----------------------|-------|
| **Swarm Service** | `Deployment` (stateless), `StatefulSet` (stateful), `DaemonSet` (global) | Primary workload abstraction |
| **Docker Compose** | Helm charts or raw K8s manifests | Native K8s doesn't use Compose; Helm is the standard |
| **Docker Stack** | Kustomize or Helm | For multi-service definitions |
| **Traefik** | **Ingress Controller** (NGINX, Traefik, or Cilium) | Handles routing + SSL |
| **Docker Volumes** | `PersistentVolumeClaim` (PVC) + `PersistentVolume` (PV) | Storage abstraction |
| **Docker Configs** | `ConfigMap` | Non-sensitive config data |
| **Docker Secrets** | `Kubernetes Secret` | Sensitive data, base64-encoded |
| **Placement Constraints** | **Node Affinity**, **Taints & Tolerations**, **Topology Spread Constraints** | Control pod placement |
| **Resource Limits** | `resources.limits` / `resources.requests` in pod spec | Same concept, native in K8s |
| **Health Checks** | `livenessProbe`, `readinessProbe`, `startupProbe` | More granular than Swarm |
| **Rolling Updates** | `Deployment` rolling update strategy | Built-in, configurable |
| **Rollback** | `kubectl rollout undo` or Helm rollback | Native K8s capability |
| **Networks** | `Service` (ClusterIP, NodePort, LoadBalancer) | K8s networking model |
| **Multi-node** | Kubernetes cluster (managed or bare-metal) | EKS, GKE, AKS, k3s, etc. |
| **Swarm Replicas** | `spec.replicas` in Deployment | Direct equivalent |
| **Service Mode (replicated/global)** | Deployment vs DaemonSet | Same concept |

---

## 3. Complete Feature Matrix: Dokploy → DeployAI-K8s

### 3.1 Application Deployment

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 1 | Deploy from Git (GitHub/GitLab/Bitbucket/Gitea) | `GitRepo` + BuildKit/ Kaniko / Pod with init container | `deploy_from_git(repo, branch, build_type)` |
| 2 | Deploy from Docker image | Direct `Deployment` with image pull | `deploy_from_image(image, tag)` |
| 3 | Deploy from file drop | Init container with S3/HTTP download | `deploy_from_upload(file_url)` |
| 4 | **Nixpacks** build | BuildKit in K8s or external build server | `build_with_nixpacks(source)` |
| 5 | **Dockerfile** build | Kaniko / BuildKit in cluster | `build_with_dockerfile(dockerfile)` |
| 6 | **Heroku Buildpacks** | Pack + BuildKit | `build_with_buildpacks(source)` |
| 7 | **Railpack** build | Railpack + BuildKit | `build_with_railpack(source)` |
| 8 | **Static** sites | Nginx sidecar or dedicated static server | `deploy_static_site(source)` |
| 9 | Auto-deploy on git push | GitHub/GitLab webhook → trigger K8s rollout | `configure_autodeploy(app, branch)` |
| 10 | Preview deployments (PRs) | Temporary `Deployment` + `Ingress` | `deploy_preview(pr_number, branch)` |
| 11 | Build args & secrets | `--build-arg` via Kaniko, K8s Secrets for build | `set_build_args(app, args)` |
| 12 | Registry push | Push to configured registry (ECR, GCR, Docker Hub) | `push_to_registry(app, registry)` |
| 13 | Rollback | `kubectl rollout undo` or Helm history | `rollback_deployment(app, revision)` |
| 14 | Webhook deployments | HTTP endpoint triggers rollout | `trigger_webhook_deploy(app)` |
| 15 | Custom commands/args | `spec.containers[*].command` / `args` | `set_container_command(app, cmd)` |

**DeployAI Agent Capabilities**:
- "Deploy my Next.js app from GitHub repo `acme/webapp` on branch `main`"
- "Create a preview deployment for PR #42"
- "Rollback the API service to the previous version"
- "Set build argument `API_URL=https://api.prod.com` for the frontend"

---

### 3.2 Database Services

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 16 | **PostgreSQL** | `StatefulSet` + PVC + `Service` (ClusterIP) | `deploy_postgres(name, version, storage)` |
| 17 | **MySQL** | `StatefulSet` + PVC + `Service` | `deploy_mysql(name, version, storage)` |
| 18 | **MariaDB** | `StatefulSet` + PVC + `Service` | `deploy_mariadb(name, version, storage)` |
| 19 | **MongoDB** | `StatefulSet` + PVC + `Service` (replica set via operator) | `deploy_mongodb(name, version, replicas)` |
| 20 | **Redis** | `StatefulSet` or `Deployment` + PVC | `deploy_redis(name, version, password)` |
| 21 | **libSQL (Turso)** | Custom operator or sidecar pattern | `deploy_libsql(name, version)` |
| 22 | External port exposure | `Service` type `NodePort` or `LoadBalancer` | `expose_database_port(db_name, port)` |
| 23 | Custom Docker image | `StatefulSet` with custom `image` field | `deploy_custom_db(image, name)` |
| 24 | DB environment variables | `ConfigMap` + `Secret` injected into pod | `set_db_env(db_name, key, value)` |

**DeployAI Agent Capabilities**:
- "Create a PostgreSQL database named `orders-db` with 10GB storage"
- "Expose Redis on port 6379 externally"
- "Deploy MongoDB with a 3-node replica set"
- "Set the PostgreSQL password to `secure123`"

---

### 3.3 Backups

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 25 | Database backups | **CronJob** running `pg_dump` / `mysqldump` / `mongodump` → S3 | `schedule_db_backup(db, schedule, s3_dest)` |
| 26 | Backup scheduling | `CronJob` with cron expression | `set_backup_schedule(db, "0 2 * * *")` |
| 27 | Backup retention | Object lifecycle policy on S3 or cleanup CronJob | `set_backup_retention(db, keep_last=7)` |
| 28 | Backup restore | Job running `pg_restore` / `mysql` from S3 backup | `restore_db_from_backup(db, backup_name)` |
| 29 | S3 destinations | K8s Secret with S3 credentials, mounted into backup Job | `configure_backup_destination(name, s3_url)` |
| 30 | Volume backups | **Velero** or snapshot-based backup (CSI snapshots) | `backup_volume(pvc_name, schedule)` |

**DeployAI Agent Capabilities**:
- "Backup PostgreSQL every night at 2 AM to S3 bucket `my-backups`"
- "Restore the `orders-db` from yesterday's backup"
- "Keep only the last 7 backups"
- "Backup the persistent volume for the uploads service"

---

### 3.4 Networking, Domains & SSL

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 31 | Custom domains | `Ingress` resource with `host` rule | `add_domain(app, domain)` |
| 32 | Let's Encrypt SSL | **cert-manager** with `ClusterIssuer` (HTTP-01 or DNS-01) | `enable_ssl_letsencrypt(app, domain)` |
| 33 | Custom certificates | `tls` secret mounted in Ingress | `upload_custom_cert(app, cert, key)` |
| 34 | Wildcard domains | `Ingress` with `*.example.com` + cert-manager wildcard cert | `add_wildcard_domain(app, domain)` |
| 35 | HTTPS redirect | Ingress annotation `nginx.ingress.kubernetes.io/ssl-redirect` | `enable_https_redirect(app)` |
| 36 | URL redirects | `Ingress` + middleware or nginx `rewrite` annotations | `add_redirect(from, to)` |
| 37 | Port configuration | `Service` with multiple ports | `add_port_mapping(app, port, target_port)` |
| 38 | Rate limiting | Ingress annotation or middleware (Traefik/NGINX) | `enable_rate_limit(app, rps)` |
| 39 | IP allowlist/denylist | `NetworkPolicy` or Ingress annotation | `set_ip_allowlist(app, [ips])` |

**DeployAI Agent Capabilities**:
- "Map `api.example.com` to the API service with Let's Encrypt SSL"
- "Add a redirect from `www.example.com` to `example.com`"
- "Enable rate limiting of 100 requests per minute on the API"
- "Allow only office IPs `203.0.113.0/24` to access the admin panel"

---

### 3.5 Security

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 40 | Basic auth | Ingress annotation or sidecar nginx | `enable_basic_auth(app, username, password)` |
| 41 | Security headers | Ingress annotation or middleware | `add_security_headers(app, headers)` |
| 42 | Two-factor auth | DeployAI's own auth (not K8s) | `enable_2fa(user)` |
| 43 | API Keys | DeployAI API key management | `generate_api_key(name, permissions)` |
| 44 | RBAC | **Kubernetes RBAC** (`Role`, `RoleBinding`, `ServiceAccount`) | `grant_role(user, role, namespace)` |

**DeployAI Agent Capabilities**:
- "Enable basic auth on the staging environment"
- "Generate an API key for CI/CD deployments"
- "Grant user `alice` admin access to the `production` namespace"

---

### 3.6 Monitoring & Logging

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 45 | Container stats | **Metrics Server** + `kubectl top pod` or Prometheus | `get_container_stats(app)` |
| 46 | Server monitoring | **Prometheus Node Exporter** + Grafana | `get_server_metrics(server)` |
| 47 | Health checks | `livenessProbe`, `readinessProbe` in pod spec | `configure_health_checks(app, type, path)` |
| 48 | Deployment logs | `kubectl logs -f` via WebSocket | `stream_logs(app, lines=100)` |
| 49 | Log cleanup | **Loki** or Fluent Bit retention policies | `set_log_retention(app, days)` |
| 50 | Resource alerts | **Prometheus Alertmanager** rules | `set_alert_threshold(app, metric, threshold)` |

**DeployAI Agent Capabilities**:
- "Show me the logs for the API service, last 50 lines"
- "Stream logs for the worker pod in real time"
- "Set a CPU alert at 80% for the frontend deployment"
- "Check the health status of all pods in the `production` namespace"

---

### 3.7 Scaling & Resource Management

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 51 | Replica count | `spec.replicas` in Deployment | `scale_app(app, replicas)` |
| 52 | Horizontal scaling | **HPA** (Horizontal Pod Autoscaler) | `enable_hpa(app, min, max, metric)` |
| 53 | Resource limits | `resources.limits` / `resources.requests` | `set_resource_limits(app, cpu, memory)` |
| 54 | Resource reservations | `resources.requests` (guaranteed QoS) | `set_resource_requests(app, cpu, memory)` |
| 55 | Vertical scaling | **VPA** (Vertical Pod Autoscaler) | `enable_vpa(app)` |
| 56 | Node affinity | `affinity.nodeAffinity` | `set_node_affinity(app, labels)` |
| 57 | Pod anti-affinity | `affinity.podAntiAffinity` | `distribute_pods_across_nodes(app)` |

**DeployAI Agent Capabilities**:
- "Scale the API to 5 replicas"
- "Enable autoscaling from 2 to 10 replicas based on CPU at 70%"
- "Set memory limit to 512Mi for the worker service"
- "Ensure pods don't run on the same node"

---

### 3.8 Multi-Server / Multi-Cluster

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 58 | Remote server management | **K8s context switching** or federation | `add_cluster(name, kubeconfig)` |
| 59 | Deploy to external servers | Deploy to remote K8s cluster | `deploy_to_cluster(app, cluster)` |
| 60 | Build servers | **Tekton** or **Argo Workflows** for CI builds | `configure_build_pipeline(app)` |
| 61 | Cluster cleanup | CronJob for `kubectl delete` of unused resources | `run_cluster_cleanup(cluster)` |

**DeployAI Agent Capabilities**:
- "Add the production EKS cluster to my environment"
- "Deploy the API to the `us-west-2` cluster"
- "Run a cleanup of unused images and volumes"
- "Set up a build pipeline that builds on a dedicated node"

---

### 3.9 Storage & Mounts

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 62 | Volume mounts | `volumeMounts` + `volumes` in pod spec | `add_volume_mount(app, path, size)` |
| 63 | Bind mounts | `hostPath` volume (discouraged in K8s) | `add_host_path_mount(app, path)` |
| 64 | File mounts | `ConfigMap` or `Secret` as volume | `mount_config_file(app, config_name, path)` |
| 65 | Persistent storage | `PersistentVolumeClaim` | `create_pvc(name, size, storage_class)` |
| 66 | Shared storage | `ReadWriteMany` PVC (NFS, EFS, etc.) | `create_shared_volume(name, size)` |

**DeployAI Agent Capabilities**:
- "Mount a 10GB persistent volume at `/data` for the uploads service"
- "Mount the `app-config` ConfigMap at `/etc/app/config.yml`"
- "Create a shared volume for multiple pods to read/write"

---

### 3.10 Environment Management

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 67 | Environment variables | `env` / `envFrom` in pod spec + `ConfigMap`/`Secret` | `set_env_var(app, key, value)` |
| 68 | Environment separation | **K8s Namespaces** (`dev`, `staging`, `prod`) | `create_environment(name)` |
| 69 | Project tags | K8s labels on resources | `tag_resource(app, key, value)` |
| 70 | Secrets management | **External Secrets Operator** or Sealed Secrets | `create_secret(name, data)` |

**DeployAI Agent Capabilities**:
- "Create a `staging` namespace"
- "Set environment variable `DATABASE_URL` for the API service"
- "Create a secret named `api-keys` with the Stripe key"
- "Tag all resources in project `acme` with `team=backend`"

---

### 3.11 Notifications

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 71 | Slack notifications | **Alertmanager** webhook or custom operator | `add_slack_notification(webhook_url)` |
| 72 | Discord notifications | Alertmanager webhook | `add_discord_notification(webhook_url)` |
| 73 | Email notifications | Alertmanager email config | `add_email_notification(smtp, to)` |
| 74 | Telegram notifications | Alertmanager webhook | `add_telegram_notification(bot_token, chat_id)` |
| 75 | Custom webhooks | Generic Alertmanager webhook receiver | `add_webhook_notification(url, events)` |

**DeployAI Agent Capabilities**:
- "Send Slack notifications to `#deployments` on every deploy"
- "Email the team when a backup fails"
- "Call the PagerDuty webhook when CPU exceeds 90%"

---

### 3.12 AI-Powered Features (Dokploy + DeployAI Synergy)

| # | Dokploy Feature | K8s Enhancement | DeployAI Tool |
|---|----------------|----------------|---------------|
| 76 | Auto-generate docker-compose | Auto-generate K8s manifests / Helm charts from NL | `generate_k8s_manifests(description)` |
| 77 | AI deployment suggestions | AI recommends resource limits, replicas, health checks | `optimize_deployment(app)` |
| 78 | Multiple AI providers | Same as Dokploy (OpenAI, Anthropic, Ollama) | Configurable in DeployAI |

**DeployAI Agent Capabilities**:
- "Generate a Kubernetes manifest for a Node.js app with PostgreSQL"
- "Optimize the API deployment based on current traffic"
- "What's the best resource allocation for a 1000 RPS API?"

---

### 3.13 Templates & One-Click Deploys

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 79 | One-click templates | Helm chart repository or K8s manifest templates | `deploy_template(template_name, vars)` |
| 80 | Template variables | Helm `values.yaml` or Kustomize overlays | `set_template_var(key, value)` |

**DeployAI Agent Capabilities**:
- "Deploy the `wordpress` template with domain `blog.example.com`"
- "Deploy `redis-cluster` with 3 nodes"

---

### 3.14 Web Terminal & File Management

| # | Dokploy Feature | K8s Implementation | DeployAI Tool |
|---|----------------|-------------------|---------------|
| 81 | Web terminal | `kubectl exec -it` via WebSocket (like `kubeterm` or `ttyd`) | `open_terminal(pod_name)` |
| 82 | File browser | `kubectl cp` + web UI | `browse_files(pod_name, path)` |

---

## 4. Data Models (PostgreSQL Schema)

You'll need these tables in your `linux_server_manager` DB:

```sql
-- Projects
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Environments (dev/staging/prod)
CREATE TABLE environments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    name TEXT NOT NULL, -- 'dev', 'staging', 'prod'
    namespace TEXT NOT NULL, -- K8s namespace
    cluster_id UUID REFERENCES clusters(id)
);

-- Applications / Deployments
CREATE TABLE applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    environment_id UUID REFERENCES environments(id),
    app_type TEXT, -- 'web', 'api', 'worker', 'static'
    source_type TEXT, -- 'git', 'image', 'upload'
    source_url TEXT,
    build_type TEXT, -- 'nixpacks', 'dockerfile', 'buildpacks', 'railpack', 'static'
    image TEXT, -- final deployed image
    replicas INT DEFAULT 1,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Kubernetes Resources (tracks what was created)
CREATE TABLE k8s_resources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id UUID REFERENCES applications(id),
    resource_type TEXT, -- 'Deployment', 'Service', 'Ingress', 'ConfigMap', 'Secret', 'PVC'
    resource_name TEXT,
    namespace TEXT,
    manifest JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Domains
CREATE TABLE domains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id UUID REFERENCES applications(id),
    domain TEXT NOT NULL,
    ssl_enabled BOOLEAN DEFAULT FALSE,
    ssl_issuer TEXT, -- 'letsencrypt', 'custom'
    cert_secret_name TEXT,
    https_redirect BOOLEAN DEFAULT TRUE
);

-- Databases
CREATE TABLE databases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    db_type TEXT, -- 'postgres', 'mysql', 'mariadb', 'mongodb', 'redis', 'libsql'
    environment_id UUID REFERENCES environments(id),
    storage_size TEXT, -- '10Gi'
    version TEXT,
    external_port INT,
    status TEXT DEFAULT 'pending'
);

-- Backups
CREATE TABLE backups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type TEXT, -- 'database', 'volume', 'compose'
    target_id UUID,
    schedule TEXT, -- cron expression
    s3_destination TEXT,
    retention_count INT DEFAULT 7,
    last_run TIMESTAMPTZ,
    last_status TEXT
);

-- Clusters
CREATE TABLE clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    provider TEXT, -- 'eks', 'gke', 'aks', 'k3s', 'bare-metal'
    kubeconfig TEXT, -- encrypted kubeconfig
    endpoint TEXT,
    status TEXT DEFAULT 'active'
);

-- Notifications
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT, -- 'slack', 'discord', 'email', 'telegram', 'webhook'
    config JSONB, -- provider-specific config
    events TEXT[] -- ['deploy_success', 'deploy_failure', 'backup_failure']
);
```

---

## 5. DeployAI Agent Tools (Complete List)

The agent needs these tools to manage the full K8s lifecycle:

### Deployment Tools
| Tool | Purpose |
|------|---------|
| `deploy_git_app(name, repo, branch, env)` | Deploy from Git source |
| `deploy_image_app(name, image, env)` | Deploy from Docker image |
| `scale_app(name, replicas, env)` | Scale replicas |
| `rollback_app(name, revision, env)` | Rollback deployment |
| `delete_app(name, env)` | Delete application |
| `get_app_status(name, env)` | Check deployment status |
| `set_env_var(app, key, value, env)` | Set environment variable |
| `set_resource_limits(app, cpu, memory, env)` | Configure resources |

### Database Tools
| Tool | Purpose |
|------|---------|
| `deploy_database(name, db_type, size, env)` | Create database |
| `backup_database(name, dest, env)` | Trigger backup |
| `restore_database(name, backup_id, env)` | Restore from backup |
| `get_db_status(name, env)` | Check DB health |
| `expose_db_port(name, port, env)` | Expose external port |

### Networking Tools
| Tool | Purpose |
|------|---------|
| `add_domain(app, domain, env)` | Map custom domain |
| `enable_ssl(app, domain, issuer, env)` | Enable SSL |
| `add_ingress_rule(app, path, port, env)` | Add ingress route |
| `add_redirect(from, to, env)` | URL redirect |

### Storage Tools
| Tool | Purpose |
|------|---------|
| `create_pvc(name, size, storage_class, env)` | Create persistent volume |
| `mount_volume(app, pvc_name, path, env)` | Mount volume to app |
| `create_configmap(name, data, env)` | Create ConfigMap |
| `create_secret(name, data, env)` | Create Secret |

### Cluster Tools
| Tool | Purpose |
|------|---------|
| `add_cluster(name, kubeconfig)` | Register K8s cluster |
| `get_cluster_status(name)` | Cluster health |
| `run_cleanup(cluster)` | Clean unused resources |
| `get_pod_logs(app, lines, env)` | Fetch logs |

### Notification Tools
| Tool | Purpose |
|------|---------|
| `add_notification(provider, config, events)` | Configure alerts |
| `test_notification(provider)` | Test channel |

---

## 6. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          User / CLI / Web UI                             │
│         "Deploy my Next.js app from GitHub to production"                │
└────────────────────────────┬────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         DeployAI Agent (Python)                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────────┐  │
│  │  Planner   │→ │  Executor  │⇄ │   Tools    │→ │    Reviewer      │  │
│  │            │  │            │  │            │  │                  │  │
│  │ "This user │  │ "I'll call │  │ deploy_    │  │ "Deployment      │  │
│  │  wants to  │  │  the K8s   │  │ git_app()  │  │  succeeded,     │  │
│  │  deploy..."│  │  tools"    │  │ scale_app()│  │  here's the URL"│  │
│  └────────────┘  └────────────┘  │ add_domain()│  └──────────────────┘  │
│                                   │ enable_ssl()│                        │
│                                   └──────┬─────┘                        │
│                                          │                              │
└──────────────────────────────────────────┼──────────────────────────────┘
                                           │
              ┌────────────────────────────┼────────────────────────────┐
              ▼                            ▼                            ▼
       ┌──────────────┐          ┌─────────────────┐          ┌─────────────┐
       │ PostgreSQL   │          │  kubectl /      │          │  Helm /     │
       │ (Inventory   │          │  K8s API        │          │  Kustomize  │
       │  + Queue)    │          │                 │          │             │
       └──────────────┘          └────────┬────────┘          └─────────────┘
                                          │
                         ┌────────────────┼────────────────┐
                         ▼                ▼                ▼
                  ┌──────────┐    ┌──────────┐     ┌──────────┐
                  │ Ingress  │    │  Pods    │     │  PVCs    │
                  │ (NGINX/  │    │(Workloads│     │(Storage) │
                  │ Traefik) │    └──────────┘     └──────────┘
                  └──────────┘
```

---

## 7. Implementation Phases (Summary)

| Phase | Name | Duration | Key Deliverable |
|-------|------|----------|-----------------|
| 0 | Foundation | 1-2 days | Agent connects to K8s cluster |
| 1 | Core Deployment | 3-4 days | Deploy image, scale, check status |
| 2 | Git Builds | 4-5 days | Deploy from GitHub with auto-build |
| 3 | Networking & SSL | 3-4 days | Custom domain + Let's Encrypt HTTPS |
| 4 | Databases | 3-4 days | PostgreSQL + nightly S3 backups |
| 5 | Storage | 2-3 days | PVCs, ConfigMaps, Secrets |
| 6 | Monitoring | 3-4 days | Logs, metrics, health checks |
| 7 | Notifications | 2 days | Slack/Discord alerts |
| 8 | Multi-Cluster | 3-4 days | HPA, multi-cluster deploy |
| 9 | Templates | 2-3 days | One-click WordPress, Redis, etc. |
| 10 | Terminal | 2-3 days | Shell into pods, browse files |
| 11 | AI Optimization | 2-3 days | Auto-tune, diagnose failures |
| 12 | Polish & QA | 3-4 days | Tests, docs, audit, cleanup |

**Total: ~37-46 engineering days** (~20-25 calendar days with parallel tracks)

---

*End of plan. See `IMPLEMENTATION_ROADMAP.md` for detailed phase-by-phase deliverables.*
