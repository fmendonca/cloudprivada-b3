from __future__ import annotations
from typing import List, Dict, Any
import os
import requests
from kubernetes import config, dynamic
from kubernetes.client import api_client
from kubernetes.dynamic.exceptions import NotFoundError, ResourceNotFoundError
from datetime import datetime

DEBUG_GUESTOSINFO = os.environ.get("DEBUG_GUESTOSINFO", "0") == "1"


def load_kube_config() -> None:
    config.load_incluster_config()


def get_dynamic_client() -> dynamic.DynamicClient:
    return dynamic.DynamicClient(api_client.ApiClient())


def list_vms_all_namespaces() -> List[Any]:
    """Lista todas VirtualMachines (ligadas e desligadas)."""
    try:
        dyn_client = get_dynamic_client()
        vm_api = dyn_client.resources.get(
            api_version="kubevirt.io/v1",
            kind="VirtualMachine",
        )
        vm_list = vm_api.get(namespace=None)
        return vm_list.items
    except (NotFoundError, ResourceNotFoundError):
        return []
    except Exception as e:
        if DEBUG_GUESTOSINFO:
            print(f"Erro listando VMs: {e}")
        return []


def list_vmis_all_namespaces() -> List[Any]:
    """Lista todas VirtualMachineInstances (apenas VMs ligadas)."""
    try:
        dyn_client = get_dynamic_client()
        vmi_api = dyn_client.resources.get(
            api_version="kubevirt.io/v1",
            kind="VirtualMachineInstance",
        )
        vmis_list = vmi_api.get(namespace=None)
        return vmis_list.items
    except (NotFoundError, ResourceNotFoundError):
        return []
    except Exception as e:
        if DEBUG_GUESTOSINFO:
            print(f"Erro listando VMIs: {e}")
        return []


def get_guestosinfo_http(namespace: str, name: str) -> Dict[str, Any]:
    """Chama guestosinfo via HTTP direto, usando service account do pod (só faz sentido para VMs ligadas)."""
    try:
        host = os.environ.get("KUBERNETES_SERVICE_HOST")
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        if not host:
            raise RuntimeError("KUBERNETES_SERVICE_HOST não definido")

        api_server = f"https://{host}:{port}"

        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

        with open(token_path, "r", encoding="utf-8") as f:
            token = f.read().strip()

        url = (
            f"{api_server}"
            f"/apis/subresources.kubevirt.io/v1/namespaces/{namespace}"
            f"/virtualmachineinstances/{name}/guestosinfo"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        if DEBUG_GUESTOSINFO:
            print(f"DEBUG guestosinfo URL: {url}")

        resp = requests.get(url, headers=headers, verify=ca_path, timeout=10)

        if DEBUG_GUESTOSINFO:
            print(f"DEBUG guestosinfo status: {resp.status_code}")
            print(f"DEBUG guestosinfo raw text: {resp.text}")

        if resp.status_code == 200:
            data = resp.json()
            if DEBUG_GUESTOSINFO:
                import json
                print("DEBUG guestosinfo JSON pretty:")
                print(json.dumps(data, indent=2, sort_keys=True))
            return data
        else:
            if DEBUG_GUESTOSINFO:
                print(
                    f"guestosinfo {namespace}/{name} falhou: "
                    f"{resp.status_code} {resp.text}"
                )
            return {}
    except Exception as e:
        if DEBUG_GUESTOSINFO:
            print(f"Erro guestosinfo {namespace}/{name}: {e}")
        return {}


def vmi_to_status_dict(vmi: Any) -> Dict[str, Any]:
    """Converte VMI em dict de status simplificado (usado quando VM está ligada)."""
    if not vmi or not vmi.status:
        return {}

    status = vmi.status.to_dict()
    result: Dict[str, Any] = {}

    # phase
    result["phase"] = status.get("phase")

    # nodeName
    result["nodeName"] = status.get("nodeName", "")

    # conditions -> AgentConnected
    agent_instalado = "Não"
    for cond in status.get("conditions", []):
        if cond.get("type") == "AgentConnected" and cond.get("status") == "True":
            agent_instalado = "Sim"
            break
    result["agent_instalado"] = agent_instalado

    # boot_start: fase Running em phaseTransitionTimestamps
    boot_start = ""
    pts = status.get("phaseTransitionTimestamps", [])
    for item in pts:
        if item.get("phase") == "Running":
            ts = item.get("phaseTransitionTimestamp")
            if ts:
                try:
                    if ts.endswith("Z"):
                        ts = ts[:-1]
                    dt = datetime.fromisoformat(ts)
                    boot_start = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    boot_start = ts
            break
    result["boot_start"] = boot_start

    # guestOSInfo
    os_name = ""
    guest_os_status = status.get("guestOSInfo", {})
    if guest_os_status:
        os_name = guest_os_status.get("prettyName") or guest_os_status.get("name", "")
    result["os_name"] = os_name

    # IP: interfaces[0].ipAddress
    vm_ip = ""
    interfaces = status.get("interfaces", [])
    if interfaces:
        vm_ip = interfaces[0].get("ipAddress", "")
    result["vm_ip"] = vm_ip

    return result


def vm_to_row(vm: Any, vmi_status: Dict[str, Any] | None, guest_info: Dict[str, Any] | None) -> Dict[str, str]:
    """
    Monta a linha da tabela a partir da VirtualMachine,
    usando info de VMI (se existir) e guestosinfo (se VM estiver ligada).
    """
    metadata = vm.metadata.to_dict()
    name = metadata.get("name", "Unknown")
    namespace = metadata.get("namespace", "Unknown")

    # Se tem VMI, está ligada; se não, está desligada
    has_vmi = vmi_status is not None and vmi_status != {}
    state = "Ligado" if has_vmi else "Desligado"

    # Defaults
    boot_start = ""
    os_name = ""
    node_running = ""
    agent_instalado = "Não"
    agent_version = ""
    vm_ip = ""

    if has_vmi:
        boot_start = vmi_status.get("boot_start", "")
        os_name = vmi_status.get("os_name", "")
        node_running = vmi_status.get("nodeName", "")
        agent_instalado = vmi_status.get("agent_instalado", "Não")
        vm_ip = vmi_status.get("vm_ip", "")

        if guest_info:
            agent_version = guest_info.get("guestAgentVersion", "")

    return {
        "name": name,
        "namespace": namespace,
        "state": state,
        "boot_start": boot_start,
        "os_name": os_name,
        "node_running": node_running,
        "agent_instalado": agent_instalado,
        "agent_version": agent_version,
        "vm_ip": vm_ip,
    }


def collect_data() -> List[Dict[str, str]]:
    """Coleta dados de todas VMs (ligadas e desligadas)."""
    load_kube_config()

    vms = list_vms_all_namespaces()
    vmis = list_vmis_all_namespaces()

    # Índice VMI por (namespace, name) para lookup rápido
    vmi_index: Dict[tuple[str, str], Any] = {}
    for vmi in vmis:
        vmi_index[(vmi.metadata.namespace, vmi.metadata.name)] = vmi

    if DEBUG_GUESTOSINFO:
        print(f"Encontradas {len(vms)} VMs e {len(vmis)} VMIs")

    rows: List[Dict[str, str]] = []

    for vm in vms:
        ns = vm.metadata.namespace
        name = vm.metadata.name

        vmi = vmi_index.get((ns, name))
        vmi_status = vmi_to_status_dict(vmi) if vmi else None

        guest_info: Dict[str, Any] | None = None
        if vmi:
            guest_info = get_guestosinfo_http(ns, name)

        row = vm_to_row(vm, vmi_status, guest_info)
        rows.append(row)

    return rows
