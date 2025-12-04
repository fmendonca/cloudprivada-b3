import logging
import os
import threading
import time
from datetime import datetime, timedelta
from dateutil import parser
from flask import Flask, render_template, jsonify, request
from kubernetes import client, config
from kubernetes.client.rest import ApiException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Caminho ABSOLUTO para templates
template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=template_dir)

logger.info(f"Template folder configurado: {template_dir}")

class VMManager:
    def __init__(self):
        try:
            config.load_incluster_config()
        except Exception:
            config.load_kube_config()
        
        self.v1_api = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()
        self.group = "kubevirt.io"
        self.version = "v1"
        self.plural = "virtualmachines"
    
    def get_all_namespaces(self):
        try:
            ns_list = self.v1_api.list_namespace()
            return [item.metadata.name for item in ns_list.items]
        except ApiException as e:
            logger.error(f"Erro ao listar namespaces: {e}")
            return []
    
    def get_vms_in_namespace(self, namespace):
        try:
            vms = self.custom_api.list_namespaced_custom_object(
                group=self.group,
                version=self.version,
                namespace=namespace,
                plural=self.plural
            )
            return vms.get('items', [])
        except ApiException as e:
            logger.warning(f"Erro ao listar VMs na namespace {namespace}: {e}")
            return []
    
    def is_vm_expired(self, vm):
        labels = vm.get('metadata', {}).get('labels', {})
        expire_days = labels.get('expire')
        if not expire_days:
            return False
        
        try:
            expire_days = int(expire_days)
            creation_timestamp = vm['metadata'].get('creationTimestamp')
            if not creation_timestamp:
                return False
            
            # Remove timezone para comparação segura
            created_time = parser.parse(creation_timestamp).replace(tzinfo=None)
            expire_time = created_time + timedelta(days=expire_days)
            now = datetime.utcnow().replace(tzinfo=None)
            
            return now >= expire_time
        except Exception as e:
            logger.error(f"Erro ao calcular expiração para VM {vm['metadata']['name']}: {e}")
            return False
    
    def delete_vm(self, namespace, vm_name):
        try:
            self.custom_api.delete_namespaced_custom_object(
                name=vm_name,
                group=self.group,
                version=self.version,
                namespace=namespace,
                plural=self.plural
            )
            logger.info(f"✅ VM {vm_name} DELETADA na namespace {namespace}")
            return True
        except ApiException as e:
            logger.error(f"Erro ao deletar VM {vm_name}: {e}")
            return False
    
    def scan_and_cleanup(self):
        """Executa scan completo e retorna resultados"""
        deleted_count = 0
        total_vms_checked = 0
        namespaces = self.get_all_namespaces()
        
        logger.info(f"🚀 INICIANDO SCAN AUTOMÁTICO - {len(namespaces)} namespaces")
        
        for namespace in namespaces:
            vms = self.get_vms_in_namespace(namespace)
            total_vms_checked += len(vms)
            
            for vm in vms:
                vm_name = vm['metadata']['name']
                expire_label = vm.get('metadata', {}).get('labels', {}).get('expire')
                
                if expire_label:
                    logger.info(f"  📋 VM: {vm_name} (expire={expire_label})")
                
                if self.is_vm_expired(vm):
                    logger.info(f"  🗑️  VM {vm_name} EXPIRADA! Deletando...")
                    if self.delete_vm(namespace, vm_name):
                        deleted_count += 1
        
        logger.info(f"🎉 SCAN CONCLUÍDO: {len(namespaces)} ns, {total_vms_checked} VMs, {deleted_count} deletadas")
        
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'total_namespaces': len(namespaces),
            'total_vms_checked': total_vms_checked,
            'deleted_vms': deleted_count
        }

# Instância global
vm_manager = VMManager()

# 🔄 SCAN AUTOMÁTICO A CADA 1 HORA
auto_scan_thread = None
AUTO_SCAN_INTERVAL = 3600  # 1 hora em segundos

def auto_scan_loop():
    """Loop automático de scan a cada hora"""
    global auto_scan_thread
    while True:
        try:
            logger.info("⏰ EXECUTANDO SCAN AUTOMÁTICO (1h)")
            result = vm_manager.scan_and_cleanup()
            logger.info(f"✅ SCAN AUTOMÁTICO CONCLUÍDO: {result}")
        except Exception as e:
            logger.error(f"❌ ERRO no scan automático: {e}")
        time.sleep(AUTO_SCAN_INTERVAL)

def start_auto_scan():
    """Inicia thread de scan automático"""
    global auto_scan_thread
    if auto_scan_thread is None or not auto_scan_thread.is_alive():
        auto_scan_thread = threading.Thread(target=auto_scan_loop, daemon=True)
        auto_scan_thread.start()
        logger.info("▶️ SCAN AUTOMÁTICO INICIADO (1h)")
    return True

# Inicia scan automático ao boot
start_auto_scan()

@app.route('/')
def index():
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Erro ao carregar index.html: {e}")
        return f"ERRO: {str(e)}", 500

@app.route('/scan', methods=['POST'])
def manual_scan():
    """Scan manual sob demanda"""
    try:
        result = vm_manager.scan_and_cleanup()
        return jsonify({
            'success': True,
            'message': 'Scan manual concluído',
            'data': result,
            'auto_scan': 'ativo (1h)'
        })
    except Exception as e:
        logger.error(f"Erro no scan manual: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/status')
def status():
    """Status do scan automático"""
    return jsonify({
        'auto_scan': 'ativo',
        'interval': '1 hora',
        'next_scan': 'em até 60min',
        'last_scan': 'automático em execução'
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'auto_scan': 'running'})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080, debug=True)
