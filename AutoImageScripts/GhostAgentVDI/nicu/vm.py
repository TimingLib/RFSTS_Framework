#!/usr/bin/python

"""
Control Vmware from Python. Used the vmrun.exe.
This python script is based on vmrun module which is developed by Binjo <binjo.cn@gmail.com>
We add new feature to support both VMware server and Vmware Workstation.
"""

from __future__ import with_statement
import os
import subprocess
import string
import shutil
import logging
import time

__all__ = ['VmwareType', 'CommonVmwareException',
           'copy_vm', 'init_vmx', 'load_vmx_conf', 'get_vmx_conf', 'Vmrun']


logger = logging.getLogger(__name__)

#
# VMware Files Explained : http://www.vmware.com/support/ws55/doc/ws_learning_files_in_a_vm.html
# We will ignore the log and snapshot files when archiving the vm image.

_VMFilterFileList = ['*.log', '*.lck']
_VMXInitConf = {'uuid.location': '""', 'uuid.bios': '""'}


class VmwareType:
    NonVM = 0          # Non Virtual Machine Server
    VmServer = 1       # VMware Server
    VmWorkstation = 2  # VMware Workstation
    VmPlayer = 3       # VMware Player and VMware VIX

    @classmethod
    def is_vm_server(cls, vm_type):
        return vm_type == VmwareType.VmServer

    @classmethod
    def is_vm_workstation(cls, vm_type):
        return vm_type == VmwareType.VmWorkstation

    @classmethod
    def is_vm_player(cls, vm_type):
        return vm_type == VmwareType.VmPlayer

    @classmethod
    def is_vm(cls, vm_type):
        return vm_type != VmwareType.NonVM

    @classmethod
    def has_snapshot_ability(cls, vm_type):
        return vm_type in [VmwareType.VmServer, VmwareType.VmWorkstation]


class CommonVmwareException(Exception):
    """user-defined common VMware exception"""
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


def copy_vm(src, dest, ignore=_VMFilterFileList):
    logger.debug("All files which have the followed suffix <%s> will be skipped during FilterCopy4VMImage." % ignore)
    try:
        if os.path.exists(dest):
            shutil.rmtree(dest)
        # Here must ensure that dest folder is inexistent, otherwise will
        # throw "WindowsError: [Error 183]" exception.
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(*ignore))
    except shutil.Error, e:
        msg = "shutil.Error [%s]" % (e)
        raise CommonVmwareException(msg)
    except OSError, error:
        msg = "OSError [%s]" % (error)
        raise CommonVmwareException(msg)


def init_vmx(vmconf, opfilter=None, delconf=None):
    """Init the VMX file"""
    try:
        tmp_file = "%s.tmp" % vmconf
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
        os.rename(vmconf, tmp_file)
        conf = load_vmx_conf(tmp_file)
        if opfilter:
            conf.update(opfilter)
            logger.debug("VMX Config will be update by "
                         "custom filter: %s" % opfilter)
        conf.update(_VMXInitConf)
        logger.debug("VMX Config will be update by predefined "
                     "filter: %s" % _VMXInitConf)
        for key in delconf if delconf else []:
            del conf[key]
        with open(vmconf, 'w') as f:
            conf_line = '\n'.join(['%s = %s' % item for item in conf.items()])
            f.write(conf_line)
    except Exception, error:
        msg = "Exception [%s]" % (error)
        raise CommonVmwareException(msg)


def load_vmx_conf(vmconf):
    """Read the vmx file and return a dict"""
    conf = {}
    with open(vmconf) as f:
        for line in f:
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip()
    return conf


def get_vmx_conf(vmconf, key):
    """Read the vmx file and return value of the key"""
    try:
        conf = load_vmx_conf(vmconf)
        if key in conf:
            return conf[key]
    except Exception, error:
        msg = "Exception [%s]" % (error)
        raise CommonVmwareException(msg)


class Vmrun:
    def VmModeValidate(self, vmtype):
        """
        Validate whether the Virtual Machine Type is correct.
        """
        if (vmtype != VmwareType.VmServer and vmtype != VmwareType.VmWorkstation and vmtype != VmwareType.VmPlayer):
            return False
        return True

    def __init__(self, vmtype, vmx, guestusr, guestpwd, host='', user='', password='', port=8333):
        """
        vmtype      : Virtual Machine Type
        user        : login account for Virtual Machine Server
        password    : login password for Virtual Machine Server
        """
        ExceptionMsg = None
        # Validate whether the vmtype is correct
        if not self.VmModeValidate(vmtype):
            ExceptionMsg = "Invalidate Virtual Machine Type(%s)." % vmtype
            raise CommonVmwareException(ExceptionMsg)

        # Vmware image file
        if not vmx:
            ExceptionMsg = "Missing the Virtual Machine image file."
            raise CommonVmwareException(ExceptionMsg)

        # Vmware guest/image information
        if not guestusr or not guestpwd:
            ExceptionMsg = "Missing login account and password for Virtual Machine image(guest)."
            raise CommonVmwareException(ExceptionMsg)

        # Vmware server need the login account and password
        if vmtype == VmwareType.VmServer:
            if not host:
                ExceptionMsg = "Missing the host for Virtual Machine Server."
                raise CommonVmwareException(ExceptionMsg)
            if not user or not password:
                ExceptionMsg = "Missing login account and password for Virtual Machine Server."
                raise CommonVmwareException(ExceptionMsg)

        # Get the location of vmrun.exe
        if os.sys.platform == "win32":
            import _winreg
            vw_dir = ''
            reg = _winreg.ConnectRegistry(None, _winreg.HKEY_LOCAL_MACHINE)
            try:
                if vmtype == VmwareType.VmServer:
                    rh = _winreg.OpenKey(reg, r'SOFTWARE\WOW6432Node\VMware, Inc.\VMware Server')
                elif vmtype == VmwareType.VmWorkstation:
                    rh = _winreg.OpenKey(reg, r'SOFTWARE\WOW6432Node\VMware, Inc.\VMware Workstation')
                elif vmtype == VmwareType.VmPlayer:
                    rh = _winreg.OpenKey(reg, r'SOFTWARE\WOW6432Node\VMware, Inc.\VMware VIX')

                try:
                    vw_dir = _winreg.QueryValueEx(rh, 'InstallPath')[0]
                finally:
                    _winreg.CloseKey(rh)
            finally:
                reg.Close()
            if not vw_dir:
                ExceptionMsg = "Cound not find the vmrun.exe."
                raise CommonVmwareException(ExceptionMsg)
            self.VMRUN_PATH = vw_dir + 'vmrun.exe'
            if not os.path.exists(self.VMRUN_PATH):
                raise CommonVmwareException("%s NOT found!" % self.VMRUN_PATH)
        else:
            if "PATH" in os.environ:
                for path in os.environ["PATH"].split(os.pathsep):
                    tmp_file = path + os.sep + "vmrun"
                    if os.path.exists(tmp_file):
                        self.VMRUN_PATH = tmp_file
                        break

        self.VM_TYPE = vmtype
        self.VM_FILE = vmx
        self.VM_GUESTUSR = guestusr
        self.VM_GUESTPWD = guestpwd
        self.VM_HOST = host
        self.VM_PORT = port
        self.VM_ADMINUSR = user
        self.VM_ADMINPWD = password

    def __str__(self):
        return self.VM_FILE

    def vmrun(self, *cmd):
        """
        Generate and run the Vmware command
        """
        cmds = list(cmd)
        # generate the parameters
        cmds.insert(1, "\"%s\"" % self.VM_FILE)
        # Todo self.VM_PORT
        if self.VM_TYPE == VmwareType.VmServer:
            cmds[0] = "-T server -h %s -u \"%s\" -p \"%s\" -gu \"%s\" -gp \"%s\" \"%s\"" % (self.VM_HOST, self.VM_ADMINUSR, self.VM_ADMINPWD, self.VM_GUESTUSR, self.VM_GUESTPWD, cmds[0])
        elif self.VM_TYPE == VmwareType.VmWorkstation:
            cmds[0] = "-gu \"%s\" -gp \"%s\" \"%s\"" % (self.VM_GUESTUSR, self.VM_GUESTPWD, cmds[0])
        elif self.VM_TYPE == VmwareType.VmPlayer:
            cmds[0] = "-gu \"%s\" -gp \"%s\" \"%s\"" % (self.VM_GUESTUSR, self.VM_GUESTPWD, cmds[0])

        params = " ".join(cmds)
        # execute the virtual machine control command
        if os.sys.platform == "win32":
            cmd = '"%s" %s' % (self.VMRUN_PATH, params)
        else:
            cmd = ["sh", "-c", "%s %s" % (self.VMRUN_PATH, params)]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        stdout, stderr = p.communicate()
        ret_val = []
        stdout = stdout.strip()
        if stdout:
            ret_val = stdout.split('\n')
        return cmd, ret_val

    #
    # Common Operations
    #
    def setVMX(self, vmx):
        if not vmx:
            ExceptionMsg = "Missing the Vmware image file."
            raise CommonVmwareException(ExceptionMsg)
        self.VM_FILE = vmx

    def setGuestInfo(self, guestusr, guestpwd):
        # Vmware guest/image information
        if not guestusr or not guestpwd:
            ExceptionMsg = "Missing login account and password for Vmware image(guest)."
            raise CommonVmwareException(ExceptionMsg)
        self.VM_GUESTUSR = guestusr
        self.VM_GUESTPWD = guestpwd

    #
    # POWER COMMANDS
    #
    def start(self):
        '''
        COMMAND                  PARAMETERS           DESCRIPTION
        start                    Path to vmx file     Start a VM or Team
                                or vmtm file
        '''
        return self.vmrun('start')

    def stop(self, mode='soft'):
        '''
        stop                     Path to vmx file     Stop a VM or Team
                                or vmtm file
                                [hard|soft]
        '''
        return self.vmrun('stop', mode)

    def reset(self, mode='soft'):
        '''
        reset                    Path to vmx file     Reset a VM or Team
                                or vmtm file
                                [hard|soft]
        '''
        return self.vmrun('reset', mode)

    def suspend(self, mode='soft'):
        '''
        suspend                 Path to vmx file     Suspend a VM or Team
                                or vmtm file
                                [hard|soft]
        '''
        return self.vmrun('suspend', mode)

    def pause(self):
        '''
        pause                    Path to vmx file     Pause a VM
        '''
        return self.vmrun('pause')

    def unpause(self):
        '''
        unpause                  Path to vmx file     Unpause a VM
        '''
        return self.vmrun('unpause')

    #
    # SNAPSHOT COMMANDS
    #
    def listSnapshots(self):
        if self.VM_TYPE == VmwareType.VmServer or self.VM_TYPE == VmwareType.VmWorkstation:
            return self.vmrun('listSnapshots')
        else:
            raise CommonVmwareException("The current virtual machine server<%s> do not support listSnapshots." % self.VM_TYPE)
            return 0

    def snapshot(self, name='binjo'):
        '''
        snapshot                 Path to vmx file     Create a snapshot of a VM
                                Snapshot name
        '''
        if self.VM_TYPE == VmwareType.VmServer or self.VM_TYPE == VmwareType.VmWorkstation:
            return self.vmrun('snapshot', name)
        else:
            raise CommonVmwareException("The current virtual machine server<%s> do not support snapshot." % self.VM_TYPE)
            return 0

    def deleteSnapshot(self, name='binjo'):
        '''
        deleteSnapshot           Path to vmx file     Remove a snapshot from a VM
                                Snapshot name
        '''
        if self.VM_TYPE == VmwareType.VmServer or self.VM_TYPE == VmwareType.VmWorkstation:
            return self.vmrun('deleteSnapshot', name)
        else:
            raise CommonVmwareException("The current virtual machine server<%s> do not support deleteSnapshot." % self.VM_TYPE)
            return 0

    def revertToSnapshot(self, name='binjo'):
        '''
        revertToSnapshot         Path to vmx file     Set VM state to a snapshot
                                Snapshot name
        '''
        if self.VM_TYPE == VmwareType.VmServer or self.VM_TYPE == VmwareType.VmWorkstation:
            return self.vmrun('revertToSnapshot', name)
        else:
            raise CommonVmwareException("The current virtual machine server<%s> do not support revertToSnapshot." % self.VM_TYPE)
            return 0

    #
    # RECORD/REPLAY COMMANDS
    #
    def beginRecording(self, snap_name='binjo'):
        '''
        beginRecording           Path to vmx file     Begin recording a VM
                                Snapshot name
        '''
        return self.vmrun('beginRecording', snap_name)

    def endRecording(self):
        '''
        endRecording             Path to vmx file     End recording a VM
        '''
        return self.vmrun('endRecording')

    def beginReplay(self, snap_name='binjo'):
        '''
        beginReplay              Path to vmx file     Begin replaying a VM
                                Snapshot name
        '''
        return self.vmrun('beginReplay', snap_name)

    def endReplay(self):
        '''
        endReplay                Path to vmx file     End replaying a VM
        '''
        return self.vmrun('endReplay')

    #
    # GUEST OS COMMANDS
    #
    # FIXME -noWait -activeWindow -interactive???
    def runProgramInGuest(self, program, *para):
        '''
        runProgramInGuest        Path to vmx file     Run a program in Guest OS
                                [-noWait]
                                [-activeWindow]
                                [-interactive]
                                Complete-Path-To-Program
                                [Program arguments]
        '''
        return self.vmrun('runProgramInGuest', "\"%s\"" % program, *para)

    # TODO straight return?
    def fileExistsInGuest(self, file):
        '''
        fileExistsInGuest        Path to vmx file     Check if a file exists in Guest OS
                                Path to file in guest
        '''
        return self.vmrun('fileExistsInGuest', "\"%s\"" % file)

    def directoryExistesInGuest(self, dirname):
        return self.vmrun('directoryExistesInGuest', '"%s"' % dirname)

    def setSharedFolderState(self, share_name, new_path, mode='readonly'):
        '''
        setSharedFolderState     Path to vmx file     Modify a Host-Guest shared folder
                                Share name
                                Host path
                                writable | readonly
        '''
        return self.vmrun('setSharedFolderState', share_name, new_path, mode)

    def addSharedFolder(self, share_name, host_path):
        '''
        addSharedFolder          Path to vmx file     Add a Host-Guest shared folder
                                Share name
                                New host path
        '''
        return self.vmrun('addSharedFolder', share_name, host_path)

    def removeSharedFolder(self, share_name):
        '''
        removeSharedFolder       Path to vmx file     Remove a Host-Guest shared folder
                                Share name
        '''
        return self.vmrun('removeSharedFolder', share_name)

    def listProcessesInGuest(self, wait_time=None):
        '''
        listProcessesInGuest     Path to vmx file     List running processes in Guest OS

        This function has three behaviours:
        1. Return processes if the corresponding OS is running.
        2. Return error if the virtual machine is not powered on.
        3. Block and return processes until the corresponding OS has started up.
        '''
        if wait_time is None:
            return self.vmrun('listProcessesInGuest')
        for i in range((wait_time-1)/10):
            (list_cmd, vm_res) = self.vmrun('listProcessesInGuest')
            if not vm_res[0].lower().startswith('error:'):
                return (list_cmd, vm_res)
            time.sleep(10)
        return self.vmrun('listProcessesInGuest')

    def killProcessInGuest(self, pid):
        '''
        killProcessInGuest       Path to vmx file     Kill a process in Guest OS
                                process id
        '''
        return self.vmrun('killProcessInGuest', pid)

    def runScriptInGuest(self, interpreter_path, script):
        '''
        runScriptInGuest         Path to vmx file     Run a script in Guest OS
                                Interpreter path
                                script_text
        '''
        return self.vmrun('runScriptInGuest', interpreter_path, "\"%s\"" % script)

    def deleteFileInGuest(self, file):
        '''
        deleteFileInGuest        Path to vmx file     Delete a file in Guest OS
                                Path in guest
        '''
        return self.vmrun('deleteFileInGuest', "\"%s\"" % file)

    def createDirectoryInGuest(self, dirname):
        '''
        createDirectoryInGuest   Path to vmx file     Create a directory in Guest OS
                                Directory path in guest
        '''
        ret = None              # ret is a tuple of 2 elements
        try:
            ret = self.vmrun('createDirectoryInGuest', "\"%s\"" % dirname)
        except:
            ret = self.directoryExistesInGuest(dirname)
        return ret

    def deleteDirectoryInGuest(self, dir):
        '''
        deleteDirectoryInGuest   Path to vmx file     Delete a directory in Guest OS
                                Directory path in guest
        '''
        return self.vmrun('deleteDirectoryInGuest', "\"%s\"" % dir)

    def listDirectoryInGuest(self, dir):
        '''
        listDirectoryInGuest     Path to vmx file     List a directory in Guest OS
                                Directory path in guest
        '''
        return self.vmrun('listDirectoryInGuest', "\"%s\"" % dir)

    def copyFileFromHostToGuest(self, host_path, guest_path):
        '''
        copyFileFromHostToGuest  Path to vmx file     Copy a file from host OS to guest OS
                                Path on host
                                Path in guest
        '''
        return self.vmrun('copyFileFromHostToGuest', "\"%s\"" % host_path, "\"%s\"" % guest_path)

    def copyFolderFromHostToGuest(self, host_folder, guest_folder):
        '''
        copyFileFromHostToGuest  Path to vmx file     Copy a file from host OS to guest OS
                                Path on host
                                Path in guest
        '''
        cmds = []
        results = []
        (cmd, result) = self.deleteDirectoryInGuest(guest_folder)
        cmds.append(cmd)
        results.append(result)
        (cmd, result) = self.createDirectoryInGuest(guest_folder)
        cmds.append(cmd)
        results.append(result)
        for root, dirs, files in os.walk(host_folder):
            for dir in dirs:
                (cmd, result) = self.createDirectoryInGuest(os.path.join(root, dir).replace(host_folder, guest_folder))
                cmds.append(cmd)
                results.append(result)
            for file in files:
                (cmd, result) = self.copyFileFromHostToGuest(os.path.join(root, file), os.path.join(root, file).replace(host_folder, guest_folder))
                cmds.append(cmd)
                results.append(result)
        return (cmds, results)

    def copyFileFromGuestToHost(self, guest_path, host_path):
        '''
        copyFileFromGuestToHost  Path to vmx file     Copy a file from guest OS to host OS
                                Path in guest
                                Path on host
        '''
        return self.vmrun('copyFileFromGuestToHost', "\"%s\"" % guest_path, "\"%s\"" % host_path)

    def renameFileInGuest(self, org_name, new_name):
        '''
        renameFileInGuest        Path to vmx file     Rename a file in Guest OS
                                Original name
                                New name
        '''
        return self.vmrun('renameFileInGuest', "\"%s\"" % org_name, "\"%s\"" % new_name)

    def captureScreen(self, path_on_host):
        '''
        captureScreen            Path to vmx file     Capture the screen of the VM to a local file
                                Path on host
        '''
        return self.vmrun('captureScreen', "\"%s\"" % path_on_host)

    def writeVariable(self, mode, v_name, v_value):
        '''
        writeVariable            Path to vmx file     Write a variable in the VM state
                                [runtimeConfig|guestEnv]
                                variable name
                                variable value
        '''
        if mode is not None:
            return self.vmrun('writeVariable', mode, v_name, v_value)
        else:
            return self.vmrun('writeVariable', v_name, v_value)

    def readVariable(self, mode, v_name):
        '''
        readVariable             Path to vmx file     Read a variable in the VM state
                                [runtimeConfig|guestEnv]
                                variable name
        '''
        if mode is not None:
            return self.vmrun('readVariable', mode, v_name)
        else:
            return self.vmrun('readVariable', v_name)

    #
    # VPROBE COMMANDS
    #
    def vprobeVersion(self):
        '''
        vprobeVersion            Path to vmx file     List VP version
        '''
        return self.vmrun('vprobeVersion')

    def vprobeLoad(self, script):
        '''
        vprobeLoad               Path to vmx file     Load VP script
                                'VP script text'
        '''
        return self.vmrun('vprobeLoad', script)

    def vprobeListProbes(self):
        '''
        vprobeListProbes         Path to vmx file     List probes
        '''
        return self.vmrun('vprobeListProbes')

    def vprobeListGlobals(self):
        '''
        vprobeListGlobals        Path to vmx file     List global variables
        '''
        return self.vmrun('vprobeListGlobals')

    #
    # GENERAL COMMANDS
    #
    def list(self):
        '''
        list                                          List all running VMs
        '''
        return self.vmrun('list')

    def upgradevm(self):
        '''
        upgradevm                Path to vmx file     Upgrade VM file format, virtual hw
        '''
        return self.vmrun('upgradevm', self.VM_FILE)

    def installtools(self):
        '''
        installtools             Path to vmx file     Install Tools in Guest OS
        '''
        return self.vmrun('installtools', self.VM_FILE)

    def clone(self, dest_vmx, mode, snap_name='binjo'):
        '''
        clone                    Path to vmx file     Create a copy of the VM
                                Path to destination vmx file
                                full|linked
                                [Snapshot name]
        '''
        return self.vmrun('clone', dest_vmx, mode, snap_name)

    def register(self):
        '''
        register                 Path to vmx file     Create a copy of the VM
        '''
        return self.vmrun('register')

    def unregister(self):
        '''
        unregister               Path to vmx file     Create a copy of the VM
        '''
        return self.vmrun('unregister')

    def isRunning(self):
        '''
        Judge whether current virtual machine is running.
        '''
        (vm_cmd, vm_res) = self.list()
        return self.VM_FILE.lower() in [x.lower().strip() for x in vm_res[1:]]


    #
    # POWER COMMANDS with blocking
    #
    def startAndWait(self):
        '''
        Start a virtual machine, and wait until login.
        (not include finishing startup script)
        '''
        (list_cmd, vm_res) = self.listProcessesInGuest()
        if not vm_res[0].lower().startswith('error:'):
            # Already started
            return (list_cmd, [])
        return self.resetAndWait()

    def resetAndWait(self):
        '''
        Reboot a virtual machine, and wait until login.
        (not include finishing startup script, same as startAndWait)
        '''
        (list_cmd, vm_res) = self.listProcessesInGuest()
        if not vm_res[0].lower().startswith('error:'):
            # Already started
            (vm_cmd, vm_res) = self.reset()
        else:
            # Shutted down
            (vm_cmd, vm_res) = self.start()
        if vm_res:
            return (vm_cmd, vm_res)
        (list_cmd, vm_res) = self.listProcessesInGuest(wait_time=60)
        if vm_res[0].lower().startswith('error:'):
            return (list_cmd, vm_res)
        return (vm_cmd, [])

    def stopAndWait(self):
        '''
        Stop a virtual machine.
        '''
        # If machine already shutdown, return directly.
        if not self.isRunning():
            return ('', [])
        (stop_cmd, vm_res) = self.stop()
        if self.isRunning():
            return (stop_cmd, vm_res or ['Error: virtual machine is still running.'])
        return (stop_cmd, [])