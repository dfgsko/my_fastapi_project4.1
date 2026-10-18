{{- define "observability.labels" -}}
app.kubernetes.io/name: observability
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: fastapi-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}
{{- define "observability.flowerName" -}}
{{- printf "%s-flower" .Release.Name -}}
{{- end }}
{{- define "observability.secretName" -}}
{{- default (printf "%s-secrets" .Release.Name) .Values.global.existingSecret -}}
{{- end }}
