# Educational Platform API — Курсы, студенты и зачисления

Вариант 8 («Курсы и студенты»). Проект прошёл семь лабораторных работ:

| Лаб. | Что сделано | Где описано |
|------|-------------|-------------|
| №1–2 | REST API на FastAPI, SQLAlchemy, кэш и rate limiting в Redis, Celery-задача генерации сертификатов, админ-панель | [docs/LAB1-2.md](docs/LAB1-2.md) (эндпоинты, модель данных, примеры запросов) |
| №3 | PostgreSQL, RabbitMQ, Kubernetes (Minikube), Helm umbrella-чарт, KEDA, CloudNativePG, Argo CD, Image Updater, GitHub Actions | разделы «Kubernetes» … «CI» ниже |
| №4 | Наблюдаемость и S3: Prometheus, Grafana, Alertmanager, Loki, Alloy, Flower, SeaweedFS (S3 API) | раздел «Лабораторная № 4» ниже |
| №5 | Безопасность: JWT и роли, защита от BOLA, Vault, NetworkPolicy, Pod Security, TLS (cert-manager), Kyverno, Falco, Trivy | раздел «Лабораторная № 5» ниже |
| №6 | MVP-фронтенд на Vue 3: вход по JWT, главный экран со списком курсов, маршрутизация | раздел «Лабораторная № 6» ниже и `frontend-app/README.md` |
| **№7** | **Компоненты фронтенда: UI-кит, composables, CRUD курсов, toast-уведомления** | раздел «Лабораторная № 7» ниже и `frontend-app/README.md` |

## Архитектура

```
                     ┌────────────────────────── namespace fastapi-app ──────────────────────────┐
 клиент ─► Ingress ─►│ Service fastapi-service :80 ─► Deployment fastapi (2 пода, :8000)          │
 (fastapi.local)     │                                   │ /health  /ready                        │
                     │            ┌──────────────────────┼───────────────┐                        │
                     │            ▼                      ▼               ▼                        │
                     │   PostgreSQL :5432          Redis :6379     RabbitMQ :5672 (UI :15672)     │
                     │   StatefulSet+PVC           кэш, rate        очередь "celery"              │
                     │   (или CNPG: 3 инстанса)    limit, результаты    │                         │
                     │            ▲                задач Celery         ▼                         │
                     │            └──── Job db-migrate    Deployment celery-worker ◄── KEDA       │
                     │                  (alembic)         (PDF-сертификаты)          (ScaledObject)│
                     └─────────────────────────────────────────────────────────────────────────────┘
                     GitHub Actions: тесты → образы в GHCR → Argo CD (Git → кластер) ← Image Updater

   Лаб. № 4 — наблюдаемость и S3
   ┌─ fastapi-app ───────────────────────┐        ┌──────────────── namespace monitoring ─────────────────┐
   │ API ──/metrics──┐   Flower ─/metrics┤ scrape │ Prometheus ◄── ServiceMonitor'ы ──► Alertmanager      │
   │ Celery-воркер ──┼─► (события RabbitMQ)│ ─────► │     │ (правила: HighErrorRate, HighLatency, ...)      │
   │ stdout всех подов ──────────────────┼─ logs ─► Alloy ─► Loki ─┐                                       │
   │ API/воркер ──S3 API :8333──► SeaweedFS (master+volume+filer+s3, бакет fastapi-files)                  │
   └─────────────────────────────────────┘        │ Grafana ◄── Prometheus + Loki (дашборды из Git)  ◄──────┘
                                                  └───────────────────────────────────────────────────────┘
```

| Компонент | Порт | Роль |
|-----------|------|------|
| API (FastAPI) | 8000 (Service: 80) | REST API, Swagger `/docs`, пробы `/health` и `/ready` |
| PostgreSQL | 5432 | основная БД (asyncpg); в HA-режиме — CloudNativePG |
| Redis | 6379 | кэш, rate limiting, backend результатов Celery |
| RabbitMQ | 5672 / 15672 | брокер Celery; длину очереди `celery` читает KEDA |
| Celery-воркер | — | генерирует сертификат при `PATCH /enrollments/{id}/complete`; готовый PDF кладёт в S3 |
| SeaweedFS (S3) | 8333 | S3-совместимое хранилище файлов: бакет `fastapi-files` |
| Flower | 5555 | экспортёр метрик Celery (`flower_*`) |
| Prometheus / Alertmanager | 9090 / 9093 | метрики и алерты (namespace `monitoring`) |
| Grafana | 3000 (Service: 80) | дашборды метрик и логов |
| Loki + Alloy | 3100 / — | хранение и сбор логов всех подов |

## Что изменено в приложении (шаги 0–2)

- **PostgreSQL.** Драйвер `asyncpg`. Строки подключения собирает `app/config.py` из окружения:
  либо готовые `DATABASE_URL` / `REDIS_URL` / `CELERY_BROKER_URL`, либо части
  (`DATABASE_HOST`, `DATABASE_USER`, … — именно так их отдают ConfigMap и Secret). В коде ничего не зашито.
- **Брокер — RabbitMQ**, результаты задач — в Redis (`app/celery_app.py`, `task_acks_late`).
- **Пробы:** `GET /health` (liveness, зависимостей не проверяет) и `GET /ready` (БД + Redis, иначе 503).
- **Миграции Alembic** теперь асинхронные (`migrations/env.py`) и берут URL из того же `app/config.py`.
  В Kubernetes `AUTO_CREATE_TABLES=false`: схему создаёт Job `alembic upgrade head`, а не реплики API.
- **Образы:** `docker/Dockerfile.api` и `docker/Dockerfile.worker` — multi-stage, пользователь `appuser` (UID 1000, не root).
- **docker-compose.yml:** db, redis, rabbitmq, migrate, api, worker (+ flower в профиле `monitoring`).

## Быстрый старт

### 1. Тесты (без Docker, без PostgreSQL)

```bash
pip install -r requirements-dev.txt
pytest -v          # ~280 тестов: SQLite in-memory, fake Redis, Celery в eager-режиме
# С лаб. № 5 API требует JWT — примеры curl с токеном см. «Лабораторная № 5»
```

### 2. Docker Compose (контрольная точка перед Kubernetes)

```bash
docker compose up --build
curl http://127.0.0.1:8000/ready          # {"status":"ready"}
# Swagger: http://127.0.0.1:8000/docs   RabbitMQ UI: http://127.0.0.1:15672 (guest/guest)
```

### 3. Локально без Docker (SQLite)

```bash
DATABASE_URL=sqlite+aiosqlite:///./app.db uvicorn app.main:app --reload
```
Без Redis/RabbitMQ API запустится, но `/ready` вернёт 503, а `PATCH .../complete` без брокера не выполнит задачу.

## Kubernetes в Minikube (шаги 3–5)

```bash
minikube start --cpus=4 --memory=8g --driver=docker
eval $(minikube docker-env)                    # образы собираются прямо в Docker Minikube
docker build -t fastapi-app:latest    -f docker/Dockerfile.api .
docker build -t fastapi-worker:latest -f docker/Dockerfile.worker .

kubectl apply -f k8s/                          # namespace, config, secret, postgres, redis, rabbitmq, migrate, api, worker
kubectl get pods -n fastapi-app -w             # все поды Running, READY 1/1 (Job db-migrate → Completed)
kubectl port-forward svc/fastapi-service 8000:80 -n fastapi-app
# http://localhost:8000/docs
```

Файлы в `k8s/` пронумерованы, чтобы `kubectl apply -f k8s/` применял их в правильном порядке
(namespace → config/secret → хранилища → приложение). Дополнительные манифесты лежат в подпапках
(`cnpg/`, `keda/`, `ingress/`) и командой выше **не** применяются.
Ingress (опционально): `minikube addons enable ingress && kubectl apply -f k8s/ingress/` и запись `fastapi.local` в `/etc/hosts`.

### Эксперименты на отказоустойчивость (шаг 5)

```bash
# 1. Убить под API — запросы продолжают проходить через вторую реплику
kubectl delete pod "$(kubectl get pod -l app=fastapi -n fastapi-app -o name | head -1)" -n fastapi-app
while true; do curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/health; sleep 0.5; done

# 2. Пробы настроены
kubectl describe pod -l app=fastapi -n fastapi-app | grep -E "Liveness|Readiness"

# 3. Данные PostgreSQL переживают перезапуск пода (PVC)
curl -X POST localhost:8000/courses -H 'Content-Type: application/json' \
  -d '{"title":"K8s","description":"Тест PVC","instructor":"Иванов И.И.","duration_hours":8}'
kubectl delete pod postgres-0 -n fastapi-app
kubectl wait --for=condition=Ready pod/postgres-0 -n fastapi-app --timeout=120s
curl localhost:8000/courses                    # курс на месте

# 4. Celery через RabbitMQ: создать студента, записать, завершить курс — и смотреть логи
curl -X POST localhost:8000/students -H 'Content-Type: application/json' \
  -d '{"full_name":"Смирнова Анна","email":"anna@example.com"}'
curl -X POST localhost:8000/enrollments -H 'Content-Type: application/json' -d '{"student_id":1,"course_id":1}'
curl -X PATCH localhost:8000/enrollments/1/complete -H 'Content-Type: application/json' -d '{"grade":92.5}'
kubectl logs -l app=celery-worker -n fastapi-app --tail=20     # «Сертификат сгенерирован ...»
```

## Автомасштабирование Celery через KEDA (этап 7)

```bash
helm repo add kedacore https://kedacore.github.io/charts && helm repo update
helm install keda kedacore/keda -n keda --create-namespace
kubectl get pods -n keda

kubectl apply -f k8s/keda/                     # Secret + TriggerAuthentication + ScaledObject
kubectl get scaledobject,hpa -n fastapi-app

python scripts/load_test.py --count 100        # 100 задач в очередь (порт-форвард на :8000 уже запущен)
kubectl get pods -l app=celery-worker -n fastapi-app -w    # рост 1 → 5–10 подов, затем спад
```

Параметры (`k8s/keda/scaledobject.yaml`): опрос каждые 15 с, `value: "10"` — 10 сообщений на воркера,
`minReplicaCount: 1`, `maxReplicaCount: 20`. В воркере включена искусственная задержка
`CERTIFICATE_DELAY_SECONDS=2` — иначе задачи выполняются за миллисекунды и очередь не успевает вырасти.
Scale-to-zero (`minReplicaCount: 0`) экономит ресурсы в dev, но в production добавляет задержку
«холодного старта» воркера к первой задаче.

## CloudNativePG (шаг 9)

```bash
helm repo add cnpg https://cloudnative-pg.github.io/charts && helm repo update
helm install cnpg cnpg/cloudnative-pg -n cnpg-system --create-namespace

kubectl delete -f k8s/10-postgres.yaml                # убрать одиночный StatefulSet
kubectl apply  -f k8s/cnpg/postgres-cluster.yaml      # кластер из 3 инстансов
kubectl get pods -n fastapi-app -l cnpg.io/cluster=postgres-cluster -w

# Переключить приложение на сервис primary и заново применить миграции в новую БД:
sed -i 's/DATABASE_HOST: "postgres"/DATABASE_HOST: "postgres-cluster-rw"/' k8s/01-configmap.yaml
kubectl apply -f k8s/01-configmap.yaml
kubectl delete job db-migrate -n fastapi-app --ignore-not-found && kubectl apply -f k8s/20-migrate-job.yaml
kubectl rollout restart deploy/fastapi deploy/celery-worker -n fastapi-app

# Failover: убить primary и наблюдать выбор новой
PRIMARY=$(kubectl get cluster postgres-cluster -n fastapi-app -o jsonpath='{.status.currentPrimary}')
kubectl delete pod "$PRIMARY" -n fastapi-app
kubectl get cluster postgres-cluster -n fastapi-app -w
```
Приложение пишет только в `postgres-cluster-rw` (primary); `-ro` — реплики для чтения.
Бэкапы (MinIO/S3) — см. `k8s/cnpg/backup-minio.yaml.example`.

## Helm umbrella-чарт (шаги 6 и 10)

```
helm/
├── fastapi-platform/            # umbrella: общие ConfigMap/Secret + зависимости
│   ├── Chart.yaml               # dependencies с condition: можно отключить любой компонент
│   ├── values.yaml / values-dev.yaml / values-prod.yaml
│   ├── templates/               # _helpers.tpl, configmap.yaml, secrets.yaml
│   └── charts/
│       ├── fastapi-api/         # Deployment, Service, Ingress, Job миграций (Helm-hook)
│       ├── fastapi-worker/      # Deployment, ScaledObject + TriggerAuthentication (keda.enabled)
│       ├── infrastructure/      # Redis, RabbitMQ, PostgreSQL StatefulSet (для dev)
│       ├── seaweedfs/           # лаб. №4: Seaweed, Bucket, BucketLifecyclePolicy, ключи S3
│       └── observability/       # лаб. №4: ServiceMonitor API, Flower (+ его ServiceMonitor)
└── postgres-cluster/            # отдельный чарт CloudNativePG Cluster (не subchart!)
```

```bash
kubectl delete namespace fastapi-app                      # если ставили «сырые» манифесты
helm install fastapi-platform helm/fastapi-platform -n fastapi-app --create-namespace \
  -f helm/fastapi-platform/values-dev.yaml
kubectl port-forward svc/fastapi-platform-api 8000:80 -n fastapi-app

helm upgrade  fastapi-platform helm/fastapi-platform -n fastapi-app --set fastapi-worker.keda.enabled=true
helm rollback fastapi-platform 1 -n fastapi-app
helm list -n fastapi-app
helm install fastapi-platform helm/fastapi-platform -n dbg --create-namespace --set fastapi-worker.enabled=false   # только API
```

Почему PostgreSQL для production не subchart: CNPG — это оператор, он ставится отдельно (в `cnpg-system`) и
раньше самого `Cluster`; `Cluster` — кастомный ресурс, поэтому он вынесен в `helm/postgres-cluster`.
Для dev внутри `infrastructure` есть простой StatefulSet (`postgresql.enabled`), в prod он выключен.

Redis и RabbitMQ — локальный subchart `infrastructure`, а не Bitnami: чарты Bitnami тянут образы,
доступные бесплатно не во всех версиях, и требуют сети при `helm dependency update`.

## GitOps: Argo CD и Image Updater (шаги 11–13)

Раскладка репозитория для Argo CD: чарт в `helm/fastapi-platform`, значения окружений в `environments/<env>/values.yaml`.

```bash
./scripts/configure.sh <ваш-github-логин> <имя-репозитория>     # подставляет репозиторий и реестр
git init && git add . && git commit -m "lab 3" && git remote add origin ... && git push -u origin main

helm repo add argo https://argoproj.github.io/argo-helm && helm repo update
helm install argocd argo/argo-cd -n argocd --create-namespace -f argocd/argocd-values.yaml
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d; echo
kubectl port-forward svc/argocd-server -n argocd 8080:443        # https://localhost:8080, логин admin

kubectl apply -f argocd/application.yaml          # ИЛИ argocd/applicationset.yaml (dev/staging/prod из папок)
```

Проверка GitOps: измените `replicaCount` в `environments/prod/values.yaml`, сделайте `git push` —
через минуту-две Argo CD покажет OutOfSync → Synced, число подов изменится без `kubectl`.
Ручное изменение в кластере (`kubectl scale ...`) откатывается из-за `selfHeal: true`.

**Sync waves** (аннотации `argocd.argoproj.io/sync-wave` в шаблонах): `-1` ConfigMap, Secret, PostgreSQL →
`0` Redis, RabbitMQ → миграции (PostSync-хук) → `1` API → `2` воркеры и KEDA.

**Image Updater:**
```bash
kubectl create secret generic ghcr-creds -n argocd --from-literal=creds=<логин>:<токен-с-read:packages>
helm install argocd-image-updater argo/argocd-image-updater -n argocd -f argocd/image-updater-values.yaml
git tag v1.2.1 && git push --tags                 # CI соберёт образы с тегом v1.2.1
kubectl logs -n argocd deploy/argocd-image-updater -f   # «Updates image ... to v1.2.1»; в Git появится коммит
```
Стратегия `semver` с ограничением `~1.2` + `allow-tags` разрешает только patch-версии 1.2.x
(`^1.2` пропустил бы и 1.3). Запись — Git write-back в `environments/<env>/values.yaml`.
Формат аннотаций соответствует Image Updater 0.x (как в лабораторной); для версий 1.x проверьте документацию.

**Multi-cluster (бонус):** `argocd/applicationset-matrix.yaml` — Matrix Generator «окружения × кластеры»,
с `RollingSync` (Progressive Sync включается флагом контроллера).

## Лабораторная № 4: наблюдаемость и S3-хранилище

Что добавлено в проект:

| Область | Файлы |
|---------|-------|
| Метрики приложения | `app/metrics.py` (`/metrics`, бизнес-метрики файлов, длина очереди `celery_queue_length`) |
| S3 (SeaweedFS) | `app/s3_client.py`, `app/routers/files.py`, `app/s3_init.py`; сертификаты воркера → S3 (`app/tasks.py`) |
| Манифесты SeaweedFS | `k8s/seaweedfs/` (кластер, бакет, S3-ключи), `k8s/03-s3-config.yaml`, `app-s3-secrets` в `k8s/02-secrets.yaml` |
| Мониторинг | `monitoring/` (`prometheus-values.yaml`, `loki-values.yaml`, `alloy-values.yaml`, datasource, Secret Grafana, дашборды), `k8s/monitoring/` (ServiceMonitor, Flower) |
| Helm | subchart'ы `seaweedfs` и `observability` в umbrella-чарте, S3-переменные в ConfigMap/Secret |
| GitOps | `argocd/observability-apps.yaml` (оператор SeaweedFS, kube-prometheus-stack, Loki, Alloy) |
| CI | job `observability-validate`, ручной `deploy-monitoring.yml` |

### Порядок развёртывания (Minikube)

Нужен кластер побольше: `minikube start --cpus=4 --memory=8192 --disk-size=40g`. Образы собраны внутри Minikube
(`eval $(minikube docker-env)`; `docker build -f docker/Dockerfile.api -t fastapi-app:latest .`, то же для воркера).

**Вариант А — одной командой** (операторы → мониторинг → приложение через Helm):

```bash
./scripts/deploy-observability.sh
```

**Вариант Б — по шагам** (так же устроен отчёт):

```bash
# 1. SeaweedFS: оператор → ключи S3 → кластер → бакет
helm repo add seaweedfs-operator https://seaweedfs.github.io/seaweedfs-operator/ && helm repo update
helm install seaweedfs-operator seaweedfs-operator/seaweedfs-operator -n seaweedfs-system --create-namespace
kubectl get pods -n seaweedfs-system

kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/seaweedfs/s3-credentials.yaml          # identities S3 (Secret seaweedfs-s3-config)
kubectl apply -f k8s/seaweedfs/seaweedfs-cluster.yaml       # master + volume + filer + s3
kubectl get pods -n fastapi-app -l app.kubernetes.io/name=seaweedfs
kubectl get svc  -n fastapi-app | grep seaweedfs            # seaweedfs-s3  8333/TCP
kubectl apply -f k8s/seaweedfs/seaweedfs-bucket.yaml        # бакет fastapi-files через CRD
kubectl get bucket -n fastapi-app

# 2. Стек мониторинга
kubectl apply -k monitoring/                                # namespace, Secret Grafana, datasource Loki, дашборды
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts && helm repo update
helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring -f monitoring/prometheus-values.yaml
helm install loki  grafana/loki  -n monitoring -f monitoring/loki-values.yaml
helm install alloy grafana/alloy -n monitoring -f monitoring/alloy-values.yaml
kubectl get pods -n monitoring

# 3. Приложение (манифесты ЛИБО Helm)
kubectl apply -f k8s/                                       # конфиги, БД, API, воркер (+ S3-конфиг и ключи)
kubectl apply -f k8s/monitoring/                            # ServiceMonitor API, Flower
# или: helm upgrade --install fastapi-platform helm/fastapi-platform -n fastapi-app --create-namespace \
#        -f helm/fastapi-platform/values-dev.yaml
```

Кластер без оператора SeaweedFS или без CRD Prometheus Operator: `--set seaweedfs.enabled=false`
и/или `--set observability.enabled=false` (иначе Helm не найдёт CRD `Seaweed`/`ServiceMonitor`).

### SeaweedFS и S3

`Seaweed` — один master, один volume-сервер, один filer и отдельный S3-шлюз (Service `seaweedfs-s3:8333`).
Учётные записи задаёт Secret `seaweedfs-s3-config` (формат `s3.json`): `admin` (запись/удаление) и `reader`
(только чтение). Те же ключи лежат в Secret приложения `app-s3-secrets`; тест
`test_s3_keys_match_between_app_secret_and_server_identities` следит, чтобы они не разошлись.

> **Отличия от методички.** В актуальной версии оператора поля CRD другие: размер диска volume-сервера —
> `volume.requests.storage`, S3 — отдельный блок `spec.s3` (а не `filer.s3`/`enableAuth`), бакет ссылается на
> кластер через `spec.clusterRef` и задаёт квоту `quota.size`. Secret `seaweedfs-s3-secret` оператор **не создаёт**,
> поэтому ключи задаются явно. Манифесты проверены на соответствие схемам CRD оператора
> (манифест `Bucket` из методички этим схемам не соответствует).

API для файлов (`/files`, Swagger `/docs`):

| Метод | Путь | Что делает |
|-------|------|-----------|
| POST | `/files/upload?folder=avatars` | загрузка (≤ 10 МБ, имя очищается, ключ `<папка>/<uuid>_<имя>`) |
| GET | `/files/download/{key}` | скачивание через API (read-only ключи) |
| GET | `/files/url/{key}?expires=3600` | presigned URL: клиент качает напрямую из S3 |
| GET | `/files?prefix=certificates/` | список объектов |
| DELETE | `/files/{key}` | удаление (admin-ключи) |

Каждый сертификат, сгенерированный воркером, дополнительно загружается в `certificates/certificate_<id>.pdf`
(`S3_UPLOAD_CERTIFICATES=true`); ошибка хранилища не роняет задачу.

```bash
kubectl port-forward svc/fastapi-service 8000:80 -n fastapi-app
curl -F "file=@README.md" "localhost:8000/files/upload?folder=docs"        # → {"key": "docs/ab12cd34_README.md", ...}
curl "localhost:8000/files?prefix=docs/"
curl "localhost:8000/files/download/docs/ab12cd34_README.md"
```

### Метрики Prometheus

`GET /metrics` (prometheus-fastapi-instrumentator): `http_requests_total{handler,method,status}`,
`http_request_duration_seconds_bucket`, `http_requests_in_progress`, а также `files_operations_total`,
`files_bytes_total` и `celery_queue_length{queue="celery"}`.

Три отличия от текста методички, без которых запросы не работали бы:
1. Статусы не группируются (`should_group_status_codes=False`): иначе метка `status="5xx"` не совпала бы с `status=~"5.."`.
2. Пробы `/health`, `/ready` и сам `/metrics` исключены — они дёргаются каждые 10–15 с и «забивают» реальный трафик.
3. Celery метрик не отдаёт, а Flower длину очереди не публикует, поэтому `celery_queue_length` отдаёт
   кастомный коллектор (пассивный `queue_declare` к RabbitMQ). Flower дополняет картину метриками `flower_*`
   (события задач, время выполнения, воркеры online).

Prometheus находит цели через **ServiceMonitor**: он выбирает Service по меткам и скрейпит именованный порт `http`
(у `fastapi-service` добавлены метка `app: fastapi` и имя порта). `serviceMonitorSelectorNilUsesHelmValues: false` в
`prometheus-values.yaml` позволяет видеть ServiceMonitor без метки `release`.

```bash
kubectl port-forward svc/monitoring-kube-prometheus-prometheus -n monitoring 9090:9090
# http://localhost:9090/targets → fastapi-monitor и flower-monitor в состоянии UP
```

### Grafana: дашборды и логи

```bash
kubectl port-forward svc/monitoring-grafana -n monitoring 3000:80      # http://localhost:3000, admin / admin
```

Дашборды хранятся в Git (`monitoring/grafana-dashboards/*.json`, генерируются `scripts/gen_dashboards.py`),
превращаются в ConfigMap с меткой `grafana_dashboard=1` (`kubectl apply -k monitoring/`) и подхватываются sidecar'ом Grafana:

* **FastAPI — RED + логи**: запросов/с, доля 5xx, p50/p95/p99, запросы в обработке, коды ответов, операции с файлами, логи ошибок.
* **Celery — очередь, воркеры, KEDA + логи**: длина очереди рядом с числом реплик воркера (видно работу KEDA), события и время задач, логи воркеров.

Логи: Alloy читает логи всех подов через Kubernetes API (кроме `kube-system`, `kube-public`, `kube-node-lease`, `monitoring`)
и пишет в Loki с метками `namespace`, `pod`, `container`, `app`. Grafana → Explore → Loki:

```
{namespace="fastapi-app"}
{namespace="fastapi-app", app="fastapi"} |= "ERROR"
{namespace="fastapi-app", app="celery-worker"} |= "Сертификат"
```

### Алерты

Правила — в `monitoring/prometheus-values.yaml` (`additionalPrometheusRulesMap`): `HighErrorRate` (5xx > 5% за 5 мин),
`HighLatency` (p95 > 1 с), `FastAPIDown`, `FastAPIPodNotReady`, `CeleryQueueBacklog` (> 100 за 10 мин),
`CeleryTasksFailing`, `FileStorageErrors`. Запросы агрегируют серии по всем репликам (`sum`/`max`).

```bash
kubectl port-forward svc/monitoring-kube-prometheus-alertmanager -n monitoring 9093:9093    # http://localhost:9093
# Как вызвать алерт: остановить Redis и PostgreSQL → /ready отдаёт 503 → FastAPIPodNotReady;
# или python scripts/load_test.py --count 2000 при CERTIFICATE_DELAY_SECONDS=2 → CeleryQueueBacklog.
```
Уведомления никуда не отправляются (receiver-заглушка); для Slack/e-mail раскомментируйте канал в `alertmanager.config`.

### Helm и GitOps

Umbrella-чарт получил subchart'ы `seaweedfs` (Seaweed, Bucket, BucketLifecyclePolicy, ключи S3) и `observability`
(ServiceMonitor API, Flower). Сами Prometheus/Grafana/Loki/Alloy — отдельные релизы в `monitoring` (как CNPG и KEDA:
у них свои CRD и жизненный цикл), но их можно развернуть через Argo CD: `kubectl apply -f argocd/observability-apps.yaml`
(multi-source Application: чарт из репозитория Helm, values — из этого Git).

### Docker Compose

`docker compose up --build` теперь поднимает ещё и SeaweedFS (`:8333`) и одноразовый `s3-init`, создающий бакет;
`docker compose --profile monitoring up` добавляет Flower (`:5555`) и Prometheus (`:9090`). Метрики API: `http://127.0.0.1:8000/metrics`.

### Доступ к сервисам

```bash
kubectl port-forward svc/fastapi-service 8000:80 -n fastapi-app                          # API, /docs, /metrics
kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring                        # Grafana
kubectl port-forward svc/monitoring-kube-prometheus-prometheus 9090:9090 -n monitoring   # Prometheus
kubectl port-forward svc/monitoring-kube-prometheus-alertmanager 9093:9093 -n monitoring # Alertmanager
kubectl port-forward svc/seaweedfs-s3 8333:8333 -n fastapi-app                           # S3 API
aws --endpoint-url http://localhost:8333 s3 ls s3://fastapi-files        # (AWS_ACCESS_KEY_ID=app-admin-key, AWS_SECRET_ACCESS_KEY=...)
```

### Решение проблем

| Симптом | Причина и решение |
|---------|-------------------|
| `fastapi-monitor` нет в Targets | нет метки `app: fastapi` / имени порта `http` у Service; ServiceMonitor не применён; проверьте `kubectl get servicemonitor -A` и `serviceMonitorSelectorNilUsesHelmValues: false` |
| Цель DOWN, `connection refused` | Service смотрит не на тот порт; проверьте `kubectl get endpoints fastapi-service -n fastapi-app` |
| `no matches for kind "Seaweed"` / `"ServiceMonitor"` | не установлены CRD: оператор SeaweedFS / kube-prometheus-stack; поставьте их раньше или отключите `seaweedfs.enabled` / `observability.enabled` |
| Бакет в фазе `Failed`/`Pending` | кластер SeaweedFS ещё не готов (`kubectl get seaweed,pods -n fastapi-app`); `kubectl describe bucket fastapi-files` |
| Загрузка файла: 502 / `InvalidAccessKeyId`, `SignatureDoesNotMatch` | ключи в `app-s3-secrets` не совпадают с `seaweedfs-s3-config`; после смены перезапустите поды S3 и API |
| Образ `chrislusf/seaweedfs:4.48` не скачивается | возьмите актуальный тег на Docker Hub и поправьте `image` в `seaweedfs-cluster.yaml` |
| В Loki нет логов | `kubectl logs -n monitoring -l app.kubernetes.io/name=alloy`; проверьте адрес `loki-gateway` и RBAC (`pods/log`) |
| Grafana: «No data» на панели | неверный источник данных (в дашборде переменные `Prometheus`/`Loki`), нет трафика (`curl localhost:8000/courses`) или цель DOWN |
| Дашборд не появился | ConfigMap без метки `grafana_dashboard=1`; `kubectl logs -n monitoring deploy/monitoring-grafana -c grafana-sc-dashboard` |
| `celery_queue_length` отсутствует | API не достаёт RabbitMQ или очередь `celery` ещё не создана (воркер не запускался) |
| Pod Prometheus/Loki `Pending` | не хватает ресурсов Minikube: `minikube start --cpus=4 --memory=8192` |

## Лабораторная № 7: компонентная архитектура фронтенда и CRUD

Во фронтенде появились собственные UI-компоненты (`BaseButton`, `BaseInput`, `BaseModal`, `BaseCard`, toast-уведомления),
composables (`useResource`, `useForm`, `useToast`, `useDebouncedRef`) и экраны деталей, создания и редактирования курса.
Пользователь создаёт, правит и удаляет курсы через `POST/PUT/DELETE /courses`, ошибки 422 FastAPI показываются под полями,
удаление подтверждается в модальном окне. Описание компонентов, маршрутов и скриншоты сквозного CRUD-сценария
из Chrome — в [`frontend-app/README.md`](frontend-app/README.md#лабораторная--7-компоненты-composables-и-crud).
Бэкенд не менялся: CRUD-эндпоинты курсов и роли были готовы в лаб. № 3–5.

## Лабораторная № 6: MVP-фронтенд на Vue.js

SPA в каталоге `frontend-app/` (Vue 3, Vite, Pinia, Vue Router, Axios, Vitest). Фронтенд запускается на компьютере
через `npm run dev` (`http://localhost:5173`) и работает с бэкендом на `http://localhost:8000`. Подробная инструкция,
переменные окружения, сквозной сценарий со скриншотами и решение проблем — в [`frontend-app/README.md`](frontend-app/README.md).

```bash
# бэкенд (терминал 1)
export DATABASE_URL=sqlite+aiosqlite:///./app.db ADMIN_BOOTSTRAP_USERNAME=admin ADMIN_BOOTSTRAP_PASSWORD=ChangeMe-Admin-2026
uvicorn app.main:app --reload
python scripts/seed_demo.py                       # демо-курсы и пользователь student / Student-passw0rd
# фронтенд (терминал 2)
cd frontend-app && npm install && cp .env.example .env.local && npm run dev
```

Изменения бэкенда: CORS по умолчанию разрешает dev-сервер Vite (`http://localhost:5173`, `http://127.0.0.1:5173`) при
`ENVIRONMENT=development`, если `CORS_ORIGINS` не задана; пустая строка (как в Kubernetes) CORS выключает, `"*"` не используется.
Добавлены `scripts/seed_demo.py` и тесты CORS (`app/tests/test_cors.py`).

## Лабораторная № 5: безопасность и защита данных

> **С этой работы API закрыт авторизацией.** Примеры `curl` из разделов выше выполняйте с заголовком
> `Authorization: Bearer $TOKEN` (получение токена — ниже). `/`, `/health`, `/ready` остаются открытыми
> (пробы Kubernetes), `/metrics` доступен только из кластера.

Что добавлено:

| Область | Файлы |
|---------|-------|
| Аутентификация и роли | `app/auth.py`, `app/routers/auth.py`, `app/routers/users.py`, `app/db_models/user.py`, миграция `0002_users_auth.py`, `app/bootstrap.py` |
| Защита HTTP | `app/security.py` (заголовки, Host, CORS, закрытие `/metrics` от Ingress), `extra="forbid"` во входных моделях |
| Pod Security, securityContext | `k8s/00-namespace.yaml` (PSS `restricted`), все манифесты `k8s/*.yaml`, Helm-шаблоны |
| Сетевая изоляция | `k8s/network-policies/network-policies.yaml` (генерируется из `helm/.../templates/networkpolicies.yaml`) |
| Секреты | `k8s/vault/`, `security/vault-values.yaml`, `scripts/vault-setup.sh`, `helm/.../templates/vault.yaml` |
| TLS | `k8s/ingress/ingress.yaml`, `security/cert-manager-issuers.yaml` |
| Политики и рантайм | `security/kyverno-policies.yaml`, `security/falco-values.yaml` |
| Наблюдаемость безопасности | дашборд `security-dashboard.json`, алерты `AuthBruteForce`, `RefreshTokenReuse`, `UnauthorizedRequestsSpike` |
| CI | `security-scan` (Trivy), сканирование образов до push, все actions закреплены по SHA коммита |
| GitOps | `argocd/security-apps.yaml`, PSS-метки через `managedNamespaceMetadata` |

### Угрозы и меры (OWASP API Top 10)

| Угроза | Как закрыта |
|--------|-------------|
| API1 BOLA (доступ к чужим объектам) | студент видит только свою карточку, записи и файлы; одинаковый `403` для чужого и несуществующего id (перебор ID бесполезен); сертификат доступен только владельцу записи |
| API2 Broken Authentication | bcrypt, политика паролей, ограничение попыток входа (по логину и по IP), одинаковые ответы и время для «нет пользователя»/«неверный пароль», короткий access (30 мин), refresh с ротацией и отзывом, обязательные `exp`/`sub`/`type`, запрет `alg=none`, слабый `SECRET_KEY` в production = отказ запуска |
| API3 Mass Assignment | входные модели с `extra="forbid"` (`{"role":"admin"}` → 422); регистрация всегда создаёт роль `user`; админ меняет только `role` и `is_active` |
| API4 Ресурсы | лимиты: попытки входа, запись на курс, размер загрузки (10 МБ), лимит тела на Ingress, quota бакета |
| API5 BFLA (функции без прав) | создание/изменение курсов, список студентов, оценки, `/admin`, `/users` — только `admin` (зависимость `require_admin`) |
| API8 Security Misconfiguration | заголовки безопасности, проверка `Host`, CORS по белому списку, `/metrics` не отдаётся через Ingress, XSS в `/admin` исправлен (`html.escape`) |
| API9 Инвентаризация | `DOCS_ENABLED=false` скрывает Swagger в production |
| Секреты | Vault + VSO; в Git нет паролей приложения; Trivy ищет секреты в репозитории |
| Цепочка поставок | actions закреплены по SHA, Trivy блокирует CRITICAL/HIGH в образах и зависимостях |

### Аутентификация и роли

```bash
kubectl port-forward svc/fastapi-service 8000:80 -n fastapi-app
# Регистрация (создаёт студента и пользователя с ролью user)
curl -X POST localhost:8000/auth/register -H 'Content-Type: application/json' \
  -d '{"username":"anna_s","password":"Str0ng-passw0rd","full_name":"Смирнова Анна","email":"anna@example.com"}'
# Вход → access + refresh
curl -X POST localhost:8000/auth/token -d 'username=anna_s&password=Str0ng-passw0rd'
TOKEN=<access_token>
curl localhost:8000/auth/me -H "Authorization: Bearer $TOKEN"
# Первый администратор создаётся из ADMIN_BOOTSTRAP_USERNAME/PASSWORD (k8s/02-secrets.yaml)
curl -X POST localhost:8000/auth/token -d 'username=admin&password=ChangeMe-Admin-2026'
```

| Эндпоинт | Доступ |
|----------|--------|
| `POST /auth/register`, `/auth/token`, `/auth/refresh`, `/auth/logout` | открыты (с лимитами) |
| `GET /auth/me`, `POST /auth/change-password` | любой пользователь |
| `GET /courses`, `GET /courses/{id}` | любой пользователь |
| `POST/PUT/DELETE /courses…`, `GET/POST /students`, `PATCH /enrollments/{id}/complete`, `/admin/*`, `/users/*` | только `admin` |
| `GET /students/{id}` | админ или владелец |
| `POST /enrollments` | себя (админ — любого) |
| `GET /enrollments` | свои записи (админ — все) |
| `POST /files/upload` | любой; файл обычного пользователя попадает в `users/<id>/…` |
| `GET /files…`, `…/download`, `…/url`, `DELETE` | админ — всё; пользователь — свой каталог и свои сертификаты |

Refresh-токены хранятся в БД (по `jti`): `logout` и смена пароля отзывают их; повторное предъявление уже использованного
токена считается кражей — отзываются все токены пользователя. Токен передаётся только в теле запроса
(не в URL, который попадает в логи).

> **Отличия от методички.** `PyJWT` + `bcrypt` вместо `python-jose` + `passlib`: python-jose слабо поддерживается
> и имел CVE, passlib несовместим с bcrypt ≥ 4.1. Роль и `is_active` берутся из БД на каждый запрос, поэтому блокировка
> и смена роли действуют сразу, а не через 30 минут.

### Порядок развёртывания (Minikube)

```bash
# NetworkPolicy работают только при CNI с их поддержкой — стандартный Minikube их НЕ применяет:
minikube start --cpus=4 --memory=8192 --disk-size=40g --cni=calico
minikube addons enable ingress

./scripts/deploy-security.sh      # cert-manager, Kyverno, Vault + VSO (+настройка), Falco, политики
# затем приложение (как в лаб. № 3–4), без app-secrets — его создаст Vault:
kubectl apply -f k8s/00-namespace.yaml                 # PSS: restricted
kubectl apply -f k8s/vault/                            # SA, VaultAuth, VaultStaticSecret → Secret app-secrets
kubectl get secret app-secrets -n fastapi-app          # появился (создал VSO)
kubectl apply -f k8s/                                  # конфиги, БД, брокер, API, воркер
kubectl apply -f k8s/ingress/ingress.yaml
kubectl apply -f k8s/network-policies/network-policies.yaml   # в самом конце
```

Без Vault: `kubectl apply -f k8s/local/app-secrets.yaml` вместо `k8s/vault/`. Helm: `vault.enabled=true`
для staging/prod уже включён в `environments/*`; для dev — `--set vault.enabled=true` или значения по умолчанию
(`global.jwt.secretKey` пуст → учебный ключ). Один скрипт без Argo CD: `scripts/deploy-observability.sh`
(лаб. № 4) + `scripts/deploy-security.sh`.

### Pod Security Standards и securityContext

Namespace `fastapi-app` помечен `pod-security.kubernetes.io/enforce: restricted`: под, нарушающий профиль, **не создаётся**.
Поэтому все workloads соответствуют ему:

| Workload | Пользователь | readOnlyRootFilesystem | Записываемые каталоги |
|----------|--------------|------------------------|-----------------------|
| API, воркер, Job миграций | 1000 | да | `/tmp` (воркер ещё `/app/certificates`) |
| PostgreSQL (alpine) | 70 | да | PVC, `/var/run/postgresql`, `/tmp` |
| Redis (alpine) | 999 | да | `/data` (emptyDir) |
| RabbitMQ (alpine) | 100 / 101 | **нет** (обоснование ниже) | `/var/lib/rabbitmq`, `/var/log/rabbitmq` |
| Flower | 1000 | да | `/tmp`, `/data` |
| SeaweedFS (через CR) | 1000 | нет | PVC |

Для всех: `runAsNonRoot`, `capabilities.drop: [ALL]`, `allowPrivilegeEscalation: false`, `seccompProfile: RuntimeDefault`,
`automountServiceAccountToken: false` (никому из них не нужен доступ к API Kubernetes). RabbitMQ без
`readOnlyRootFilesystem`: образ хранит `10-defaults.conf` в `/etc/rabbitmq/conf.d` и пишет в свои каталоги, подмена их
пустым томом ломает сетевой доступ; остальные требования restricted выполнены. UID алпайн-образов указаны явно
(postgres 70, redis 999, rabbitmq 100). Профиль проверяется автотестом на всех манифестах и на рендере Helm.

```bash
kubectl get ns fastapi-app --show-labels | tr ',' '\n' | grep pod-security
# попытка запустить небезопасный под — отказ:
kubectl run bad --image=nginx -n fastapi-app --privileged     # Error ... violates PodSecurity "restricted"
```

### NetworkPolicy

`default-deny-all` + разрешения (DNS по UDP и TCP, Ingress → API, Prometheus → API/Flower, API/воркер → БД/Redis/RabbitMQ/S3,
KEDA → RabbitMQ, SeaweedFS между компонентами и оператором, CloudNativePG, cert-manager-решатель). Политики
генерируются из Helm-шаблона (`./scripts/gen-network-policies.sh`), CI проверяет отсутствие расхождений.
Автотест содержит симулятор политик и проверяет 22 нужных и 21 лишний поток.

> **Отличия от методички.** Добавлены то, чего в шаблоне не хватало и что сломало бы приложение: воркер → S3 (кладёт сертификаты),
> Prometheus → API и Flower (иначе мониторинг лаб. № 4 перестаёт работать), KEDA → RabbitMQ, оператор SeaweedFS, DNS по TCP,
> доступ CNPG к API-серверу Kubernetes. Метки подов: везде единая `app: <имя>`.

```bash
# Разрешено: API → PostgreSQL
kubectl exec -n fastapi-app deploy/fastapi -- python -c "import socket; socket.create_connection(('postgres',5432),3); print('OK')"
# Запрещено: под из другого namespace → Redis (таймаут)
kubectl run nettest -n default --rm -it --restart=Never --image=busybox -- nc -zv -w3 redis.fastapi-app 6379
# Запрещено: воркер → API
kubectl exec -n fastapi-app deploy/celery-worker -- python -c "import socket; socket.create_connection(('fastapi-service',80),3)"
```

### Vault и Vault Secrets Operator

Vault в dev-режиме (данные в памяти!) хранит `SECRET_KEY`, пароли БД и брокера (`secret/fastapi/config`, kv-v2).
VSO логинится в Vault токеном ServiceAccount `fastapi-sa` (метод `kubernetes`), читает секрет и **сам создаёт Secret
`app-secrets`**, а при изменении перезапускает API и воркеры. `scripts/vault-setup.sh` включает метод `kubernetes`,
настраивает адрес API-сервера, политику (`read` только на `secret/data/fastapi/*`) и роль (только `fastapi-sa` из `fastapi-app`,
`audience=vault`) — в методичке этих шагов нет, без них Vault отвечает 403. Bootstrap-пароль администратора остаётся в обычном
Secret `app-bootstrap-secrets`.

```bash
kubectl get vaultauth,vaultstaticsecret -n fastapi-app           # статус: Synced / Healthy
kubectl exec -n vault vault-0 -- env VAULT_TOKEN=root vault kv get secret/fastapi/config
# Ротация: меняем значение в Vault — через ≤ 30 с Secret обновится, поды перезапустятся
kubectl exec -n vault vault-0 -- env VAULT_TOKEN=root vault kv patch secret/fastapi/config SECRET_KEY=$(openssl rand -hex 32)
kubectl rollout status deploy/fastapi -n fastapi-app
```

Важно: пароль БД в Vault должен совпадать с тем, с которым PostgreSQL был инициализирован (смена пароля в Vault не меняет
пользователя в уже созданной БД). Для автоматической ротации есть `k8s/vault/optional/vault-dynamic-secret.yaml`
(динамические учётные данные PostgreSQL с TTL). Смена `SECRET_KEY` разлогинивает всех пользователей — это ожидаемо.

### TLS (cert-manager)

`ClusterIssuer`: `selfsigned-issuer` (Minikube, домен `fastapi.local`) и `letsencrypt-staging` / `letsencrypt-prod` (реальный домен,
HTTP-01). Ingress с аннотацией `cert-manager.io/cluster-issuer` и блоком `tls` получает сертификат в Secret `fastapi-tls`,
cert-manager продлевает его сам. Включён редирект на HTTPS, приложение добавляет HSTS за HTTPS-прокси.

```bash
kubectl get certificate -n fastapi-app                       # READY=True
curl -k https://fastapi.local/health ; curl -sI http://fastapi.local/ | head -2   # 308 → https
```
Let's Encrypt не выдаёт сертификаты на `fastapi.local`: для боевого выпуска нужен публичный домен, указывающий на Ingress,
и подстановка e-mail в `security/cert-manager-issuers.yaml`.

### Kyverno, Falco, Trivy

* **Kyverno** (`security/kyverno-policies.yaml`): запрет privileged и root — `Enforce`, тег `:latest` — `Audit`
  (локальные образы Minikube). Политики действуют только в `fastapi-*`, иначе остановили бы системные поды.
  `failureAction` задан в правиле (поле `validationFailureAction` в ClusterPolicy помечено deprecated).
  Проверка: `kubectl get clusterpolicy`, `kubectl get policyreport -A`.
* **Falco** (`security/falco-values.yaml`): драйвер `modern_ebpf` (legacy `ebpf` из методички устарел и требует заголовков ядра),
  свои правила: shell в контейнере `fastapi-app` и чтение токена service account. События идут в Loki и на дашборд «Безопасность».
  Проверка: `kubectl exec -it -n fastapi-app deploy/fastapi -- sh`, затем `kubectl logs -n falco -l app.kubernetes.io/name=falco | grep -i shell`.
* **Trivy** (CI): `security-scan` ищет уязвимости зависимостей и секреты в репозитории (CRITICAL/HIGH блокируют сборку), образы сканируются
  **до** публикации, мисконфигурации манифестов выводятся отчётом. Все actions закреплены по SHA коммита, а не по тегу:
  тег можно переписать, SHA — нет. Обновлять SHA нужно осознанно (Dependabot/Renovate).

### Решение проблем

| Симптом | Причина и решение |
|---------|-------------------|
| Под не создаётся: `violates PodSecurity "restricted"` | в манифесте нет `runAsNonRoot`/`seccompProfile`/`drop: ALL`; команда `kubectl get events -n fastapi-app`; временно понизить `enforce` до `baseline` |
| Под в `CrashLoopBackOff`, `permission denied` | образ пишет в каталог, недоступный при `readOnlyRootFilesystem` или не-root; смонтируйте `emptyDir` (см. таблицу PSS) или проверьте `fsGroup`/UID образа |
| NetworkPolicy «не работают» (всё доступно) | CNI без поддержки политик: пересоздайте Minikube с `--cni=calico` |
| После политик пропали метрики / не масштабируются воркеры / нет S3 | проверьте потоки: Prometheus → API/Flower, KEDA → RabbitMQ, воркер → `seaweedfs:8333`; `kubectl describe networkpolicy -n fastapi-app` |
| Под не резолвит имена | DNS должен быть открыт по UDP **и** TCP (политика `allow-dns-egress`) |
| `VaultAuth` в статусе Error / 403 от Vault | не выполнен `scripts/vault-setup.sh` (метод `kubernetes`, роль) или `audience` роли ≠ `vault` |
| `Secret app-secrets` не появился | `kubectl describe vaultstaticsecret app-secrets -n fastapi-app`; VSO не установлен; Secret создан вручную (конфликт) |
| API не стартует: `SECRET_KEY не задан или короче 32` | `ENVIRONMENT=production/staging` требует сильный ключ из Vault/Secret |
| 401 на все запросы после смены ключа | токены подписаны старым `SECRET_KEY` — войдите заново |
| 429 при входе | сработал лимит попыток на логин (`AUTH_RATE_LIMIT_MAX`/`WINDOW`), подождите окно |
| 400 `Invalid host header` | значение `Host` не входит в `TRUSTED_HOSTS` (добавьте хост Ingress) |
| Сертификат не выпускается (`READY=False`) | `kubectl describe certificate,order,challenge -n fastapi-app`; для `fastapi.local` используйте `selfsigned-issuer`; HTTP-01 решатель должен быть доступен Ingress (политика `allow-acme-solver`) |
| Kyverno блокирует под | `kubectl describe clusterpolicy`; политика привязана к `fastapi-*`; для отладки `failureAction: Audit` |
| Falco в `CrashLoopBackOff` | ядро без BTF для `modern_ebpf`: `--set driver.kind=kmod` (нужны kernel headers) |

## CI (GitHub Actions)

`.github/workflows/ci.yml`: `pytest` и `frontend` (линтеры, Vitest, сборка Vue) → `helm lint` + `helm template` (в т.ч. без SeaweedFS и мониторинга) →
`observability-validate` (kustomize build, kubeconform, `alloy validate`, актуальность дашбордов) → сборка и публикация
образов в GHCR (теги: `sha-…` и `vX.Y.Z` при `git tag`). Деплоя в кластер нет: это задача Argo CD (pull-модель,
kubeconfig в CI не нужен). Вариант из методички (шаг «Deploy monitoring stack» в CI) оформлен отдельным ручным
workflow `.github/workflows/deploy-monitoring.yml` — он нужен только если кластер доступен из GitHub Actions.

## Структура проекта

```
├── app/                     # приложение: config.py, routers/{health,files}.py, metrics.py, s3_client.py, s3_init.py
├── docker/                  # Dockerfile.api, Dockerfile.worker (multi-stage, non-root)
├── docker-compose.yml       # db + redis + rabbitmq + SeaweedFS + api + worker (+ flower, prometheus)
├── k8s/                     # «сырые» манифесты; cnpg/, keda/, ingress/, seaweedfs/, monitoring/ — отдельно
├── monitoring/              # values kube-prometheus-stack / Loki / Alloy, Grafana: datasource, дашборды (лаб. №4)
├── security/                # Kyverno, Falco, Vault, cert-manager (лаб. №5)
├── frontend-app/            # SPA на Vue 3 + Vite (лаб. №6)
├── helm/                    # fastapi-platform (umbrella) и postgres-cluster (CNPG)
├── argocd/                  # Application, ApplicationSet (Git dir / Matrix), values Argo CD и Image Updater
├── environments/            # dev / staging / prod values для GitOps
├── migrations/, alembic.ini # Alembic (async)
├── scripts/                 # load_test.py, configure.sh, gen_dashboards.py, deploy-observability.sh
├── docs/                    # LAB1-2.md, DEFENSE.md (ответы на вопросы для защиты)
└── .github/workflows/       # ci.yml, deploy-monitoring.yml (ручной)
```

## Что проверено, а что нет

**Проверено в среде сборки (без кластера):**

* `pytest` — 280+ тестов (API, аутентификация, роли и BOLA, метрики, S3, воркер, согласованность конфигов), `flake8`.
* Реальный код `app/s3_client.py` прогнан против S3-совместимого сервера (moto): загрузка, скачивание, список, presigned URL, удаление, 404.
* Helm 3.10: `helm lint` и `helm template` для dev / staging / prod и с отключёнными `seaweedfs` / `observability`.
* `kubeconform --strict`: 99 ресурсов (манифесты `k8s/`, `monitoring/`, рендер чартов, включая `ServiceMonitor`) валидны.
* Ресурсы `Seaweed`, `Bucket`, `BucketLifecyclePolicy` (манифесты и рендер Helm) соответствуют схемам CRD оператора SeaweedFS.
* `alloy validate` (Alloy v1.20.1) для конфигурации сбора логов; `kustomize build monitoring/`.
* Все PromQL-запросы дашбордов и алертов разбираются парсером Prometheus; метрики в них действительно экспортируются приложением.


**Лаб. № 5 — проверено без кластера:**

* Аутентификация: подделанные токены (`alg=none`, чужой ключ, без `exp`, refresh вместо access, роль в токене), ротация и повторное
  предъявление refresh, лимит попыток входа, отсутствие различий между «нет пользователя» и «неверный пароль» — автотесты;
  намеренная порча защиты (`require_admin`, проверка владельца) приводит к падению тестов.
* Авторизация: каждый эндпоинт без токена даёт 401; роли; BOLA для студентов, записей, файлов и сертификатов; Mass Assignment.
* Профиль Pod Security `restricted` проверен реализацией проверок на всех манифестах `k8s/` и на рендере Helm (dev/staging/prod);
  негативный контроль подтверждает, что проверка ловит небезопасные поды.
* Симулятор NetworkPolicy: 22 нужных потока разрешены, 21 лишний запрещён; DNS по UDP и TCP.
* Ресурсы Vault Secrets Operator (v1.6.1) и Kyverno (1.19) проверены по схемам CRD; `kubeconform --strict`: 169 ресурсов валидны;
  `helm template` для dev/staging/prod (prod без секрета — осознанная ошибка рендера).
* CI: все actions закреплены по SHA (проверяет тест), Trivy блокирует CRITICAL/HIGH.

**Лаб. № 5 — не запускалось** (нет Docker и кластера): реальная работа admission (PSS, Kyverno), применение NetworkPolicy в Calico,
Vault и VSO, cert-manager, Falco, срабатывание алертов безопасности, запуск образов под не-root (особенно PostgreSQL, Redis, RabbitMQ,
SeaweedFS и Flower), результаты Trivy на реальных образах. Выполните шаги и приложите скриншоты.

**Не запускалось** (в среде нет Docker и кластера): сборка образов, `docker compose up`, Minikube, оператор SeaweedFS
и реальное создание бакета, установка kube-prometheus-stack / Loki / Alloy, статус целей Prometheus, отображение
дашбордов в Grafana, срабатывание алертов, Argo CD, работа коллектора `celery_queue_length` и Flower с живым RabbitMQ.
Эти шаги выполните у себя и приложите скриншоты (см. таблицу «Решение проблем»). Остальное — как в лаб. № 3:
KEDA, CNPG, Argo CD и Image Updater в среде сборки не запускались.

## Безопасность (учебные допущения)

Пароли в `k8s/02-secrets.yaml`, `k8s/seaweedfs/s3-credentials.yaml`, `monitoring/grafana-admin-secret.yaml` и
`values.yaml` — учебные (ключи S3 `*-change-me`, Grafana `admin/admin`); в production их выносят из Git.
С лаб. № 5 пароли приложения (`SECRET_KEY`, БД, брокер) хранятся в Vault и в Git не попадают; в репозитории остаются только учебные
значения (bootstrap-администратор, ключи S3, Grafana). Приложению выдаются два набора ключей S3: `admin` (загрузка/удаление) и `reader` (скачивание, presigned URL) — принцип наименьших привилегий. Secret в Kubernetes только закодирован base64;
в production — шифрование etcd и Sealed Secrets / External Secrets / Vault (для Helm — `global.existingSecret`).
Образы запускаются не от root; контейнер PostgreSQL использует штатный entrypoint, который сам понижает привилегии.
