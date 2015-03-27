from usm_rest_api.models import Host
from usm_rest_api.models import DiscoveredNode
from usm_wrappers import utils as usm_wrapper_utils


def check_minion_is_new(minion_id):
    new = True
    in_host_list = Host.objects.filter(node_name__exact=minion_id)
    in_free_pool = DiscoveredNode.objects.filter(node_name__exact=minion_id)
    if in_host_list or in_free_pool:
        new = False
    return new


def add_minion_to_free_pool(minion_id):
    node = DiscoveredNode(
        node_name=minion_id,
        management_ip=usm_wrapper_utils.resolve_hostname(minion_id))
    node.save()
