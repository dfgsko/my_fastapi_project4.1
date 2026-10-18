{{- define "fastapi-worker.fullname" -}}
{{- printf "%s-worker" .Release.Name -}}
{{- end }}

{{- define "fastapi-worker.selectorLabels" -}}
app.kubernetes.io/name: fastapi-worker
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "fastapi-worker.labels" -}}
{{ include "fastapi-worker.selectorLabels" . }}
app.kubernetes.io/component: worker
app.kubernetes.io/part-of: fastapi-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{- define "fastapi-worker.image" -}}
{{- $registry := default "" .Values.global.image.registry -}}
{{- if $registry -}}
{{- printf "%s/%s:%s" $registry .Values.image.repository (toString .Values.image.tag) -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository (toString .Values.image.tag) -}}
{{- end -}}
{{- end }}

{{- define "fastapi-worker.secretName" -}}
{{- default (printf "%s-secrets" .Release.Name) .Values.global.existingSecret -}}
{{- end }}

{{- define "fastapi-worker.configName" -}}
{{- printf "%s-config" .Release.Name -}}
{{- end }}
