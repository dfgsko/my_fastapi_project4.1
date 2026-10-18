{{- define "seaweedfs.labels" -}}
app.kubernetes.io/name: seaweedfs
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: fastapi-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}
