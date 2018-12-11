'''
This script is to help administrator to create or clean up the invertory list of VMWare Workstation.

Since that there is no open interface to update the invertory list of VMWare Workstation dynamically,
we should close all active virtual machines before executing this script.
Otherwise, it won't take any effect.

This script will be used for three purposes:
1. Add all template virtual machines into invertory list.
2. Remove all temporary virtual machines (which is inexistent now) from invertory list.
3. Close all tabs except the home tab.

Additionally, the generated invertory.vmls and preferences.ini actually don't match all tokens as
the setting of the virtual machines. However, once administrator click one virtual machine on
VMWare Workstation, all will be updated again by VMWare Workstation, while the folder structure
is reserved as we expected.
'''

import os
import sys
import shutil
import socket
import uuid
import subprocess
sys.path.append('..')
from nicu.db import init_db, SQLServerDB
import nicu.config as config


config_dir = os.path.join(os.environ['APPDATA'], 'VMWare')
backup_dir = os.path.join(config_dir, 'Backup')
inventory_info = [] # [[vmlist], [vmlist, index], ...]


def process_exists(processname):
    '''
    Only works for windows platform.
    '''
    tlcall = 'TASKLIST', '/FI', 'imagename eq %s' % processname
    tlproc = subprocess.Popen(tlcall, shell=True, stdout=subprocess.PIPE)
    tlout = tlproc.communicate()[0].strip().split('\r\n')
    # if TASKLIST returns single line without processname: it's not running
    if len(tlout) > 1 and processname in tlout[-1]:
        return True
    else:
        return False


def update_preferences_ini():
    '''
    It's used to update %%APPDATA%%\VMWare\preferences.ini, and close all tabs of VMWare Workstation.
    '''
    preferences_ini_file = 'preferences.ini'
    preferences_ini_path = os.path.join(config_dir, preferences_ini_file)
    with open(preferences_ini_path, 'r') as fp:
        lines = fp.readlines()

    shutil.copy(preferences_ini_path, os.path.join(backup_dir, preferences_ini_file))

    with open(preferences_ini_path, 'w') as fp:
        for line in lines:
            line = line.strip('\n')
            if not line:
                continue
            if not line.startswith('pref.ws.session.window0.tab'):
                fp.write('%s\n' % (line))
            elif line.startswith('pref.ws.session.window0.tab.count'):
                fp.write('pref.ws.session.window0.tab.count = "1"\n')
            else:
                # close all tabs
                pass
        # However, we reserve the home tab
        fp.write('pref.ws.session.window0.tab0.dest = ""\n')
        fp.write('pref.ws.session.window0.tab0.file = ""\n')
        fp.write('pref.ws.session.window0.tab0.type = "home"\n')
        fp.write('pref.ws.session.window0.tab0.focused = "TRUE"\n')
    return


def update_inventory_vmls():
    '''
    It's used to update %%APPDATA%%\VMWare\inventory.vmls.
    We only reserve template virtual machines.
    '''
    inventory_vmls_file = 'inventory.vmls'
    inventory_vmls_path = os.path.join(config_dir, inventory_vmls_file)
    with open(inventory_vmls_path, 'r') as fp:
        first_line = fp.readline()

    # Generate inventory info based on database.
    server_name = socket.gethostname().split('.')[0]
    (server_id,) = SQLServerDB.query_one(
        "select ServerID from GhostServer where ServerName='%s'" % (server_name))

    machine_map = {} # {ID: [Name, FolderID], ...}

    rows = SQLServerDB.query(
        'select distinct MachineID from Machine_Reimage where IsVM=1 and ServerID=%s order by MachineID' % (server_id))
    for row in rows:
        machine_id = int(row[0])
        (machine_name,) = SQLServerDB.query_one(
            'select MachineName from Machine_Info where MachineID=%s' % (machine_id))
        folder_id = generate_inventory_folder_info(machine_name)
        machine_map[machine_id] = [machine_name, folder_id]

    rows = SQLServerDB.query(
        'select MachineID, ImageSource from Machine_Reimage where IsVM=1 and ServerID=%s order by MachineID' % (server_id))
    for row in rows:
        machine_id, vmx_path = row
        machine_name, folder_id = machine_map[machine_id]
        generate_inventory_vm_info(machine_name, folder_id, vmx_path)

    shutil.copy(inventory_vmls_path, os.path.join(backup_dir, inventory_vmls_file))

    with open(inventory_vmls_path, 'w') as fp:
        if first_line.startswith('.encoding'):
            fp.write('%s\n' % (first_line.strip('\n')))
        for vm_info in inventory_info:
            fp.write('%s\n' % vm_info[0])
        for vm_info in inventory_info:
            if len(vm_info) == 1:
                continue
            fp.write('%s\n' % vm_info[1])
        fp.write('index.count = "%s"\n' % (sum(len(x)==2 for x in inventory_info)))
    return


def generate_inventory_folder_info(machine_name):
    '''
    Generate the information for the folders in inventory. And return the folder id.
    '''
    vmlist_template = [
        'vmlist%(index)d.config = "folder%(index)d"',
        'vmlist%(index)d.Type = "2"',
        'vmlist%(index)d.DisplayName = "%(name)s"',
        'vmlist%(index)d.ParentID = "0"',
        'vmlist%(index)d.ItemID = "%(item)d"',
        'vmlist%(index)d.SeqID = "%(seq)d"',
        'vmlist%(index)d.IsFavorite = "FALSE"',
        'vmlist%(index)d.UUID = "folder:%(uuid)s"',
        'vmlist%(index)d.Expanded = "FALSE"'
    ]
    cur_vmlist_index = len(inventory_info) + 1
    uu_id = generate_uuid()
    vmlist_str = '\n'.join(vmlist_template) % {
        'index': cur_vmlist_index, 'name': machine_name, 'item': cur_vmlist_index,
        'seq': 0, 'uuid': uu_id}
    inventory_info.append([vmlist_str])
    return cur_vmlist_index


def generate_inventory_vm_info(machine_name, folder_id, vmx_path):
    '''
    Generate the information for the virtual machines in inventory.

    The index of vmlist_template starts from 1,
    while the index of index_template starts from 0.
    '''
    vmlist_template = [
        'vmlist%(index)d.config = "%(vmx)s"',
        'vmlist%(index)d.DisplayName = "%(name)s"',
        'vmlist%(index)d.ParentID = "%(parent)d"',
        'vmlist%(index)d.ItemID = "%(item)d"',
        'vmlist%(index)d.SeqID = "%(seq)d"',
        'vmlist%(index)d.IsFavorite = "FALSE"',
        'vmlist%(index)d.IsClone = "FALSE"',
        'vmlist%(index)d.CfgVersion = "%(ver)s"',
        'vmlist%(index)d.State = "%(state)s"',
        'vmlist%(index)d.UUID = "%(uuid)s"',
        'vmlist%(index)d.IsCfgPathNormalized = "TRUE"'
    ]
    cur_vmlist_index = len(inventory_info) + 1
    cfg_version_default = 8
    uuid_default = '00 00 00 00 00 00 00 00-00 00 00 00 00 00 00 00'
    if os.path.exists(vmx_path):
        cfg_version = read_conf(vmx_path, 'config.version') or cfg_version_default
        state = 'normal'
        uu_id = read_conf(vmx_path, 'uuid.location') or uuid_default
    else:
        cfg_version = cfg_version_default
        state = 'broken'
        uu_id = uuid_default
    display_name = os.path.basename(os.path.dirname(vmx_path))
    vmlist_str = '\n'.join(vmlist_template) % {
        'index': cur_vmlist_index, 'vmx': vmx_path, 'name': display_name,
        'parent': folder_id, 'item': cur_vmlist_index, 'seq': 0, 'ver': cfg_version,
        'state': state, 'uuid': uu_id}

    index_template = [
        'index%(index)d.field0.name = "guest"',
        'index%(index)d.field0.value = "%(guest_os)s"',
        'index%(index)d.field0.default = "TRUE"',
        'index%(index)d.hostID = "localhost"',
        'index%(index)d.id = "%(vmx)s"',
        'index%(index)d.field.count = "1"',
    ]
    if os.path.exists(vmx_path):
        guest_os = read_conf(vmx_path, 'guestOS') or machine_name
    else:
        guest_os = machine_name
    cur_index_index = sum(len(x) == 2 for x in inventory_info)
    index_str = '\n'.join(index_template) % {
        'index': cur_index_index, 'guest_os': guest_os, 'vmx': vmx_path}

    inventory_info.append([vmlist_str, index_str])
    return


def generate_uuid():
    '''
    Generate a new uuid.
    '''
    uu_id = uuid.uuid1().get_hex()
    uu_id = ' '.join(uu_id[2*i:2*i+2] for i in range(len(uu_id)/2))
    uu_id = '%s-%s' % (uu_id[:len(uu_id)/2], uu_id[len(uu_id)/2+1:])
    return uu_id


def read_conf(conf_path, token):
    '''
    Get the value of given token in the given file.
    '''
    with open(conf_path, 'r') as fp:
        lines = fp.readlines()
    for line in lines:
        line = line.strip('\n')
        if not line:
            continue
        key, value = [x.strip() for x in line.split('=', 1)]
        if key == token:
            return value.strip('"')
    return None


if __name__ == '__main__':
    if process_exists('vmware.exe'):
        print('Error: VMWare Workstation is still running, please close it before executing this script.')
        sys.exit(1)
    if not os.path.exists(config_dir):
        print('Error: Couldn\'t find configuration directory "%s"' % (config_dir))
        sys.exit(1)
    if not os.path.exists(backup_dir):
        os.mkdir(backup_dir)

    init_db(config.DB_DEFAULT_HOST, config.DB_DEFAULT_USER,
            config.DB_DEFAULT_PASSWORD, config.DB_DEFAULT_DATABASE)

    print('Updating preferences.ini ...')
    update_preferences_ini()
    print('Updating inventory.vmls ...')
    update_inventory_vmls()
    print('Finish!')
