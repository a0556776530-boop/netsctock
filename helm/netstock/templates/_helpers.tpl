{{- define "netstock.name" -}}
netstock
{{- end -}}

{{- define "netstock.fullname" -}}
{{ .Release.Name }}-netstock
{{- end -}}

{{- define "netstock.labels" -}}
app.kubernetes.io/name: {{ include "netstock.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "netstock.selectorLabels" -}}
app.kubernetes.io/name: {{ include "netstock.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "netstock.secretName" -}}
{{- if .Values.secret.create -}}
{{ include "netstock.fullname" . }}
{{- else -}}
{{ .Values.secret.existingSecretName }}
{{- end -}}
{{- end -}}
