# Usar a imagem UBI Python 3.12 mais recente (versão atual do RHEL 9)
FROM registry.access.redhat.com/ubi9/python-312:latest

LABEL maintainer="SysAdmin Team" \
      description="VM Snapshot Cleanup Tool for OpenShift/KubeVirt" \
      io.k8s.description="Automated cleanup of KubeVirt VM snapshots based on retention policies" \
      io.k8s.display-name="VM Snapshot Cleaner" \
      io.openshift.tags="kubevirt,snapshot,cleanup,python" \
      summary="VM Snapshot Cleanup Tool" \
      version="1.0.0"

# Definir variáveis de ambiente para pip
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UPGRADE_PIP_TO_LATEST=1

# Definir diretório de trabalho
WORKDIR /opt/app-root/src

# Copiar requirements primeiro (para cache de layers)
COPY --chown=1001:0 requirements.txt .

# Atualizar pip e instalar dependências
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copiar aplicação
COPY --chown=1001:0 snapshot_cleaner.py .

# Ajustar permissões (UBI já usa usuário 1001)
RUN chmod +x snapshot_cleaner.py && \
    chmod -R g=u /opt/app-root

# UBI já configura o usuário não-root (1001)
USER 1001

# Comando padrão
CMD ["python", "snapshot_cleaner.py"]
