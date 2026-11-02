{{- define "fastapi-api.fullname" -}}
{{- printf "%s-api" .Release.Name -}}
{{- end }}

{{- define "fastapi-api.selectorLabels" -}}
app.kubernetes.io/name: fastapi-api
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "fastapi-api.labels" -}}
{{ include "fastapi-api.selectorLabels" . }}
app.kubernetes.io/component: api
app.kubernetes.io/part-of: fastapi-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{/* Полное имя образа: [registry/]repository:tag */}}
{{- define "fastapi-api.image" -}}
{{- $registry := default "" .Values.global.image.registry -}}
{{- if $registry -}}
{{- printf "%s/%s:%s" $registry .Values.image.repository (toString .Values.image.tag) -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository (toString .Values.image.tag) -}}
{{- end -}}
{{- end }}

{{/* Имя Secret: готовый (existingSecret) или создаваемый umbrella-чартом */}}
{{- define "fastapi-api.secretName" -}}
{{- default (printf "%s-secrets" .Release.Name) .Values.global.existingSecret -}}
{{- end }}

{{- define "fastapi-api.configName" -}}
{{- printf "%s-config" .Release.Name -}}
{{- end }}
{{- define "fastapi-api.bootstrapSecret" -}}
{{- default (printf "%s-bootstrap" .Release.Name) .Values.global.bootstrap.existingSecret -}}
{{- end }}
