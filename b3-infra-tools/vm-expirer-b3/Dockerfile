FROM registry.access.redhat.com/ubi9/python-312:latest

LABEL maintainer="SysAdmin Team" \
      description="VM Expirer" \
      io.k8s.description="" \
      io.k8s.display-name="VM Expirer" \
      io.openshift.tags="kubevirt,tools,python" \
      summary="VM Expirer Tool" \
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
COPY --chown=1001:0 app/ .

# Ajustar permissões (UBI já usa usuário 1001)
RUN chmod +x *.py && \
    chmod -R g=u /opt/app-root

# UBI já configura o usuário não-root (1001)
USER 1001

# Expõe porta 8080 (já padrão da imagem)
EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "3", "--timeout", "120", "app:app"]