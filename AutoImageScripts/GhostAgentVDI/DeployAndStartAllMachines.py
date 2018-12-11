'''
This script is to help administrator to deploy and start all test machines.
This script is used when deploying this GhostAgent to a clean server.
'''

import sys
import socket
sys.path.append('..')
from nicu.db import init_db
import nicu.config as config
from nicu.vm import Vmrun, VmwareType
from nicu.ghost import GhostCenter
import util.dbx as dbx


default_os_id = 6 # win 7 64-bit SP1


def list_active_machines():
    """
    List all active machines.
    """
    vm_object = Vmrun(VmwareType.VmWorkstation, 'NotEmpty', 'NotEmpty', 'NotEmpty')
    (vm_cmd, vm_res) = vm_object.list()
    machine_ids = set([])
    for image in vm_res[1:]:
        try:
            machine_name = image.split('\\')[2]
            (machine_id,) = dbx.queryx_table('Machine_Info', 'MachineID',
                "MachineName='%s'" % machine_name, only_one=True)
            machine_ids.add(machine_id)
        except Exception:
            pass
    return machine_ids


def get_os_id(machine_id):
    """
    Get the OS id of specific machine, which will be ghosted to.
    """
    rows = dbx.queryx_table('Machine_Reimage', 'OSID', 'MachineID=%s and OSID=%s' % (machine_id, default_os_id))
    if not rows:
        rows = dbx.queryx_table('Machine_Reimage', 'TOP 1 OSID', 'MachineID=%s' % (machine_id))
    return rows[0][0]


def ghost_inactive_machines():
    """
    Ghost all inactive machines.
    """
    (server_id,) = dbx.queryx_server_id(socket.gethostname())
    machine_ids = list_active_machines()
    ghosted_pair = []
    rows = dbx.queryx_table('Machine_Reimage', 'distinct MachineID', 'ServerID=%s' % (server_id))
    for row in rows:
        machine_id = row[0]
        if machine_id in machine_ids:
            continue
        os_id = get_os_id(machine_id)
        ghosted_pair.append([machine_id, os_id])

    gc = GhostCenter(server_name=socket.gethostname())
    for machine_id, os_id in ghosted_pair:
        print('Ready to ghost machine %s, os %s' % (machine_id, os_id))
        res = gc.ghost_client(machine_id, os_id)
        if res:
            print('Failed to ghost machine %s, os %s: %s' % (machine_id, os_id, res))
    return


if __name__ == '__main__':
    init_db(config.DB_DEFAULT_HOST, config.DB_DEFAULT_USER,
            config.DB_DEFAULT_PASSWORD, config.DB_DEFAULT_DATABASE)
    ghost_inactive_machines()
    print('Finish!')
