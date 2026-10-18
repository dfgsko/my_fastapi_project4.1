# Подготовка к защите (лаб. №3 и №4)

Сценарий демонстрации (5 минут): `kubectl get pods -n fastapi-app` → Swagger → логи воркера после
`PATCH /enrollments/{id}/complete` → `python scripts/load_test.py --count 100` и рост подов воркера
(KEDA) → Argo CD UI (Synced / Healthy) → что произойдёт при `git push`.

## Контрольные вопросы

**1. Deployment vs StatefulSet. Что выбрано для PostgreSQL?**
Deployment — взаимозаменяемые поды без состояния (случайные имена, общий том или без тома).
StatefulSet даёт каждому поду стабильное имя (`postgres-0`), упорядоченный запуск и собственный PVC
(`volumeClaimTemplates`), который переживает пересоздание пода. БД хранит состояние на диске, поэтому
StatefulSet; в HA-варианте — CloudNativePG, который сам управляет репликацией и failover. Redis и RabbitMQ
в лабе — Deployment, т. к. критичных данных не хранят (очередь при потере брокера можно перепоставить).

**2. Что произойдёт с подами FastAPI, если обновить образ в Git?**
Image Updater (или CI) коммитит новый тег в `environments/<env>/values.yaml` → Argo CD замечает расхождение
Git ↔ кластер → применяет обновлённый Deployment → Kubernetes делает rolling update: поднимает новый под
(`maxSurge: 1`), ждёт `/ready`, только потом гасит старый (`maxUnavailable: 0`) → простоя нет.
Перед этим Helm-хук запускает Job миграций.

**3. Зачем TriggerAuthentication, если в RabbitMQ уже есть пароль?**
Чтобы не хранить креды открытым текстом в ScaledObject: KEDA читает их из Secret. Права на Secret и на
ScaledObject можно разделять (RBAC), секрет можно ротировать/подтягивать из внешнего хранилища, не трогая
описание масштабирования.

**4. Как Argo CD понимает, что кластер разошёлся с Git? Что делает `selfHeal: true`?**
Он периодически (и по webhook) рендерит манифесты из Git (`helm template`) и сравнивает их с живыми
объектами кластера (diff). Различие → статус OutOfSync. При `automated` он применяет Git-состояние сам;
`selfHeal: true` откатывает и ручные правки в кластере (например `kubectl scale`), `prune: true` удаляет
ресурсы, которых больше нет в Git.

**5. Почему Secret не «секретный»? Как исправить в production?**
Значения лежат в etcd в base64 — это кодирование, любой с правом `get secret` прочитает их. Исправление:
шифрование etcd (EncryptionConfiguration/KMS), строгий RBAC, внешние менеджеры — Vault, External Secrets,
Sealed Secrets (в Git лежит только зашифрованный вариант). В чарте для этого есть `global.existingSecret`.

**6. Что такое sync waves и зачем?**
Аннотация `argocd.argoproj.io/sync-wave` задаёт порядок применения ресурсов: сначала меньшие номера, следующая
волна ждёт Healthy предыдущей. У нас: `-1` ConfigMap/Secret/PostgreSQL → `0` Redis/RabbitMQ → миграции →
`1` API → `2` воркеры/KEDA. Без этого API мог бы стартовать раньше БД.

## Вопросы для закрепления (кратко)

- **PVC у PostgreSQL, но не у Redis:** данные БД — источник истины; Redis — кэш/счётчики, их потеря не критична.
- **Liveness падает / readiness падает:** liveness → под перезапускается; readiness → под убирается из
  балансировки, но живёт. Поэтому `/health` не проверяет БД: перезапуск API не починит чужую БД.
- **`serviceName` в StatefulSet:** governing-service даёт подам стабильные DNS-имена (`postgres-0.postgres`).
- **Почему у воркера exec-проба:** нет HTTP-сервера; `celery inspect ping -d celery@$HOSTNAME` проверяет,
  что именно этот воркер отвечает брокеру. `timeoutSeconds` пришлось увеличить: у exec-пробы по умолчанию 1 с.
- **Зачем Helm при наличии `kubectl apply`:** параметризация (dev/prod values), одна команда на весь стек,
  версии релизов и `helm rollback`, отключение компонентов через `condition`.
- **Как KEDA отдаёт метрику в HPA:** KEDA-оператор опрашивает RabbitMQ, публикует длину очереди как external
  metric через свой metrics-apiserver и создаёт обычный HPA, который считает `ceil(длина / value)` реплик.
- **`minReplicaCount: 0`:** воркеры полностью останавливаются при пустой очереди; первая задача ждёт запуска
  пода. Для dev — экономия, для production с требованиями к задержке — риск.
- **Почему не HPA по CPU для Celery:** воркер простаивает в ожидании задач и пиково грузит CPU на секунды;
  длина очереди — прямая мера невыполненной работы.
- **`semver ~1.2` вместо `newest-build`:** newest-build возьмёт любой свежий тег (в т. ч. нестабильную сборку),
  semver с ограничением допустит только патчи стабильной минорной версии.
- **Push vs pull деплой:** push — CI применяет манифесты и держит kubeconfig; pull — Argo CD внутри кластера
  забирает изменения из Git, доступ к кластеру из CI не нужен.

## Лабораторная № 4: вопросы для самопроверки

1. **Чем SeaweedFS отличается от MinIO?** Оба дают S3 API. SeaweedFS — Apache 2.0, написан на Go, хранит данные
   в больших «томах» (мелкие файлы не создают по inode на объект), состоит из master (раздаёт тома), volume-серверов
   (данные), filer (дерево каталогов/метаданные) и S3-шлюза; для Kubernetes есть оператор с CRD `Seaweed` и `Bucket`.
   Команды уходят от MinIO из-за смены модели распространения и лицензирования (риск vendor lock-in).
   В проекте приложение не меняется при смене хранилища: используется только boto3 + `S3_ENDPOINT`.
2. **Что такое ServiceMonitor и как Prometheus находит цели?** Это CRD Prometheus Operator: селектор по меткам
   Service, `namespaceSelector` и список `endpoints` (именованный порт, путь, интервал). Оператор по нему генерирует
   конфигурацию скрейпа (service discovery через Kubernetes API) и перезагружает Prometheus. Prometheus берёт только те
   ServiceMonitor, что подходят под `serviceMonitorSelector`; `serviceMonitorSelectorNilUsesHelmValues: false`
   снимает ограничение «метка `release`». У нас: метка `app: fastapi` и порт `http` у `fastapi-service`.
3. **Почему Loki не индексирует полный текст?** Он индексирует только метки (`namespace`, `pod`, `app`), а строки лога
   хранит сжатыми чанками. Индекс маленький, запись и хранение дешёвые. Цена — запрос читает чанки выбранных потоков,
   поэтому метки должны быть стабильными и низкой кардинальности (нельзя ставить в метку id запроса).
4. **Как Alloy собирает логи со всех подов?** `discovery.kubernetes` получает список подов, `discovery.relabel`
   превращает метаданные в метки и отбрасывает системные namespace, `loki.source.kubernetes` читает логи через
   Kubernetes API (`pods/log`), `loki.write` отправляет их в `loki-gateway`. Достаточно одного пода (Deployment);
   DaemonSet с чтением файлов нужен, когда логи читают с диска каждого узла.
5. **Три столпа наблюдаемости.** Метрики (числа во времени: `http_requests_total`, `celery_queue_length` — Prometheus),
   логи (события: ошибки API, «Сертификат сгенерирован» — Loki), трейсы (путь одного запроса через сервисы: API →
   RabbitMQ → воркер → S3 — OpenTelemetry/Tempo; в проекте пока не реализованы, это тема следующей работы).
6. **Алерт на высокий процент 5xx.** `sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) > 0.05`
   с `for: 5m`, меткой `severity: critical`. Важно: статусы не должны быть сгруппированы в `5xx` (см. `app/metrics.py`),
   а `sum` нужен, чтобы доля считалась по всем репликам. Алерт попадает в Alertmanager, который группирует, подавляет
   дубли и отправляет в receiver.
7. **Отказоустойчивость SeaweedFS.** Master кворумом raft (3 реплики), несколько volume-серверов и репликация томов
   (`defaultReplication`, формат `xyz`: `001` — копия на другом сервере той же стойки), filer с метаданными во внешней БД,
   несколько S3-шлюзов (stateless). В нашем Minikube по одной реплике каждого компонента — это учебная конфигурация
   без отказоустойчивости: данные живут на PVC, но потеря узла означает потерю доступа.

**Вопросы по реализации**

- **Почему `status` не группируется?** Instrumentator по умолчанию пишет `2xx/4xx/5xx`; регулярка `5..` из алертов
  не совпала бы. Тест `test_status_codes_are_not_grouped` фиксирует это.
- **Откуда `celery_queue_length`, если Celery метрик не отдаёт?** Кастомный коллектор в `app/metrics.py`: при скрейпе делает
  пассивный `queue_declare` к RabbitMQ (очередь не создаёт и не меняет). Реплики API публикуют одно и то же значение,
  поэтому в запросах — `max(...)`.
- **Зачем два набора S3-ключей?** `admin` пишет/удаляет, `reader` только скачивает и подписывает ссылки (least privilege).
  Ключи сервера (`seaweedfs-s3-config`) и приложения (`app-s3-secrets`) обязаны совпадать — проверяет тест.
- **Почему в методичке Bucket не применяется?** Схема CRD оператора изменилась: `clusterRef` вместо `seaweedRef`,
  `name` вместо `bucketName`, `quota.size`, `versioning` — строка (`Off`). Манифест из методички не проходит проверку по схеме.
- **Почему стек мониторинга не в umbrella-чарте приложения?** У Prometheus Operator, Loki и Alloy свои CRD, namespace и
  жизненный цикл (как у CNPG и KEDA). В umbrella — только то, что относится к приложению: ServiceMonitor и Flower.

**Если что-то не запустилось (лаб. № 4):** см. таблицу «Решение проблем» в README, раздел «Лабораторная № 4».

## Если что-то не запустилось

| Симптом | Причина / решение |
|---------|-------------------|
| `ImagePullBackOff` на `fastapi-app:latest` | образы собраны не в Docker Minikube: выполните `eval $(minikube docker-env)` и пересоберите |
| `CrashLoopBackOff` у API | `kubectl logs -l app=fastapi -n fastapi-app`: чаще всего БД/Redis ещё не готовы или неверный `DATABASE_HOST` |
| Под API Running, но `0/1` | `/ready` = 503: проверьте Redis и PostgreSQL (`curl` на `/ready` покажет, что именно) |
| В БД нет таблиц | не отработал Job миграций: `kubectl logs job/db-migrate -n fastapi-app`; пересоздать: `kubectl delete job db-migrate -n fastapi-app && kubectl apply -f k8s/20-migrate-job.yaml` |
| `kubectl apply` на Job: `field is immutable` | сначала удалите Job (см. выше) |
| Воркер перезапускается по liveness | брокер недоступен или `timeoutSeconds` слишком мал для `celery inspect ping` |
| KEDA не масштабирует | `kubectl describe scaledobject -n fastapi-app`; нет CRD → установите KEDA; неверные креды в `keda-rabbitmq-secret` |
| 429 при нагрузочном тесте | лимит 5 запросов/мин на студента; `load_test.py` создаёт нового студента на каждую задачу |
| Argo CD: ошибка зависимостей Helm | выполните `helm dependency update helm/fastapi-platform` и закоммитьте `Chart.lock` и `charts/*.tgz` |
| Argo CD: `ComparisonError` по пути values | проверьте `repoURL`, ветку и что файл `environments/<env>/values.yaml` закоммичен |
