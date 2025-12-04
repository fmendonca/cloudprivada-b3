# VM Snapshot Cleanup Tool for OpenShift

Automated cleanup of KubeVirt VirtualMachine snapshots based on retention policies (in hours) and protection tags.

## Configuration

### Environment Variables

| Variable | Default | Description | Examples |
|----------|---------|-------------|----------|
| `SNAPSHOT_RETENTION_HOURS` | `168` (7 days) | Number of hours to retain snapshots | `24` (1 day), `72` (3 days), `720` (30 days) |
| `EXCLUDED_VM_TAGS` | ` ` | Comma-separated tags to exclude VMs from cleanup | `backup=permanent,protected=true` |
| `DRY_RUN` | `false` | If `true`, only simulate without deleting | `true` or `false` |
| `NAMESPACE` | ` ` | Specific namespace (empty = all namespaces) | `production`, `default` |

### Retention Hours Examples

Common retention periods
SNAPSHOT_RETENTION_HOURS: “1”     # 1 hora (testes)
SNAPSHOT_RETENTION_HOURS: “6”     # 6 horas
SNAPSHOT_RETENTION_HOURS: “12”    # 12 horas (meio dia)
SNAPSHOT_RETENTION_HOURS: “24”    # 24 horas (1 dia)
SNAPSHOT_RETENTION_HOURS: “48”    # 48 horas (2 dias)
SNAPSHOT_RETENTION_HOURS: “72”    # 72 horas (3 dias)
SNAPSHOT_RETENTION_HOURS: “168”   # 168 horas (7 dias / 1 semana)
SNAPSHOT_RETENTION_HOURS: “336”   # 336 horas (14 dias / 2 semanas)
SNAPSHOT_RETENTION_HOURS: “720”   # 720 horas (30 dias / 1 mês)
SNAPSHOT_RETENTION_HOURS: “2160”  # 2160 horas (90 dias / 3 meses)


### Example Configurations

#### Short-term snapshots (Development)





## CronJob Schedule Examples

A cada hora
schedule: “0 * * * *”
A cada 2 horas
schedule: “0 */2 * * *”
A cada 6 horas (recomendado para políticas baseadas em horas)
schedule: “0 */6 * * *”
A cada 12 horas
schedule: “0 */12 * * *”
Uma vez por dia às 2h
schedule: “0 2 * * *”
Duas vezes por dia (2h e 14h)
schedule: “0 2,14 * * *”



## Usage Examples

### Run with different retention periods

Teste: deletar snapshots com mais de 1 hora
oc set env cronjob/snapshot-cleaner-cronjob 
SNAPSHOT_RETENTION_HOURS=1 
DRY_RUN=true 
-n vm-snapshot-cleaner
Desenvolvimento: 12 horas
oc set env cronjob/snapshot-cleaner-cronjob 
SNAPSHOT_RETENTION_HOURS=12 
-n vm-snapshot-cleaner
Staging: 3 dias (72 horas)
oc set env cronjob/snapshot-cleaner-cronjob 
SNAPSHOT_RETENTION_HOURS=72 
-n vm-snapshot-cleaner
Produção: 30 dias (720 horas)
oc set env cronjob/snapshot-cleaner-cronjob 
SNAPSHOT_RETENTION_HOURS=720 
-n vm-snapshot-cleaner



### Run locally with specific retention


Snapshots com mais de 2 horas
podman run –rm 
-e SNAPSHOT_RETENTION_HOURS=2 
-e DRY_RUN=true 
-v ~/.kube/config:/tmp/kubeconfig:ro,z 
-e KUBECONFIG=/tmp/kubeconfig 
quay.io/fcalomen/snapshot-cleaner:latest
Snapshots com mais de 1 dia (24 horas)
podman run –rm 
-e SNAPSHOT_RETENTION_HOURS=24 
-e EXCLUDED_VM_TAGS=“backup=permanent” 
-v ~/.kube/config:/tmp/kubeconfig:ro,z 
-e KUBECONFIG=/tmp/kubeconfig 
quay.io/fcalomen/snapshot-cleaner:latest



### Quick reference table

| Retention Period | Hours | ConfigMap Value |
|------------------|-------|-----------------|
| 1 hour | 1 | `"1"` |
| 6 hours | 6 | `"6"` |
| 12 hours | 12 | `"12"` |
| 1 day | 24 | `"24"` |
| 2 days | 48 | `"48"` |
| 3 days | 72 | `"72"` |
| 1 week | 168 | `"168"` |
| 2 weeks | 336 | `"336"` |
| 1 month (~30 days) | 720 | `"720"` |
| 2 months (~60 days) | 1440 | `"1440"` |
| 3 months (~90 days) | 2160 | `"2160"` |
| 6 months (~180 days) | 4320 | `"4320"` |
| 1 year (~365 days) | 8760 | `"8760"` |

## Testing

Test with very short retention (30 minutes)
oc create job –from=cronjob/snapshot-cleaner-cronjob test-30min-$(date +%s) -n vm-snapshot-cleaner
oc set env job/test-30min-* SNAPSHOT_RETENTION_HOURS=0.5 DRY_RUN=true -n vm-snapshot-cleaner

## Watch logs
oc logs -f job/test-30min-* -n vm-snapshot-cleaner



## Monitoring

The logs will now show ages in a more readable format:
- Less than 1 hour: displayed in minutes
- 1-24 hours: displayed in hours
- More than 24 hours: displayed in both days and hours

Example log output:

Analisando snapshot: vm-prod-snapshot-1
	•	Namespace: production
	•	VM Fonte: vm-prod
	•	Idade: 2.34 dias (56.2 horas)
	•	Criado em: 2025-11-15T10:30:00Z
	•	Ação: MANTER (faltam 13.8 horas para expirar)


## Dockerfile Atualizado (Labels)
arquivo:  Dockerfile 

FROM registry.access.redhat.com/ubi9/python-312:latest

LABEL maintainer="SysAdmin Team" \
      description="VM Snapshot Cleanup Tool for OpenShift/KubeVirt (retention in hours)" \
      io.k8s.description="Automated cleanup of KubeVirt VM snapshots based on hour-based retention policies" \
      io.k8s.display-name="VM Snapshot Cleaner (Hours)" \
      io.openshift.tags="kubevirt,snapshot,cleanup,python,retention-hours" \
      summary="VM Snapshot Cleanup Tool with Hour-Based Retention" \
      version="2.0.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UPGRADE_PIP_TO_LATEST=1 \
    SNAPSHOT_RETENTION_HOURS=168

WORKDIR /opt/app-root/src

COPY --chown=1001:0 requirements.txt .

RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

COPY --chown=1001:0 snapshot_cleaner.py .

RUN chmod +x snapshot_cleaner.py && \
    chmod -R g=u /opt/app-root

USER 1001

CMD ["python", "snapshot_cleaner.py"]


## Script de Conversão de Dias para Horas
arquivo:  convert-retention.sh 

#!/bin/bash

echo "=== Conversor de Retenção: Dias → Horas ==="
echo ""

if [ -z "$1" ]; then
    echo "Uso: $0 <dias>"
    echo ""
    echo "Exemplos:"
    echo "  $0 1    # 1 dia = 24 horas"
    echo "  $0 7    # 7 dias = 168 horas"
    echo "  $0 30   # 30 dias = 720 horas"
    exit 1
fi

DAYS=$1
HOURS=$((DAYS * 24))

echo "Retenção de $DAYS dias = $HOURS horas"
echo ""
echo "Para atualizar o ConfigMap:"
echo "oc set env cronjob/snapshot-cleaner-cronjob SNAPSHOT_RETENTION_HOURS=$HOURS -n vm-snapshot-cleaner"
echo ""
echo "Ou edite o ConfigMap:"
echo "oc edit configmap snapshot-cleaner-config -n vm-snapshot-cleaner"
echo ""
echo "Defina: SNAPSHOT_RETENTION_HOURS: \"$HOURS\""


