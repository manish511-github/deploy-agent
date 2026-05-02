# DeployAI + Dokploy-K8s Implementation Roadmap

## Document Control
- **Version**: 1.0
- **Updated**: 2026-04-30
- **Status**: Planning
- **Branch**: `dev`
- **Next Review**: After Phase 1 completion

---

## Phase 0: Foundation & Tooling Setup
**Timeline**: 1-2 days  
**Goal**: Agent can talk to a Kubernetes cluster. Nothing deploys yet — just connectivity and discovery.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 0.1 | Add `kubernetes` Python SDK to dependencies | `pyproject.toml` | `pip install -e .` succeeds, `kubectl` works inside Docker |
| 0.2 | Create K8s client wrapper | `src/infrastructure/k8s_client.py` | Can `list_namespaces()`, `get_nodes()`, `get_pods()` against a cluster |
| 0.3 | Mount kubeconfig into Docker | `docker-compose.yml` | Agent container can reach the K8s API server |
| 0.4 | Add cluster registry table | `src/db/migrations/003_clusters.sql` | Can store cluster name + encrypted kubeconfig |
| 0.5 | Create cluster repository | `src/infrastructure/cluster_repo.py` | CRUD for clusters (list, add, delete, get kubeconfig) |
| 0.6 | Add `add_cluster` tool | `src/tools/k8s_cluster.py` | Agent command: "add cluster production with kubeconfig ~/.kube/config" |
| 0.7 | Add `get_cluster_status` tool | `src/tools/k8s_cluster.py` | Returns: node count, total CPU, total memory per cluster |
| 0.8 | Update agent prompt | `src/graph/nodes/agent.py` | SYSTEM_PROMPT lists K8s capabilities |

### Definition of Done
```
You > list my clusters
🤖 You have 1 cluster: production (3 nodes, 6 vCPU, 12GB RAM)

You > check cluster health
🤖 All 3 nodes Ready. No pressure alerts.
```

---

## Phase 1: Core Application Deployment
**Timeline**: 3-4 days  
**Goal**: Deploy a containerized app from an image to Kubernetes. No Ingress, no SSL — just `kubectl port-forward` or `NodePort` access.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 1.1 | Create project registry table | `src/db/migrations/004_projects.sql` | `projects`, `environments` tables |
| 1.2 | Create project repository | `src/infrastructure/project_repo.py` | CRUD for projects & environments |
| 1.3 | Create application registry table | `src/db/migrations/005_applications.sql` | `applications`, `k8s_resources` tables |
| 1.4 | Create application repository | `src/infrastructure/application_repo.py` | CRUD for applications |
| 1.5 | Add `create_project` tool | `src/tools/k8s_deploy.py` | "create project myapp" → DB entry + K8s namespace |
| 1.6 | Add `create_environment` tool | `src/tools/k8s_deploy.py` | "create environment staging in project myapp" → namespace `myapp-staging` |
| 1.7 | Add `deploy_image_app` tool | `src/tools/k8s_deploy.py` | "deploy nginx image to myapp-staging" → Deployment + Service |
| 1.8 | Add `get_app_status` tool | `src/tools/k8s_deploy.py` | Returns: pods running, restarts, image, age |
| 1.9 | Add `scale_app` tool | `src/tools/k8s_deploy.py` | "scale myapp-staging to 3 replicas" |
| 1.10 | Add `delete_app` tool | `src/tools/k8s_deploy.py` | Deletes Deployment + Service + DB record |
| 1.11 | Add `set_env_var` tool | `src/tools/k8s_deploy.py` | Patches Deployment env; stores in DB |
| 1.12 | Add `set_resource_limits` tool | `src/tools/k8s_deploy.py` | Sets CPU/memory limits & requests |
| 1.13 | K8s resource tracking | `src/infrastructure/k8s_client.py` | Every created resource is recorded in `k8s_resources` table |
| 1.14 | DeployAI graph update | `src/graph/graph.py` | Router correctly routes deployment intent to planner → executor |

### Definition of Done
```
You > create project webapp
🤖 Created project `webapp`. ID: prj-abc123.

You > create environment staging in webapp
🤖 Created environment `webapp-staging`. Namespace: webapp-staging.

You > deploy image nginx:latest to webapp-staging as frontend
🤖 Deployed `frontend` to webapp-staging.
   Pods: 1/1 running
   Image: nginx:latest
   Access: kubectl port-forward -n webapp-staging svc/frontend 8080:80

You > scale frontend in webapp-staging to 3
🤖 Scaled to 3 replicas. All 3 pods running.

You > set env var API_URL=https://api.dev.com for frontend in webapp-staging
🤖 Patched deployment. Rolling update in progress.
```

---

## Phase 2: Git Source & Build Pipeline
**Timeline**: 4-5 days  
**Goal**: Deploy from Git (GitHub/GitLab/Bitbucket) with automatic builds.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 2.1 | Add Git provider registry tables | `src/db/migrations/006_git_providers.sql` | `git_providers` table linking to GitHub/GitLab apps |
| 2.2 | Add `configure_git_provider` tool | `src/tools/k8s_git.py` | OAuth or PAT-based connection to GitHub/GitLab |
| 2.3 | Add `deploy_git_app` tool | `src/tools/k8s_deploy.py` | Clones repo, detects Dockerfile or uses Nixpacks |
| 2.4 | Integrate BuildKit/Kaniko | `src/infrastructure/builder.py` | Runs builds as Kubernetes Jobs; pushes to registry |
| 2.5 | Add registry support | `src/db/migrations/007_registries.sql` | `registries` table (Docker Hub, GHCR, ECR, GCR) |
| 2.6 | Add `push_to_registry` tool | `src/tools/k8s_deploy.py` | Tags and pushes built image |
| 2.7 | Add `configure_autodeploy` tool | `src/tools/k8s_deploy.py` | Webhook endpoint that triggers rollout on git push |
| 2.8 | Add `deploy_preview` tool | `src/tools/k8s_deploy.py` | Temporary Deployment for PRs |
| 2.9 | Add `rollback_deployment` tool | `src/tools/k8s_deploy.py` | `kubectl rollout undo` or Helm history rollback |
| 2.10 | Deployment logs streaming | `src/infrastructure/k8s_client.py` | WebSocket or chunked HTTP for `kubectl logs -f` |
| 2.11 | Webhook receiver endpoint | `src/api/webhooks.py` | FastAPI endpoint for GitHub/GitLab webhooks |

### Definition of Done
```
You > connect GitHub to project webapp
🤖 GitHub connected. Repositories available: acme/webapp, acme/api.

You > deploy from GitHub repo acme/webapp branch main to webapp-staging
🤖 Cloning acme/webapp@main...
   Detected: Dockerfile
   Building with BuildKit... (Job build-abc12 running)
   Build complete. Image: ghcr.io/acme/webapp:main-abc12
   Deployed to webapp-staging.

You > enable autodeploy for frontend on main branch
🤖 Webhook configured: https://deployai.example.com/webhooks/github/webapp
```

---

## Phase 3: Networking, Domains & SSL
**Timeline**: 3-4 days  
**Goal**: Custom domains + SSL on any deployed app.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 3.1 | Install cert-manager support | `src/infrastructure/k8s_client.py` | Can detect if cert-manager is installed; install if missing |
| 3.2 | Add domain registry table | `src/db/migrations/008_domains.sql` | `domains` table |
| 3.3 | Add `add_domain` tool | `src/tools/k8s_networking.py` | Creates `Ingress` resource with `host` rule |
| 3.4 | Add `enable_ssl_letsencrypt` tool | `src/tools/k8s_networking.py` | Creates `Certificate` or Ingress with cert-manager annotations |
| 3.5 | Add `upload_custom_cert` tool | `src/tools/k8s_networking.py` | Creates `tls` Secret and attaches to Ingress |
| 3.6 | Add `add_redirect` tool | `src/tools/k8s_networking.py` | Ingress annotation or middleware for URL rewriting |
| 3.7 | Add `enable_https_redirect` tool | `src/tools/k8s_networking.py` | Ingress annotation `ssl-redirect` |
| 3.8 | Add `add_port_mapping` tool | `src/tools/k8s_networking.py` | Adds additional ports to Service |
| 3.9 | Add `enable_rate_limit` tool | `src/tools/k8s_networking.py` | Ingress annotation for rate limiting |
| 3.10 | Add `set_ip_allowlist` tool | `src/tools/k8s_networking.py` | `NetworkPolicy` or Ingress whitelist |
| 3.11 | Add `add_wildcard_domain` tool | `src/tools/k8s_networking.py` | Wildcard Ingress + cert-manager wildcard cert |
| 3.12 | Add `enable_basic_auth` tool | `src/tools/k8s_security.py` | Ingress basic auth via Secret |

### Definition of Done
```
You > add domain api.example.com to frontend in webapp-staging
🤖 Domain `api.example.com` mapped to frontend.
   DNS: Point A record to <ingress-ip>

You > enable SSL for api.example.com
🤖 Let's Encrypt certificate requested.
   Certificate issued. HTTPS active.

You > add redirect from www.example.com to example.com
🤖 Redirect configured. All www traffic goes to root domain.
```

---

## Phase 4: Database Services
**Timeline**: 3-4 days  
**Goal**: Deploy and manage databases on Kubernetes.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 4.1 | Add database registry tables | `src/db/migrations/009_databases.sql` | `databases` table |
| 4.2 | Add `deploy_postgres` tool | `src/tools/k8s_database.py` | StatefulSet + PVC + Service; stores creds in Secret |
| 4.3 | Add `deploy_mysql` tool | `src/tools/k8s_database.py` | Same pattern |
| 4.4 | Add `deploy_mariadb` tool | `src/tools/k8s_database.py` | Same pattern |
| 4.5 | Add `deploy_mongodb` tool | `src/tools/k8s_database.py` | StatefulSet with replica init |
| 4.6 | Add `deploy_redis` tool | `src/tools/k8s_database.py` | StatefulSet + PVC |
| 4.7 | Add `deploy_libsql` tool | `src/tools/k8s_database.py` | Sidecar or operator deployment |
| 4.8 | Add `expose_database_port` tool | `src/tools/k8s_database.py` | Creates NodePort or LoadBalancer Service |
| 4.9 | Add `set_db_env` tool | `src/tools/k8s_database.py` | Injects DB credentials into app as env vars |
| 4.10 | Database backup CronJobs | `src/tools/k8s_database.py` | CronJob running pg_dump / mysqldump |
| 4.11 | Backup destination support | `src/infrastructure/backup.py` | S3 upload via boto3 |
| 4.12 | Add `schedule_db_backup` tool | `src/tools/k8s_database.py` | Creates CronJob with schedule |
| 4.13 | Add `restore_db_from_backup` tool | `src/tools/k8s_database.py` | Runs restore Job from S3 backup |

### Definition of Done
```
You > create postgres named orders-db in webapp-staging with 10GB storage
🤖 PostgreSQL `orders-db` deployed.
   Host: orders-db.webapp-staging.svc.cluster.local
   Port: 5432
   User: postgres
   Password: <auto-generated, stored in Secret>

You > backup orders-db every night at 2am to s3://my-backups
🤖 Backup CronJob created. Schedule: 0 2 * * *.

You > connect orders-db to frontend app
🤖 Injected DATABASE_URL into frontend env.
```

---

## Phase 5: Storage & Configuration
**Timeline**: 2-3 days  
**Goal**: Persistent volumes, ConfigMaps, and Secrets.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 5.1 | Add `create_pvc` tool | `src/tools/k8s_storage.py` | Creates PersistentVolumeClaim |
| 5.2 | Add `mount_volume` tool | `src/tools/k8s_storage.py` | Patches Deployment with volumeMount + volume |
| 5.3 | Add `create_configmap` tool | `src/tools/k8s_storage.py` | Creates ConfigMap from key-value pairs or file |
| 5.4 | Add `mount_config_file` tool | `src/tools/k8s_storage.py` | Mounts ConfigMap as file in pod |
| 5.5 | Add `create_secret` tool | `src/tools/k8s_storage.py` | Creates K8s Secret from key-value pairs |
| 5.6 | Add `mount_secret` tool | `src/tools/k8s_storage.py` | Mounts Secret as env var or file |
| 5.7 | Add `create_shared_volume` tool | `src/tools/k8s_storage.py` | RWX PVC for multi-pod access |
| 5.8 | Storage class awareness | `src/infrastructure/k8s_client.py` | Lists available storage classes; user selects |

### Definition of Done
```
You > create a 5GB volume named uploads-data in webapp-staging
🤖 PVC `uploads-data` (5Gi) created in webapp-staging.

You > mount uploads-data to /app/uploads for frontend
🤖 Volume mounted. Pod rolling update in progress.

You > create secret stripe-key with value sk_live_xxx in webapp-staging
🤖 Secret `stripe-key` created. Available as env var in frontend.
```

---

## Phase 6: Monitoring, Logging & Alerts
**Timeline**: 3-4 days  
**Goal**: Observe what's happening across all deployments.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 6.1 | Add `get_pod_logs` tool | `src/tools/k8s_monitoring.py` | Returns last N lines of logs for app |
| 6.2 | Add `stream_logs` tool | `src/tools/k8s_monitoring.py` | Real-time WebSocket or chunked HTTP log stream |
| 6.3 | Add `get_container_stats` tool | `src/tools/k8s_monitoring.py` | CPU, memory, restarts per pod |
| 6.4 | Add `get_server_metrics` tool | `src/tools/k8s_monitoring.py` | Node-level CPU, memory, disk via Metrics Server |
| 6.5 | Add `configure_health_checks` tool | `src/tools/k8s_monitoring.py` | Sets livenessProbe, readinessProbe |
| 6.6 | Add `set_alert_threshold` tool | `src/tools/k8s_monitoring.py` | Stores thresholds in DB; checks periodically |
| 6.7 | Add `set_log_retention` tool | `src/tools/k8s_monitoring.py` | Configures log rotation / cleanup |
| 6.8 | Metrics collection CronJob | `src/infrastructure/metrics.py` | Scrapes metrics periodically, stores in DB |

### Definition of Done
```
You > show logs for frontend in webapp-staging, last 50 lines
🤖 [logs here]

You > stream logs for worker in webapp-staging
🤖 Streaming... (live updates)

You > check cpu and memory for frontend
🤖 Pod frontend-7d9f4b8c5-x2abc:
   CPU: 45m / 500m (limit)
   Memory: 128Mi / 512Mi (limit)

You > set cpu alert at 80% for frontend
🤖 Alert configured. Will notify when CPU > 80% for 5 minutes.
```

---

## Phase 7: Notifications
**Timeline**: 2 days  
**Goal**: Alert team when deployments happen or break.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 7.1 | Add notification registry table | `src/db/migrations/010_notifications.sql` | `notifications` table |
| 7.2 | Add `add_slack_notification` tool | `src/tools/k8s_notification.py` | Stores webhook URL; sends test message |
| 7.3 | Add `add_discord_notification` tool | `src/tools/k8s_notification.py` | Same pattern |
| 7.4 | Add `add_email_notification` tool | `src/tools/k8s_notification.py` | SMTP config; sends test email |
| 7.5 | Add `add_telegram_notification` tool | `src/tools/k8s_notification.py` | Bot token + chat ID |
| 7.6 | Add `add_webhook_notification` tool | `src/tools/k8s_notification.py` | Generic POST webhook |
| 7.7 | Add `test_notification` tool | `src/tools/k8s_notification.py` | Sends test message to configured channel |
| 7.8 | Notification dispatcher | `src/infrastructure/notifications.py` | Fires notifications on deploy/backup/alert events |
| 7.9 | Event hooks | `src/infrastructure/notifications.py` | Wires dispatch into deploy, backup, alert flows |

### Definition of Done
```
You > add Slack notification to #deployments for project webapp
🤖 Slack webhook configured. Testing... ✓ Message sent.

You > notify me on Discord when a deployment fails
🤖 Discord notification active for: deploy_failure.
```

---

## Phase 8: Multi-Cluster & Advanced Operations
**Timeline**: 3-4 days  
**Goal**: Manage multiple Kubernetes clusters from a single DeployAI instance.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 8.1 | Cluster switching in K8s client | `src/infrastructure/k8s_client.py` | All tools accept `cluster` param; defaults to first/active |
| 8.2 | Add `deploy_to_cluster` tool | `src/tools/k8s_cluster.py` | Deploys to specific cluster by name |
| 8.3 | Add `set_active_cluster` tool | `src/tools/k8s_cluster.py` | Changes default cluster for subsequent commands |
| 8.4 | Add `run_cluster_cleanup` tool | `src/tools/k8s_cluster.py` | Deletes unused pods, images, completed Jobs |
| 8.5 | Add `enable_hpa` tool | `src/tools/k8s_deploy.py` | Creates HorizontalPodAutoscaler |
| 8.6 | Add `enable_vpa` tool | `src/tools/k8s_deploy.py` | Creates VerticalPodAutoscaler |
| 8.7 | Add `set_node_affinity` tool | `src/tools/k8s_deploy.py` | Adds nodeSelector / affinity to Deployment |
| 8.8 | Add `distribute_pods_across_nodes` tool | `src/tools/k8s_deploy.py` | Adds podAntiAffinity |
| 8.9 | Add `configure_build_pipeline` tool | `src/tools/k8s_cluster.py` | Argo Workflows or Tekton pipeline setup |
| 8.10 | Cross-cluster deployment tracking | `src/infrastructure/application_repo.py` | Tracks which cluster each app lives on |

### Definition of Done
```
You > add cluster production-eks in us-east-1
🤖 Cluster `production-eks` added. 5 nodes, 20 vCPU, 40GB RAM.

You > deploy image nginx:latest to webapp-prod on cluster production-eks
🤖 Deployed to production-eks in namespace webapp-prod.

You > enable autoscaling for frontend in webapp-prod, min 2 max 10
🤖 HPA created. Scales on CPU > 70%.

You > run cleanup on cluster production-eks
🤖 Removed 12 unused images, 3 completed Jobs, 2 evicted pods.
```

---

## Phase 9: Templates & One-Click Deploys
**Timeline**: 2-3 days  
**Goal**: Deploy complex stacks with a single sentence.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 9.1 | Add template registry tables | `src/db/migrations/011_templates.sql` | `templates` table with JSON manifest |
| 9.2 | Create built-in templates | `src/templates/` | WordPress, Redis Cluster, PostgreSQL + PgAdmin, LAMP, MEAN |
| 9.3 | Add `deploy_template` tool | `src/tools/k8s_templates.py` | Deploys template by name with variable substitution |
| 9.4 | Add `list_templates` tool | `src/tools/k8s_templates.py` | Shows available templates |
| 9.5 | AI manifest generation | `src/tools/k8s_templates.py` | LLM generates YAML manifests from natural language description |
| 9.6 | Add `generate_k8s_manifests` tool | `src/tools/k8s_templates.py` | Creates raw YAML or Helm chart skeleton |
| 9.7 | Variable substitution engine | `src/infrastructure/templates.py` | Handles ${domain}, ${password}, ${randomPort}, etc. |
| 9.8 | Helm chart support | `src/infrastructure/helm_client.py` | Install/upgrade/uninstall Helm charts |
| 9.9 | Add `install_helm_chart` tool | `src/tools/k8s_templates.py` | "install helm bitnami/wordpress in webapp-staging" |

### Definition of Done
```
You > list templates
🤖 Available templates:
   1. wordpress (WordPress + MySQL)
   2. redis-cluster (3-node Redis cluster)
   3. postgres-pgadmin (PostgreSQL + PgAdmin)

You > deploy template wordpress with domain blog.example.com to webapp-staging
🤖 Deployed WordPress stack:
   WordPress: https://blog.example.com
   Database: wordpress-db (MySQL)
   Admin: https://blog.example.com/wp-admin

You > generate manifests for a Node.js API with Redis cache
🤖 Generated:
   - deployment.yaml (Node.js app, 2 replicas)
   - service.yaml (ClusterIP)
   - redis-statefulset.yaml
   - ingress.yaml
```

---

## Phase 10: Web Terminal & File Management
**Timeline**: 2-3 days  
**Goal**: Shell into pods and browse files from the chat interface.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 10.1 | WebSocket terminal backend | `src/api/terminal.py` | WebSocket endpoint wrapping `kubectl exec -it` |
| 10.2 | Add `open_terminal` tool | `src/tools/k8s_terminal.py` | Returns WebSocket URL for pod |
| 10.3 | File browser backend | `src/api/files.py` | REST API for `kubectl cp` + `ls` |
| 10.4 | Add `browse_files` tool | `src/tools/k8s_terminal.py` | Lists files in pod at path |
| 10.5 | Add `download_file` tool | `src/tools/k8s_terminal.py` | Downloads file from pod |
| 10.6 | Add `upload_file` tool | `src/tools/k8s_terminal.py` | Uploads file to pod |

### Definition of Done
```
You > open terminal for frontend pod in webapp-staging
🤖 Terminal available at ws://deployai.example.com/terminal/frontend-abc

You > list files in /app for frontend
🤖 /app:
   - main.py
   - requirements.txt
   - static/

You > download /app/main.py from frontend
🤖 Download started: main.py (download link)
```

---

## Phase 11: AI-Powered Optimization
**Timeline**: 2-3 days  
**Goal**: Let the AI recommend and apply optimal configurations.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 11.1 | Add `optimize_deployment` tool | `src/tools/k8s_ai.py` | LLM analyzes current metrics, suggests resource tuning |
| 11.2 | Add `diagnose_failure` tool | `src/tools/k8s_ai.py` | LLM reads pod events + logs, suggests fix |
| 11.3 | Add `generate_health_check` tool | `src/tools/k8s_ai.py` | Auto-generates liveness/readiness probes |
| 11.4 | Historical metrics analysis | `src/infrastructure/metrics.py` | Feeds past 7 days of metrics into LLM context |
| 11.5 | Cost estimation | `src/tools/k8s_ai.py` | Estimates monthly cost based on current usage |

### Definition of Done
```
You > optimize frontend in webapp-staging
🤖 Analysis:
   Current: 2x 500m CPU / 512Mi memory
   Traffic: Peak 50 RPS, average 5 RPS
   Recommendation: 200m CPU / 256Mi memory, scale 1-3 via HPA
   Apply? (y/n)

You > why is frontend crashing?
🤖 Diagnosis:
   Last crash: OOMKilled at 2026-04-30 14:23
   Memory usage: 512Mi / 512Mi limit
   Recommendation: Increase memory limit to 1Gi
   Apply? (y/n)
```

---

## Phase 12: Polish, Testing & Documentation
**Timeline**: 3-4 days  
**Goal**: Ship-ready with tests, docs, and stability.

### Deliverables
| # | Task | File(s) | Acceptance Criteria |
|---|------|---------|---------------------|
| 12.1 | Integration tests | `tests/test_k8s_*.py` | pytest suite for every tool |
| 12.2 | End-to-end tests | `tests/e2e/` | Full deploy → scale → delete cycle via CLI |
| 12.3 | Error handling | All tool files | Every K8s API error has user-friendly message |
| 12.4 | Retry logic | `src/infrastructure/k8s_client.py` | Exponential backoff on transient K8s errors |
| 12.5 | Audit logging | `src/infrastructure/audit.py` | Every deploy/scale/delete logged to DB |
| 12.6 | Performance limits | `src/core/config.py` | Max replicas, max resource limits enforced |
| 12.7 | Documentation | `docs/` | README, API docs, troubleshooting guide |
| 12.8 | Cleanup orphaned resources | CronJob or scheduled task | Deletes failed pods, exited Jobs older than 7 days |
| 12.9 | Security audit | N/A | No hardcoded secrets; all via K8s Secrets |
| 12.10 | CLI completions | `src/cli/app.py` | Shell completions for bash/zsh |

### Definition of Done
```
# Full acceptance test — run by CI

deploy-ai run "create project e2e-test"
deploy-ai run "create environment prod in e2e-test"
deploy-ai run "deploy image nginx:latest to e2e-test-prod as hello"
deploy-ai run "scale hello in e2e-test-prod to 3"
deploy-ai run "add domain hello.example.com to hello in e2e-test-prod"
deploy-ai run "enable SSL for hello.example.com"
deploy-ai run "check status of hello in e2e-test-prod"
deploy-ai run "delete app hello in e2e-test-prod"
```

---

## Rollout Strategy

### Parallel Tracks
- **Track A (Backend)**: Phases 0-2, 4, 5 — core deployment, databases, storage
- **Track B (Networking)**: Phase 3 — can run in parallel with Track A
- **Track C (Observability)**: Phases 6-7 — depends on Track A
- **Track D (Advanced)**: Phases 8-11 — depends on Track A + B + C
- **Track E (QA)**: Phase 12 — runs continuously throughout, gates releases

### Branching Strategy
- `main` — stable
- `dev` — integration branch
- `feature/phase-{N}` — per-phase feature branches
- `hotfix/*` — emergency fixes

### Release Gates
| Gate | Criteria |
|------|----------|
| Phase 1 gate | `pytest tests/test_k8s_deploy.py` passes |
| Phase 3 gate | Manual SSL cert issuance confirmed |
| Phase 6 gate | 95%+ log coverage; no missing pod crash events |
| Phase 12 gate | Full e2e test passes; security audit clean |

---

## Appendix A: Database Migration Order

Run migrations in this exact sequence:

1. `003_clusters.sql` — Phase 0
2. `004_projects.sql` — Phase 1
3. `005_applications.sql` — Phase 1
4. `006_git_providers.sql` — Phase 2
5. `007_registries.sql` — Phase 2
6. `008_domains.sql` — Phase 3
7. `009_databases.sql` — Phase 4
8. `010_notifications.sql` — Phase 7
9. `011_templates.sql` — Phase 9

---

## Appendix B: Phase Complexity Estimates

| Phase | Story Points | Risk Level | Blockers |
|-------|-------------|------------|----------|
| 0 | 5 | Low | None |
| 1 | 13 | Medium | K8s cluster availability |
| 2 | 21 | High | BuildKit reliability |
| 3 | 13 | Medium | cert-manager DNS propagation |
| 4 | 13 | Medium | StatefulSet Pod startup order |
| 5 | 8 | Low | PVC provisioning delays |
| 6 | 13 | Medium | Metrics Server availability |
| 7 | 5 | Low | Webhook URL validation |
| 8 | 13 | High | Multi-cluster auth complexity |
| 9 | 13 | Medium | LLM manifest quality |
| 10 | 8 | Medium | WebSocket reliability |
| 11 | 8 | Low | LLM context limits |
| 12 | 21 | Low | Scope creep |
| **Total** | **154** | | |

---

*End of roadmap. Start with Phase 0.*
