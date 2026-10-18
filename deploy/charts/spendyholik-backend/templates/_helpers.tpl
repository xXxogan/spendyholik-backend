{{/*
Common labels.
*/}}
{{- define "spendyholik-backend.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "spendyholik-backend.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Release name, or "<release>-<chart>" when the release name does not already
contain the chart name (release "spendyholik-backend" → "spendyholik-backend").
*/}}
{{- define "spendyholik-backend.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{ .Release.Name | trunc 50 | trimSuffix "-" }}
{{- else -}}
{{ printf "%s-%s" .Release.Name .Chart.Name | trunc 50 | trimSuffix "-" }}
{{- end -}}
{{- end }}

{{- define "spendyholik-backend.image" -}}
{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}
{{- end }}

{{/*
Host header for kubelet probes: Django rejects hosts outside ALLOWED_HOSTS, and
kubelet would otherwise send the pod IP.
*/}}
{{- define "spendyholik-backend.probeHost" -}}
{{- splitList "," .Values.env.ALLOWED_HOSTS | first | trim -}}
{{- end }}

{{/*
envFrom block shared by every app container.
*/}}
{{- define "spendyholik-backend.envFrom" -}}
- configMapRef:
    name: {{ include "spendyholik-backend.fullname" . }}-env
- secretRef:
    name: {{ include "spendyholik-backend.fullname" . }}-secret
{{- end }}
