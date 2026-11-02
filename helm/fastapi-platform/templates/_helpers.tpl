{{/* Метки, общие для ресурсов самого umbrella-чарта */}}
{{- define "fastapi-platform.labels" -}}
app.kubernetes.io/name: fastapi-platform
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: fastapi-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{/* Адреса зависимостей: явный override из global либо имя сервиса subchart */}}
{{- define "fastapi-platform.dbHost" -}}
{{- default (printf "%s-postgres" .Release.Name) .Values.global.database.host -}}
{{- end }}
{{- define "fastapi-platform.redisHost" -}}
{{- default (printf "%s-redis" .Release.Name) .Values.global.redis.host -}}
{{- end }}
{{- define "fastapi-platform.rabbitHost" -}}
{{- default (printf "%s-rabbitmq" .Release.Name) .Values.global.rabbitmq.host -}}
{{- end }}

{{/* Селекторы БД для NetworkPolicy: StatefulSet (app: postgres) и CloudNativePG. */}}
{{- define "np.dbSelectors" }}
- podSelector:
    matchLabels: {app: postgres}
- podSelector:
    matchLabels: {cnpg.io/cluster: postgres-cluster}
{{- end }}
