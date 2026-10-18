{{- define "infrastructure.labels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: fastapi-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{- define "infrastructure.secretName" -}}
{{- default (printf "%s-secrets" .Release.Name) .Values.global.existingSecret -}}
{{- end }}

{{- define "infrastructure.configName" -}}
{{- printf "%s-config" .Release.Name -}}
{{- end }}
