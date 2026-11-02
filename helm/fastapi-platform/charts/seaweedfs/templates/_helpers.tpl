{{- define "seaweedfs.labels" -}}
app.kubernetes.io/name: seaweedfs
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: fastapi-platform
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}
{{- define "seaweedfs.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 1000
runAsGroup: 1000
fsGroup: 1000
seccompProfile:
  type: RuntimeDefault
{{- end }}
{{- define "seaweedfs.containerSecurityContext" -}}
allowPrivilegeEscalation: false
capabilities:
  drop: [ALL]
{{- end }}
