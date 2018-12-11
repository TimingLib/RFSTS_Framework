"""
**Naming Notations:**
    * **Global Name:**
        * all global variables start with **g_**/**gt_**
            * **g_**: this variable is shared in all targets
            * **gt_**: this variable is shared in special target
        * prefix format is **g[t]_[vm_]**
        * Exmaples:
            * **g_vm_**: this variable is exclusive in vmware.

    * **Path Name:**
        * File name: ends with **_file**/**_script**/**_ini**,
          based on extension of file.
        * Folder name: ends with **_folder**.
        * Directory: ends with **_dir**/**_root**,
            **_root** signifies the special directory, like `INCOMING`
            and so on.
        * Path name: ends with **_full**/**_src**/**_dst**.
            When emphasize the machine where the file stored,
            replace the suffix above with follows:

            * Path in Client Machine: ends with **_client**.
            * Path in File Server: ends with **_server**.
            * Path in GhostAgent Server: ends with **_local**.

"""
import os
import sys
import platform
import threading

# python 2.5.1, platform.system() is 'microsoft'
# python 2.6, platform.system() is 'windows'
g_platform = platform.system().lower()
if g_platform == 'microsoft':
    g_platform = 'windows'


#--------------- Path configuration -----------------------

g_ga_root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
"""
The path of current GhostAgent server.
"""

g_export_server = "\\\\cn-sha-rdfs01\\RD\\SAST\\Installer_Services\\Services\\GhostAgentVDI"
"""
This export folder is used to store all needed files(like script, config).
"""

g_incoming_folder = 'INCOMING'
"""
This folder is used to store all scripts that run in Client Machine after ghost.
"""

g_incoming_local = os.path.join(g_ga_root, g_incoming_folder)
"""
This folder is :dudir:`Program Root\\INCOMING`.
.. seealso:: :const:`g_incoming_folder`.
"""

g_version_txt = "version.txt"
"""
The file to store GhostAgent version.
"""

g_script_ini = "script.ini"
"""
The configure file, including all the steps will do after ghost.
"""

g_log_root = os.path.join(g_ga_root, "Logs")
"""
GhostAgent Server log directory.
"""

g_script_ini_dir_server = g_export_server + '\\APPDATA'
"""
The directory is where "script.ini" stored.
"""

g_apply_images_folder = "Apply Images"
"""
A folder that `script.ini` stored in.
"""

g_export_vmroot = "\\\\cn-sha-rdfs01\\VM-Pool\\Export VM"
"""
The path to export images
"""

#--------------- Email configuration -----------------------

g_smtp_server = 'mailmass.natinst.com'
"""
SMTP server.
"""

g_sast_group_email = 'yang.liu3@ni.com'
"""
Our group email address, used to receive emails when ghost failed.
"""

g_reply_email_from = 'donotreply_sast@ni.com'
"""
Email address where emails sent from.
"""

#--------------- GhostAgent configuration -----------------------

g_server_ip = '0.0.0.0'
"""
The IP address of GhostAgent Server.
.. note::
    This IP will be changed to internal IP, when GhostAgent is deployed
    in Windows and restarting.
"""

g_is_upgrade = False
"""
Whether current GhostAgent Server needs to upgrade.
"""

g_check_upgrade_interval = 5
"""
The interval to check whether GhostAgent needs to upgrade.
"""

g_ns_port = None
"""
The port of Notify Server, will be initialed after started.
"""

g_ns = None
"""
The instance of Notify Server, used for communication betwwen client and server
after client ghosted. Through Notify Server, GhostAgent is able to know whether
a client machine has been ghosted or not.
It will be initialed after started.
"""

g_thread_lock = threading.Lock()
"""
The lock shared by all threads.
"""

g_thread_map = {}
"""
The key word is thread id, and the value is the variables module based on
target os platform.
"""

g_thread_data = threading.local()
"""
This variable will store local variables for each thread.
"""

g_export_images_size_limit = 500 * 1024 * 1024 * 1024L
"""
This variable will limit the size to archive under g_export_vmroot.
"""

# ----------------------------------------------
# Variables in VMware Machine
# ----------------------------------------------

g_vm_clean_snap = 'CleanSnap'
"""
Clean snapshot name of vmware client machine.
"""

g_vm_max_customized_snapshot_num = 3
"""
Max number to save customized snapshots for one vmware client machine.
"""

#--------------- Path configuration -----------------------

g_vm_lock_root = os.path.join(g_ga_root, ".LockRoot")
"""
The lock folder, to indicate whether the vmware client machine has been locked.
"""

g_vm_image_archive_root = os.path.join(g_ga_root, "VMImageArchiveRoot")
"""
The directory to store archive images.
"""

g_vm_conf_file = 'config.ini'
"""
The configure file about the vmware client machine.
"""

g_vm_script_log = 'scriptOut.log'
"""
The file is used to log the messages which scripts print.
"""

g_vm_install_log = 'InstallLog.txt'
"""
The file stores all the installed products.
"""

#--------------- Time & Count configuration -----------------------

g_vm_thread_killed_time = 300
"""
The time to wait for current thread owning vmware lock killed.
"""

g_vm_images_max_count = 3
"""
The max count of local images reserved for each vmware client machine at one time.
"""

g_vm_parallel_max_count = 3
"""
The max count to execute vmrun tools at the same time.
"""