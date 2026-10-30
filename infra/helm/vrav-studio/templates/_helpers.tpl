{{- define "vrav.name" -}}
vrav-studio
{{- end -}}

{{- define "vrav.labels" -}}
app.kubernetes.io/name: {{ include "vrav.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
{{- end -}}
