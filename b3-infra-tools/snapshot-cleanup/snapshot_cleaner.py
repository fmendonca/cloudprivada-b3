#!/usr/bin/env python3
"""
VM Snapshot Cleanup Script for OpenShift/KubeVirt
Deletes VirtualMachineSnapshots older than specified retention period (in hours),
excluding VMs with specified protection tags.
"""

import os
import sys
import logging
from datetime import datetime, timezone
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SnapshotCleaner:
    """Gerenciador de limpeza de snapshots de VMs"""
    
    def __init__(self):
        """Inicializa o cleaner com variáveis de ambiente"""
        # Carregar configuração do cluster
        try:
            config.load_incluster_config()
            logger.info("Configuração in-cluster carregada com sucesso")
        except config.ConfigException:
            try:
                config.load_kube_config()
                logger.info("Configuração local carregada com sucesso")
            except config.ConfigException:
                logger.error("Não foi possível carregar configuração do Kubernetes")
                sys.exit(1)
        
        # Inicializar API clients
        self.custom_api = client.CustomObjectsApi()
        self.core_api = client.CoreV1Api()
        
        # Variáveis de ambiente - AGORA EM HORAS
        self.retention_hours = int(os.getenv('SNAPSHOT_RETENTION_HOURS', '168'))  # 168h = 7 dias
        self.excluded_tags = os.getenv('EXCLUDED_VM_TAGS', '').split(',')
        self.excluded_tags = [tag.strip() for tag in self.excluded_tags if tag.strip()]
        self.dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'
        self.namespace = os.getenv('NAMESPACE', None)  # None = all namespaces
        
        # Calcular equivalência em dias para exibição
        self.retention_days = self.retention_hours / 24
        
        logger.info(f"Configuração:")
        logger.info(f"  - Retention: {self.retention_hours} horas ({self.retention_days:.2f} dias)")
        logger.info(f"  - Excluded Tags: {self.excluded_tags}")
        logger.info(f"  - Dry Run: {self.dry_run}")
        logger.info(f"  - Namespace: {self.namespace or 'all'}")
    
    def get_vm_tags(self, vm_name, namespace):
        """Obtém as tags/labels de uma VirtualMachine"""
        try:
            vm = self.custom_api.get_namespaced_custom_object(
                group="kubevirt.io",
                version="v1",
                namespace=namespace,
                plural="virtualmachines",
                name=vm_name
            )
            
            labels = vm.get('metadata', {}).get('labels', {})
            annotations = vm.get('metadata', {}).get('annotations', {})
            
            # Combinar labels e annotations para tags
            all_tags = {**labels, **annotations}
            return all_tags
            
        except ApiException as e:
            if e.status == 404:
                logger.warning(f"VM {vm_name} não encontrada no namespace {namespace}")
                return {}
            logger.error(f"Erro ao obter tags da VM {vm_name}: {e}")
            return {}
    
    def is_vm_excluded(self, vm_name, namespace):
        """Verifica se a VM deve ser excluída da limpeza baseado nas tags"""
        if not self.excluded_tags:
            return False
        
        vm_tags = self.get_vm_tags(vm_name, namespace)
        
        # Verificar se alguma das tags de exclusão está presente
        for excluded_tag in self.excluded_tags:
            # Verificar se a tag existe como chave
            if excluded_tag in vm_tags:
                logger.info(f"VM {vm_name} tem tag de exclusão: {excluded_tag}")
                return True
            
            # Verificar se a tag existe como key=value
            if '=' in excluded_tag:
                key, value = excluded_tag.split('=', 1)
                if vm_tags.get(key) == value:
                    logger.info(f"VM {vm_name} tem tag de exclusão: {key}={value}")
                    return True
        
        return False
    
    def calculate_snapshot_age_hours(self, creation_timestamp):
        """Calcula a idade do snapshot em horas (com decimais)"""
        try:
            # Parse do timestamp ISO 8601
            if isinstance(creation_timestamp, str):
                # Remove 'Z' e adiciona '+00:00' para timezone
                if creation_timestamp.endswith('Z'):
                    creation_timestamp = creation_timestamp[:-1] + '+00:00'
                created_time = datetime.fromisoformat(creation_timestamp)
            else:
                created_time = creation_timestamp
            
            # Garantir que está em UTC
            if created_time.tzinfo is None:
                created_time = created_time.replace(tzinfo=timezone.utc)
            
            now = datetime.now(timezone.utc)
            age = now - created_time
            
            # Retornar idade em horas (float para precisão)
            return age.total_seconds() / 3600
            
        except Exception as e:
            logger.error(f"Erro ao calcular idade do snapshot: {e}")
            return 0
    
    def format_age(self, hours):
        """Formata a idade em formato legível"""
        if hours < 1:
            minutes = hours * 60
            return f"{minutes:.1f} minutos"
        elif hours < 24:
            return f"{hours:.1f} horas"
        else:
            days = hours / 24
            return f"{days:.2f} dias ({hours:.1f} horas)"
    
    def list_snapshots(self):
        """Lista todos os snapshots no cluster ou namespace específico"""
        try:
            if self.namespace:
                # Lista snapshots de um namespace específico
                snapshots = self.custom_api.list_namespaced_custom_object(
                    group="snapshot.kubevirt.io",
                    version="v1beta1",
                    namespace=self.namespace,
                    plural="virtualmachinesnapshots"
                )
            else:
                # Lista snapshots de todos os namespaces
                snapshots = self.custom_api.list_cluster_custom_object(
                    group="snapshot.kubevirt.io",
                    version="v1beta1",
                    plural="virtualmachinesnapshots"
                )
            
            return snapshots.get('items', [])
            
        except ApiException as e:
            logger.error(f"Erro ao listar snapshots: {e}")
            return []
    
    def delete_snapshot(self, snapshot_name, namespace):
        """Deleta um snapshot específico"""
        try:
            if self.dry_run:
                logger.info(f"[DRY-RUN] Deletaria snapshot {snapshot_name} no namespace {namespace}")
                return True
            
            self.custom_api.delete_namespaced_custom_object(
                group="snapshot.kubevirt.io",
                version="v1beta1",
                namespace=namespace,
                plural="virtualmachinesnapshots",
                name=snapshot_name
            )
            
            logger.info(f"Snapshot {snapshot_name} deletado com sucesso do namespace {namespace}")
            return True
            
        except ApiException as e:
            logger.error(f"Erro ao deletar snapshot {snapshot_name}: {e}")
            return False
    
    def process_snapshots(self):
        """Processa todos os snapshots e deleta os que atendem aos critérios"""
        logger.info("Iniciando processamento de snapshots...")
        logger.info(f"Critério de retenção: {self.retention_hours} horas ({self.retention_days:.2f} dias)")
        
        snapshots = self.list_snapshots()
        total_snapshots = len(snapshots)
        deleted_count = 0
        excluded_count = 0
        kept_count = 0
        
        logger.info(f"Total de snapshots encontrados: {total_snapshots}")
        
        for snapshot in snapshots:
            metadata = snapshot.get('metadata', {})
            spec = snapshot.get('spec', {})
            
            snapshot_name = metadata.get('name')
            namespace = metadata.get('namespace')
            creation_timestamp = metadata.get('creationTimestamp')
            
            # Obter nome da VM fonte
            source = spec.get('source', {})
            vm_name = source.get('name')
            
            if not vm_name:
                logger.warning(f"Snapshot {snapshot_name} não tem VM fonte definida, pulando...")
                continue
            
            # Calcular idade do snapshot em horas
            age_hours = self.calculate_snapshot_age_hours(creation_timestamp)
            age_formatted = self.format_age(age_hours)
            
            logger.info(f"\nAnalisando snapshot: {snapshot_name}")
            logger.info(f"  - Namespace: {namespace}")
            logger.info(f"  - VM Fonte: {vm_name}")
            logger.info(f"  - Idade: {age_formatted}")
            logger.info(f"  - Criado em: {creation_timestamp}")
            
            # Verificar se a VM está excluída
            if self.is_vm_excluded(vm_name, namespace):
                logger.info(f"  - Ação: MANTER (VM tem tag de proteção)")
                excluded_count += 1
                continue
            
            # Verificar se o snapshot é antigo o suficiente (em horas)
            if age_hours >= self.retention_hours:
                logger.info(f"  - Ação: DELETAR (idade {age_hours:.1f}h >= {self.retention_hours}h)")
                if self.delete_snapshot(snapshot_name, namespace):
                    deleted_count += 1
            else:
                remaining_hours = self.retention_hours - age_hours
                remaining_formatted = self.format_age(remaining_hours)
                logger.info(f"  - Ação: MANTER (faltam {remaining_formatted} para expirar)")
                kept_count += 1
        
        # Resumo final
        logger.info("\n" + "="*60)
        logger.info("RESUMO DA EXECUÇÃO")
        logger.info("="*60)
        logger.info(f"Critério de retenção: {self.retention_hours} horas ({self.retention_days:.2f} dias)")
        logger.info(f"Total de snapshots processados: {total_snapshots}")
        logger.info(f"Snapshots deletados: {deleted_count}")
        logger.info(f"Snapshots mantidos (com tag de proteção): {excluded_count}")
        logger.info(f"Snapshots mantidos (dentro do período de retenção): {kept_count}")
        logger.info("="*60)


def main():
    """Função principal"""
    logger.info("Iniciando VM Snapshot Cleaner...")
    
    cleaner = SnapshotCleaner()
    cleaner.process_snapshots()
    
    logger.info("Execução concluída!")


if __name__ == "__main__":
    main()
