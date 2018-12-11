import os

import globalvar


# ----------------------------------------------
# Variables in Windows Machine
# ----------------------------------------------

gt_setupenv_script = 'setupenv.bat'
"""
This script is used to setup environment when restart from ghosted
in Windows(Physical & VMware) & Linux(VMware).
In the end of this script, it will call boot script.
"""

gt_mapping_script = 'MAPDRIVES.bat'
"""
The script to map server drives.
"""

gt_cmd_prefix = ''
"""
The prefix added to execute a script.
    * Windows: No prefix is needed.
    * Linux & Mac: Prefix "./" is needed.
"""

gt_sep = '\\'
"""
File separator in target OS
"""


# ----------------------------------------------
# Variables in Windows VMware Machine
# ----------------------------------------------

gt_vm_prepare_script = 'vm_prepare.bat'
"""
This script is used to call rename.bat, and then restart.
"""

gt_vm_prepare_script_full = os.path.join(globalvar.g_incoming_local, gt_vm_prepare_script)
"""
This is the local path of :const:`gt_vm_prepare_script`.
"""

gt_vm_prepare_script_client = os.path.join("C:\\", gt_vm_prepare_script)
"""
This is the client path of :const:`gt_vm_prepare_script`.
"""

gt_vm_rename_script = "rename.bat"
"""
This script is used to rename vmware machine.
"""

gt_vm_rename_script_local = os.path.join(globalvar.g_incoming_local, gt_vm_rename_script)
"""
This is the local path of :const:`gt_vm_rename_script`.
"""

gt_vm_root = "C:\\Incoming"
"""
The working directory on Windows vmware client machine.
"""

gt_vm_rename_script_client = os.path.join(gt_vm_root, gt_vm_rename_script)
"""
This is the client path of :const:`gt_vm_rename_script`.
"""



