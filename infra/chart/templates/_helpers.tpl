{{- define "lasteverlm.labels" -}}
app.kubernetes.io/part-of: lasteverlm
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{- define "lasteverlm.image" -}}
{{ .root.Values.registry }}/lasteverlm-{{ .name }}:{{ .root.Values.imageTag }}
{{- end }}

{{- define "lasteverlm.securityContext" -}}
allowPrivilegeEscalation: false
runAsNonRoot: true
{{- with .runAsUser }}
runAsUser: {{ . }}
{{- end }}
capabilities:
  drop: ["ALL"]
{{- end }}

{{- define "lasteverlm.envFrom" -}}
- configMapRef:
    name: lasteverlm-config
{{- range .secrets }}
- secretRef:
    name: {{ . }}
{{- end }}
{{- range .optionalSecrets }}
- secretRef:
    name: {{ . }}
    optional: true
{{- end }}
{{- end }}

{{- define "lasteverlm.hpa" -}}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ .name }}
  labels:
    {{- include "lasteverlm.labels" .root | nindent 4 }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ .name }}
  minReplicas: {{ .hpa.min }}
  maxReplicas: {{ .hpa.max }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .hpa.cpu }}
{{- end }}

{{- define "lasteverlm.pgCaVolumeMount" -}}
- name: pg-ca
  mountPath: {{ .Values.pgCa.mountPath }}
  readOnly: true
{{- end }}

{{- define "lasteverlm.pgCaVolume" -}}
- name: pg-ca
  configMap:
    name: {{ .Values.pgCa.configMap }}
{{- end }}
