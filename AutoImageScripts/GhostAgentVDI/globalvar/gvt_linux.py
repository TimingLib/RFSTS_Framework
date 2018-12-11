import os

import globalvar


# ----------------------------------------------
# Variables in Linux Machine
# ----------------------------------------------

gt_setupenv_script = 'setupenv.sh'
"""
.. seealso:: :const:`globalbar.gvt_windows.gt_setupenv_script`
"""

gt_mapping_script = 'MAPDRIVES.sh'
"""
.. seealso:: :const:`globalbar.gvt_windows.gt_mapping_script`
"""

gt_cmd_prefix = './'
"""
.. seealso:: :const:`globalbar.gvt_windows.gt_cmd_prefix`
"""

gt_sep = '/'
"""
File separator in target OS
"""


# ----------------------------------------------
# Variables in Linux VMware Machine
# ----------------------------------------------

gt_vm_rename_script = "rename.sh"
"""
.. seealso:: :const:`globalbar.gvt_windows.gt_mapping_script`.
"""

gt_vm_rename_script_local = os.path.join(globalvar.g_incoming_local, gt_vm_rename_script)
"""
.. seealso:: :const:`globalbar.gvt_windows.gt_vm_rename_script_local`.
"""

gt_vm_rename_script_client = os.path.join("/home/lvtest/", gt_vm_rename_script)
"""
.. seealso:: :const:`globalbar.gvt_windows.gt_vm_rename_script_client`.
"""

gt_vm_root = "/home/lvtest/INCOMING"
"""
The working directory on Linux vmware client machine.
"""

gt_vm_script_root = "/mnt/cn-sha-rdfs01/RD/SAST/Installer_Services/Services/GhostAgentVDI/APPDATA/%s/%s/%s/OSID_%s"
"""
The dirctory to copy script.ini
"""
