{{/*
Expand the name of the chart.
*/}}
{{- define "agent-security-lab.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited
to this (by the DNS naming spec). If release name contains chart name it
will be used as a full name.
*/}}
{{- define "agent-security-lab.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels applied to all resources.
*/}}
{{- define "agent-security-lab.labels" -}}
app.kubernetes.io/name: {{ include "agent-security-lab.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: agent-security-lab
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Selector labels — the minimal set used in matchLabels and service selectors.
*/}}
{{- define "agent-security-lab.selectorLabels" -}}
app.kubernetes.io/name: {{ include "agent-security-lab.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
