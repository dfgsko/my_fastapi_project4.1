# Educational Platform API — Курсы, студенты и зачисления

Вариант 8 («Курсы и студенты»). Проект прошёл четыре лабораторные работы:

| Лаб. | Что сделано | Где описано |
|------|-------------|-------------|
| №1–2 | REST API на FastAPI, SQLAlchemy, кэш и rate limiting в Redis, Celery-задача генерации сертификатов, админ-панель | [docs/LAB1-2.md](docs/LAB1-2.md) (эндпоинты, модель данных, примеры запросов) |
| №3 | PostgreSQL, RabbitMQ, Kubernetes (Minikube), Helm umbrella-чарт, KEDA, CloudNativePG, Argo CD, Image Updater, GitHub Actions | разделы «Kubernetes» … «CI» ниже |
| **№4** | **Наблюдаемость и S3: Prometheus, Grafana, Alertmanager, Loki, Alloy, Flower, SeaweedFS (S3 API)** | раздел «Лабораторная № 4» ниже |

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
pytest -v          # 42 теста: SQLite in-memory, fake Redis, Celery в eager-режиме
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

## CI (GitHub Actions)

`.github/workflows/ci.yml`: `pytest` → `helm lint` + `helm template` (в т.ч. без SeaweedFS и мониторинга) →
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

* `pytest` — 133 теста (API, метрики, S3-роутер на имитации клиента, воркер, согласованность конфигов), `flake8`.
* Реальный код `app/s3_client.py` прогнан против S3-совместимого сервера (moto): загрузка, скачивание, список, presigned URL, удаление, 404.
* Helm 3.10: `helm lint` и `helm template` для dev / staging / prod и с отключёнными `seaweedfs` / `observability`.
* `kubeconform --strict`: 99 ресурсов (манифесты `k8s/`, `monitoring/`, рендер чартов, включая `ServiceMonitor`) валидны.
* Ресурсы `Seaweed`, `Bucket`, `BucketLifecyclePolicy` (манифесты и рендер Helm) соответствуют схемам CRD оператора SeaweedFS.
* `alloy validate` (Alloy v1.20.1) для конфигурации сбора логов; `kustomize build monitoring/`.
* Все PromQL-запросы дашбордов и алертов разбираются парсером Prometheus; метрики в них действительно экспортируются приложением.

**Не запускалось** (в среде нет Docker и кластера): сборка образов, `docker compose up`, Minikube, оператор SeaweedFS
и реальное создание бакета, установка kube-prometheus-stack / Loki / Alloy, статус целей Prometheus, отображение
дашбордов в Grafana, срабатывание алертов, Argo CD, работа коллектора `celery_queue_length` и Flower с живым RabbitMQ.
Эти шаги выполните у себя и приложите скриншоты (см. таблицу «Решение проблем»). Остальное — как в лаб. № 3:
KEDA, CNPG, Argo CD и Image Updater в среде сборки не запускались.

## Безопасность (учебные допущения)

Пароли в `k8s/02-secrets.yaml`, `k8s/seaweedfs/s3-credentials.yaml`, `monitoring/grafana-admin-secret.yaml` и
`values.yaml` — учебные (ключи S3 `*-change-me`, Grafana `admin/admin`); в production их выносят из Git.
Приложению выдаются два набора ключей S3: `admin` (загрузка/удаление) и `reader` (скачивание, presigned URL) — принцип наименьших привилегий. Secret в Kubernetes только закодирован base64;
в production — шифрование etcd и Sealed Secrets / External Secrets / Vault (для Helm — `global.existingSecret`).
Образы запускаются не от root; контейнер PostgreSQL использует штатный entrypoint, который сам понижает привилегии.
