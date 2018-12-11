"""
This file is an extension of vm operation, used in GhostAgent.
"""
from __future__ import with_statement
import os
import time
import logging
import thread
import threading
import shutil
import traceback
import uuid
import socket
import glob
import re
import ConfigParser
from datetime import datetime

import nicu.vm as vm
import nicu.errcode as errcode
from nicu.file.filelock import FileLock
from nicu.vm import VmwareType, CommonVmwareException
from nicu.vmrun import VmrunPool
from nicu.mail import Mail
from nicu.db import SQLServerDB
from nicu.decor import TimeoutError
from nicu.misc import get_last_modified_time

import globalvar as gv
import util
import util.dbx as dbx
import util.conf as conf
import util.report as report


__all__ = [
    "ghost_machine",
    "grab_new_image",
    "deploy_vm_image",
    "archive_vm_image",
    "release_machine",
    "start_vm",
    "shutdown_vm",
    "restart_vm",
    "is_vm_running",
    "list_snapshots",
    "take_snapshot",
    "delete_snapshot",
    "revert_snapshot",
    "get_snapshot_list",
    "start_all_machines",
    "delete_expired_image"
    "export_vm"
]

LOGGER = logging.getLogger(__name__)


class Vmrun():
    """
    A lite Vmrun class for processing vmware workstation only,
    and dealing with result to make code more concise.
    """

    # We will only process the result of these following commands
    cmds_observed = [
        'start', 'stop', 'reset', 'snapshot', 'deleteSnapshot', 'revertToSnapshot',
        'runProgramInGuest', 'runScriptInGuest', 'deleteFileInGuest', 'createDirectoryInGuest',
        'deleteDirectoryInGuest', 'copyFileFromHostToGuest', 'copyFolderFromHostToGuest',
        'copyFileFromGuestToHost', 'renameFileInGuest', 'clone', 'startAndWait', 'resetAndWait',
        'stopAndWait']

    def __init__(self, vmx, guestusr, guestpwd):
        self.vmrun = VmrunPool(
            VmwareType.VmWorkstation, vmx, guestusr, guestpwd,
            host='', user='', password='', port=8333,
            parallel=gv.g_vm_parallel_max_count)
        self.func_name = None
        self._set_args()

    def __call__(self, *args, **kwargs):
        self._set_args(*args, **kwargs)
        return self

    def __getattr__(self, func_name):
        func = getattr(self.vmrun, func_name)
        # if this is the member variable or not the command we observe.
        if not hasattr(func, '__call__') or func_name not in Vmrun.cmds_observed:
            self.func_name = None
            self._set_args()
            return func
        else:
            self.func_name = func_name
            return self._call_func_with_retries

    def _set_args(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs
        return

    def _call_func_with_retries(self, *func_args, **func_kwargs):
        args, kwargs = self.args, self.kwargs
        self._set_args()
        if func_args and func_kwargs:
            parameters = ': %s, %s' % (str(func_args), str(func_kwargs))
        elif func_args:
            parameters = ': %s' % (str(func_args))
        elif func_kwargs:
            parameters = ': %s' % (str(func_kwargs))
        else:
            parameters = ''
        LOGGER.info('%sExecute vm operation "%s%s" on "%s"'
                    % (util.get_caller_pos(), self.func_name, parameters, self.vmrun))
        func = getattr(self.vmrun, self.func_name)
        # vmware tools would be occasionally unstable.
        # So we would retry it 3 times at most.
        MAX_TRIES = 3
        for i in range(MAX_TRIES):
            try:
                vm_cmd, vm_res = func(*func_args, **func_kwargs)
            except Exception, error:
                vm_cmd = ''
                if isinstance(error, TimeoutError):
                    vm_res = 'Timeout when execute "%s%s" on "%s"' % (
                        self.func_name, parameters, self.vmrun)
                else:
                    vm_res = 'Exception raised during executing "%s%s" on "%s": %s' % (
                        self.func_name, parameters, self.vmrun, str(error))
            try:
                vm_process_res(vm_cmd, vm_res, *args, **kwargs)
                break
            except Exception, error:
                if i == MAX_TRIES - 1:
                    raise Exception(error)
                time.sleep(5)
                LOGGER.info('Retry to execute vm operation "%s" again' % (self.func_name))
        return (vm_cmd, vm_res)


class VmLock(FileLock):
    """
    VM lock is used to lock a vm machine.
    """
    def __init__(self, machine_id):
        lock_file_contents = '%s\n%s' % (thread.get_ident(),
                                         traceback.format_exc())
        self.machine_id = machine_id
        super(VmLock, self).__init__(
            os.path.join(gv.g_vm_lock_root, machine_id),
            lock_file_contents=lock_file_contents)

    def __enter__(self):
        super(VmLock, self).__enter__()
        if not self.locked():
            LOGGER.info("machine %s acquire lock fail" % self.machine_id)
            raise Exception(errcode.ER_GA_LOCK_ACQUIRE_EXCEPTION)

        LOGGER.info("machine %s acquire lock by thread %s"
                    % (self.machine_id, thread.get_ident()))
        return self

    @classmethod
    def release_force(cls, machine_id):
        # when calling release_force, the caller doesn't know
        # whether there is a lock file, because no lock file situation
        # and locked by other thread situation will both specify
        # LockStat False. So we need to test whether there is lock file
        # first.
        # We should make sure that *.lck folders of the vm image also have
        # been removed. Otherwise, this vm won't be accessed correctly later.
        try:
            (machine_name,) = dbx.queryx_machine_name(machine_id)
            vm_object_tmp = Vmrun('NotEmpty', 'NotEmpty', 'NotEmpty')
            (vm_cmd, vm_res) = vm_object_tmp.list()
            for vmx_path in vm_res[1:]:
                vmx_path = vmx_path.strip().lower()
                if '\\%s\\' % (machine_name.lower()) not in vmx_path:
                    continue
                lck_list = glob.glob(os.path.join(os.path.dirname(vmx_path), "*.lck"))
                for lck in lck_list:
                    util.delete_path(lck)
        except Exception, error:
            LOGGER.warning('Failed to release *.lck folder for machine %s: %s'
                           % (machine_id, error))

        lockfile = os.path.join(gv.g_vm_lock_root, "%s.lock" % machine_id)
        if not os.path.exists(lockfile):
            LOGGER.debug("The lock file doesn't exist, filename= %s", lockfile)
            dbx.updatex_table(
                'Machine_Info', 'ExpireTime', 'GETDATE()',
                'MachineID=%s' % machine_id)
            LOGGER.debug("ExpireTime of machine %s is reset" % machine_id)
            return errcode.ER_SUCCESS

        LOGGER.info("The lock file exists, try to read the thread id in it"
                    " and kill the thread")
        try:
            tid = int(open(lockfile, "r").readline())
            victim = None
            # enumerate return a list of thread objects
            thread_list = [t for t in threading.enumerate() if t.ident == tid]
            if thread_list and thread_list[0].isAlive():
                victim = thread_list[0]
                victim.terminate()
                victim.join(gv.g_vm_thread_killed_time)
                if victim.isAlive():
                    raise Exception('Fail to kill thread %d, timeout (%s)sec'
                                    % (tid, gv.g_vm_thread_killed_time))
            LOGGER.info("thread %s killed or died long ago" % tid)
            if os.path.exists(lockfile):
                os.remove(lockfile)
            dbx.updatex_table(
                'Machine_Info', 'ExpireTime', 'GETDATE()',
                'MachineID=%s' % machine_id)
            LOGGER.info('lockfile %s removed, release_force %s locked by'
                        ' thread %s succeed.' % (lockfile, machine_id, tid))
            return errcode.ER_SUCCESS

        except Exception, error:
            LOGGER.error('Fail to release_force %s locked by thread %s: %s.'
                         '\n%s' % (machine_id, tid, error,
                                   traceback.format_exc()))
            raise Exception(errcode.ER_GA_LOCK_RELEASE_EXCEPTION)


def vm_get_image_vmx(vm_image_root):
    """
    Get the file name of ".vmx" from vm_image_root.

    :param vm_image_root:
        The directory of vm image.
    :returns:
        The file name of ".vmx".
    """
    for root, dirs, files in os.walk(vm_image_root):
        for file_name in files:
            file_suffix = os.path.splitext(file_name)[1][1:]
            if file_suffix.lower() == "vmx":
                return file_name
    LOGGER.error("no file with suffix vmx found at %s" % vm_image_root, extra={'error_level': 2})
    return None


def vm_get_login_info(vm_config_file_full):
    """
    Get the login information of the VM image from `config.ini`.

    :param vm_config_file_full:
        The path of file `config.ini`.
    :returns:
        * successful - (image_user, image_pwd)
            * image_user - The account of vm image.
            * image_pwd - The password of vm image.
        * failed - None
    """
    try:
        LOGGER.info("Getting login information from %s."
                    % (vm_config_file_full))
        vm_config = ConfigParser.ConfigParser()
        vm_config.read(vm_config_file_full)
        image_user = vm_config.get('BasicInfo', 'Account')
        image_pwd = vm_config.get('BasicInfo', 'Password')
    except Exception, error:
        LOGGER.warning("Failed to get login information from config.ini: %s" % error)
        return None
    return (image_user, image_pwd)


def vm_process_res(vm_cmd, vm_res, tip='', is_raise=True, level='error'):
    """
    Process the result of executed command. If result of executed command
    is not 0, and parameter `is_raise` is set `True`, then raise exception.

    :param vm_cmd:
    :param vm_res:
        The result of command.
    :param tip:
        The tip to print.
    :param is_raise:
        Whether raise exception when command executed failed.
    :param level:
        Set the logger level to print error message when command executed
        failed.
    """
    if vm_cmd:
        LOGGER.info('%s%s%s' % (util.get_caller_pos(2), tip, vm_cmd))
    if vm_res:
        getattr(LOGGER, level.lower())(vm_res)
        # LOGGER.error(traceback.format_stack())
        if level == 'error':
            LOGGER.error('%s%s' % (tip, vm_res), extra={'error_level': 3})
        if is_raise:
            raise Exception(errcode.ER_GA_VM_CMD_FAILED)
    return


def vm_check_template_image(vm_image_root):
    """
    Check whether the image template exists in the template server.

    :param vm_image_root:
        The directory of vm image.
    :returns:
        True if the image template exists in the template server,
        otherwise False.
    """
    if not vm_image_root or not os.path.exists(vm_image_root):
        LOGGER.error("The virtual image template folder <%s> is not exist." % (vm_image_root),
                     extra={'error_level': 2})
        return errcode.ER_FILE_NONEXIST
    vm_image_vmx = vm_get_image_vmx(vm_image_root)
    if not vm_image_vmx:
        LOGGER.error("Can not get the virtual image file from %s." % (vm_image_root),
                     extra={'error_level': 2})
        return errcode.ER_FILE_NONEXIST
    return errcode.ER_SUCCESS


def grab_new_image(machine_id, os_id, server_id):
    """
    Grab a new image with specific OS for target vm machine.
    Similar with :func:`handle.grab_new_image`, except target is vmware.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    :param os_id:
        The `OSID` column in `OS_Info` table.
    :param server_id:
        The `ServerID` column in `GhostServer` table.
    :returns:
        * successful - 0
        * failed - raise exception
    """
    qs_res = dbx.queryx_image_info(machine_id, os_id)
    image_full, image_user, image_pwd = qs_res[1:4]

    with VmLock(machine_id):
        vm_object = Vmrun(image_full, image_user, image_pwd)

        cur_time = time.strftime('%Y%m%d%H%M%S', time.localtime())
        vm_snap_name = "Snap%s" % (cur_time)

        # take new snapshot for current vm image
        vm_object(is_raise=False, level='warning').stopAndWait()
        vm_object.snapshot(vm_snap_name)
        vm_object.startAndWait()

    return errcode.ER_SUCCESS


def remove_vmware_lock(vm_image_dir):
    """
    Remove all the lock generated by vmware workstation.
    """
    locks = glob.glob(os.path.join(vm_image_dir, '*.lck'))
    for lock in locks:
        util.delete_path(lock)
    return


def stop_machines(machine_id):
    # Stop the all related images.
    # Since that usally only one virtual machine with specified ID is running
    # at one time, and each virtual machine may support dozens of OS.
    # So it's not efficient to attempt to shutdown all possible vm machines
    # one by one.
    # It's better to list all running vm machines, and close them all.
    #
    # Sometimes, the reimage record of specified machine and OS will be
    # modified/deleted, so as a potential consequence, if this image has already
    # been started, and it will never be powered off.
    # In order to avoid this as much as possible, we will also stop machines
    # whose path contains the machine name, such as
    # D:\DailyVMRoot\sh-rd-vmtest01\Windows_7_64_EN\Windows 7 x64.vmx
    LOGGER.info("stopping machine %s's registered images ..." % (machine_id))
    (machine_name,) = dbx.queryx_machine_name(machine_id)
    rows = dbx.queryx_all_images(machine_id)
    # It's a trick to initial vm object with parameters which are not empty.
    # Otherwise, it will raise an error.
    # And we will reset these attributes later.
    vm_object_tmp = Vmrun('NotEmpty', 'NotEmpty', 'NotEmpty')
    (vm_cmd, vm_res) = vm_object_tmp.list()
    for vmx_path in vm_res[1:]:
        vmx_path = vmx_path.strip()
        for row in rows:
            if row[0].lower() != vmx_path.lower() and \
                '\\%s\\' % (machine_name.lower()) not in vmx_path.lower():
                continue
            vm_object_tmp.setVMX(vmx_path)
            vm_object_tmp.setGuestInfo(row[1], row[2])
            vm_object_tmp(is_raise=False, level='warning').stopAndWait()
            remove_vmware_lock(os.path.dirname(vmx_path))
            break
    return


def ghost_machine(machine_id, os_id, seq_id, email_to,
                  client_addr=None, is_grab_image=False):
    """
    Ghost a vm machine. Similar with :func:`handle.ghost_machine`,
    except target is vmware.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    :param os_id:
        The `OSID` column in `OS_Info` table.
    :param seq_id:
        The `SeqID` column in `GhostSequences` table.
    :param email_to:
        The email adderss for receiving the notification email of Ghost
        status.
    :returns:
        * successful - 0
        * failed - raise exception
    """
    # is_grab_image only works for Windows Physical Machine
    if is_grab_image:
        LOGGER.error(
            "Grab Image does not work for Vmware Machine <%s>" % (machine_id),
            extra={'error_level': 1})
        raise Exception(errcode.ER_GA_PF_UNSUPPORT)

    qs_res = dbx.queryx_image_info(machine_id, os_id)
    image_full, image_user, image_pwd = qs_res[1:4]

    gvt, hdl = util.export_target_modules()

    qs_res = dbx.queryx_target_os_info(os_id)
    target_platform = qs_res[0]
    if target_platform not in ['windows', 'linux']:
        LOGGER.error(
            "VMWare doesn't support platform %s" % target_platform,
            extra={'error_level': 1})
        raise Exception(errcode.ER_GA_PF_UNSUPPORT)

    with VmLock(machine_id):
        stop_machines(machine_id)

        deploy_vm_image_single(machine_id, os_id, lock=False, force=False, reset_local=False)

        remove_vmware_lock(os.path.dirname(image_full))
        vm_object = Vmrun(image_full, image_user, image_pwd)
        vm_object.revertToSnapshot(gv.g_vm_clean_snap)
        vm_object.startAndWait()
        # Delete the working director on client
        vm_object(is_raise=False, level='debug').deleteDirectoryInGuest(gvt.gt_vm_root)
        # Create the working director on client,
        vm_object.createDirectoryInGuest(gvt.gt_vm_root)

        # Generate the ini file for Ghost, and placed behind
        # deploy_vm_image_single() to ensure adopting the updated
        # value of gvt.gt_vm_root & gvt.gt_vm_rename_script_client
        LOGGER.info("Ready to generate script.ini")
        script_ini_full = conf.gen_ghost_conf(machine_id, os_id, seq_id, email_to,
                                              is_grab_image=False, boot_dir_home=gvt.gt_vm_root)
        setupenv_script_local = os.path.join(
            os.path.dirname(script_ini_full), gvt.gt_setupenv_script)
        setupenv_script_client = gvt.gt_vm_root + gvt.gt_sep + gvt.gt_setupenv_script
        LOGGER.info("transfer server to client: %s ==> %s"
                    % (setupenv_script_local, setupenv_script_client))
        vm_object.copyFileFromHostToGuest(setupenv_script_local, setupenv_script_client)

        # Running the boot batch file
        vm_object = vm_object(tip='run script in client:\n', is_raise=False, level='warning')
        if target_platform == 'windows':
            vm_object.runScriptInGuest(
                '""',
                '\\"%s\\" \\"%s\\"' % (setupenv_script_client, gvt.gt_vm_root),
                nowait=True)
        else:   # linux
            # Since that linux virual machine starts much faster than before, and
            # startAndWait will return immediately after login in. So setupenv.sh
            # probabaly has already generated BootScript.desktop before desktop
            # environment start throughly.
            # So it will cause one issue that "boot.sh" will be executed twice
            # at the same time.
            # As a solution, we add another 10 seconds to wait for desktop
            # environment starting.
            time.sleep(10)
            vm_object.runProgramInGuest(setupenv_script_client, True, image_user)
    return errcode.ER_SUCCESS


def need_update(local_vmx, template_src_dir):
    """
    Judge whether there is a newer image on server.
    Sometimes, only config.ini file has been updated, we also need to keep an eye
    on this situation.

    If local vm template doesn't have the snapshot (maybe caused by failed to
    deploy or copied from rdfs01 manully), ghost process will fail since for
    lack of snapshot. So we have to take care of this situation.
    """
    server_vmx = os.path.join(template_src_dir, os.path.basename(local_vmx))
    config_file = 'config.ini'
    local_config = os.path.join(os.path.dirname(local_vmx), config_file)
    server_config = os.path.join(template_src_dir, config_file)
    if not os.path.exists(local_vmx) or not os.path.exists(local_config):
        return True
    local_vmx_ctime = os.path.getctime(local_vmx)
    local_config_ctime = os.path.getctime(local_config)
    server_vmx_mtime = os.path.getmtime(server_vmx)
    server_config_mtime = os.path.getmtime(server_config)
    if server_vmx_mtime > local_vmx_ctime or server_config_mtime > local_config_ctime:
        return True

    # Account is unnecessary when list the snapshots.
    vm_object = Vmrun(local_vmx, 'NotEmpty', 'NotEmpty')
    vm_res = vm_object.listSnapshots()[1]
    snapshots = get_snapshot_list(vm_res)
    # CleanSnap must be the first snapshot.
    return gv.g_vm_clean_snap != snapshots[0]


def vm_reg_image(machine_id, os_id):
    """
    Register a vmware image with the vmware server or workstation,
    including unregister image, clean up older images, copy vm image files,
    rename machine name, register image, take clean snapshot.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    :param os_id:
        The `OSID` column in `OS_Info` table.
    :returns:
        * successful - 0
        * failed - raise exception
    """
    gvt, hdl = util.export_target_modules()

    qs_res = dbx.queryx_target_os_info(os_id)
    target_os_platform, vm_image_template_src = qs_res[0], qs_res[2]
    res = vm_check_template_image(vm_image_template_src)
    if res != errcode.ER_SUCCESS:
        LOGGER.error(
            "The virtual image template <%s> of OS<%s> is invalid."
            % (vm_image_template_src, os_id),
            extra={'error_level': 2})
        raise Exception(errcode.ER_FILE_NONEXIST)

    stop_machines(machine_id)

    (machine_name,) = dbx.queryx_machine_name(machine_id)

    (image_full, image_user, image_pwd) = dbx.queryx_table(
        'Machine_Reimage', 'ImageSource, LoginUsr, LoginPwd',
        "MachineID=%s and OSID=%s" % (machine_id, os_id),
        only_one=True)
    vm_image_dir_dst = os.path.dirname(image_full)
    util.delete_path(vm_image_dir_dst, is_raise=True)

    clean_up_older_images(machine_id, gv.g_vm_images_max_count - 1)

    vm_object = Vmrun(image_full, image_user, image_pwd)
    LOGGER.info("Begin to register the VM image for (Machine %s, OS %s)" % (machine_id, os_id))
    try:
        LOGGER.info("Copying VM image from template server <%s> to local destination <%s>."
                    % (vm_image_template_src, vm_image_dir_dst))
        shutil.copytree(vm_image_template_src, vm_image_dir_dst)

        # Lauch the VM image and rename it as the target machine name
        vm_object.startAndWait()

        # transfer rename script, and execute it.
        if target_os_platform.lower() == 'linux':
            # if platform is linux, we should set the account as root to execute rename.
            vm_object.setGuestInfo('root', image_pwd)
        elif target_os_platform.lower() == 'windows':
            vm_object.createDirectoryInGuest(gvt.gt_vm_root)

        vm_object.copyFileFromHostToGuest(gvt.gt_vm_rename_script_local, gvt.gt_vm_rename_script_client)
        if target_os_platform.lower() == 'linux':
            # revert the account.
            vm_object.runProgramInGuest(gvt.gt_vm_rename_script_client, False, image_user, machine_name)
            vm_object.setGuestInfo(image_user, image_pwd)
        elif target_os_platform.lower() == 'windows':
            vm_object.runProgramInGuest(gvt.gt_vm_rename_script_client, False, machine_name)

        # reboot vm machine to make rename operation take effect
        vm_object.resetAndWait()
        vm_object.stopAndWait()

        # Get MAC address from database or vmx config
        mac_addr = util.get_mac_addr(machine_id, image_full)

        #Get Machine Info from database
        cpu_core, mem_size = util.get_machine_config(machine_id)
        mem_size = max(mem_size,
                       int(dbx.queryx_table('OS_Info', 'RequiredMemSize', 'OSID=%s' % os_id, only_one=True)[0]) * 1024)

        # Init some config of vm image
        # Network to bridged
        # static MAC addresss
        # Memory size to 2GB
        # One processer 2 core
        opfilter = {'ethernet0.connectionType': '"bridged"',
                    'ethernet0.address': mac_addr,
                    'ethernet0.addressType': '"static"',
                    'memsize':'"%s"' % mem_size,
                    'numvcpus':'"%s"' % cpu_core,
                    'cpuid.coresPerSocket':'"1"'}
        defconf = ('ethernet0.generatedAddress', 'ethernet0.generatedAddressOffset')
        vm.init_vmx(image_full, opfilter, defconf)

        # Take the clean snapshot
        vm_object.snapshot(gv.g_vm_clean_snap)
        vm_object.startAndWait()

        # Update the database
        sql_str = ("update Machine_Reimage set ImageSource='%s', ImageSnapshot='%s', "
            "LoginUsr='%s', LoginPwd='%s' where MachineID=%s and OSID=%s"
            % (image_full, gv.g_vm_clean_snap, image_user, image_pwd, machine_id, os_id))
        res = SQLServerDB.execute(sql_str)
        if res:
            LOGGER.error(
                "Failed to update Machine_Reimage of Machine %s OS %s." % (machine_id, os_id),
                extra={'error_level': 2})
            raise Exception(errcode.ER_DB_COMMON_ERROR)
    except Exception, error:
        util.process_error(error)
        raise Exception('Failed to register Machine %s, OS %s' % (machine_id, os_id))
    return errcode.ER_SUCCESS


def clean_up_older_images(machine_id, reserve_count):
    """
    Clean up older images of this virtual machine, based on modification time.
    And reserve `reserve_count` at most.
    """
    folders_info = []
    rows = dbx.queryx_all_images(machine_id)
    for row in rows:
        folder_path = os.path.dirname(row[0])
        if folders_info and folder_path in zip(*folders_info)[0]:
            continue
        if os.path.exists(folder_path):
            folders_info.append((folder_path, os.stat(folder_path).st_mtime))
    folders_info.sort(key=lambda x: x[1], reverse=True)
    for folder_info in folders_info[reserve_count:]:
        util.delete_path(folder_info[0])
    return


def remove_customized_snapshots(machine_id, os_id):
    res = errcode.ER_FAILED
    try:
        snapshots = list_snapshots(machine_id, os_id)
        if len(snapshots) > 1:
            LOGGER.info('Machine %s OS %s has %d customized snapshots, which will be removed.'
                % (machine_id, os_id, len(snapshots)-1))
        (image_full, image_user, image_pwd) = dbx.queryx_table(
            'Machine_Reimage', 'ImageSource, LoginUsr, LoginPwd',
            "MachineID=%s and OSID=%s" % (machine_id, os_id),
            only_one=True)
        vm_object = Vmrun(image_full, image_user, image_pwd)
        for snapshot in snapshots[:0:-1]:
            LOGGER.info('Removing customized snapshot "%s" for Machine %s OS %s'
                % (snapshot, machine_id, os_id))
            vm_object.deleteSnapshot(snapshot)
        res = errcode.ER_SUCCESS
    except Exception, error:
        LOGGER.warning('Failed to remove customized snapshots for Machine %s OS %s: %s'
            % (machine_id, os_id, error))
    return res

def deploy_vm_image_single(machine_id, os_id, lock=True, force=True, reset_local=True):
    """
    Deploy a single image. During this process, this machine will be locked
    with :class:`.VmLock`.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    :param os_id:
        The `OSID` column in `OS_Info` table.
    :param lock:
        Whether lock this virtual machine during deploying process.
    :param force:
        Deploy image anyway if `force` is `True`, otherwise only deploy image
        when local image is inexistent or server image has updated.
    :param reset_local:
        Reset thread local data if `reset_local` is `True`.
    :returns:
        * successful - 0
        * failed - raise exception
    """

    if reset_local:
        util.reset_thread_data()
        util.set_thread_data(machine_id=machine_id, os_id=os_id)

    gvt, hdl = util.import_target_modules(os_id, True)

    #Validate os_id
    qs_res = dbx.queryx_target_os_info(os_id)
    target_os_platform, vm_image_template_src = qs_res[0], qs_res[2]

    if target_os_platform.lower() not in ("windows", "linux"):
        LOGGER.error(
            "Unsupported OS platform %s (OSID: %s) on machine %s"
            % (target_os_platform, os_id, machine_id),
            extra={'error_level': 2})
        raise Exception(errcode.ER_GA_PF_UNSUPPORT)

    (image_full, image_user) = dbx.queryx_image_info(machine_id, os_id)[1:3]
    if target_os_platform.lower() == 'linux':
        span = re.match(r'/(.+?)/(.+?)/(.+)', gvt.gt_vm_root).span(2)
        gvt.gt_vm_root = gvt.gt_vm_root[:span[0]] + image_user + gvt.gt_vm_root[span[1]:]
        gvt.gt_vm_rename_script_client = gvt.gt_vm_rename_script_client[:span[0]] + image_user + \
                                         gvt.gt_vm_rename_script_client[span[1]:]

    if not force:
        if not need_update(image_full, vm_image_template_src):
            if remove_customized_snapshots(machine_id, os_id) == errcode.ER_SUCCESS:
                LOGGER.info('Local image "%s" is newest, no need to deploy it again' % (image_full))
                return "%s:%s:0" % (machine_id, os_id)
        else:
            LOGGER.info('A newer image generated, need to deploy "%s"' % (image_full))
    else:
        LOGGER.info('Deploy "%s" forcelly.' % (image_full))

    if lock:
        with VmLock(machine_id):
            vm_reg_image(machine_id, os_id)
    else:
        vm_reg_image(machine_id, os_id)
    return errcode.ER_SUCCESS


def vm_prepare_clone_image(vm_object, opfilter, target_os_platform):
    """
    Prepare a clone image from an local image, and also do some rename/update
    configuration things.

    :param vm_object:
        The instance of :class:`nicu.vm.Vmrun`.
    :param opfilter:
        The customer filter for cloned vmx configure.
    :param target_os_platform:
        The OS platform of target VM.
    :returns:
        * successful - 0
        * failed - raise exception
    """
    gvt, hdl = util.export_target_modules()
    # Set random machine name when first launching
    vm_object.startAndWait()
    if target_os_platform.lower() == 'windows':
        vm_object.copyFileFromHostToGuest(gvt.gt_vm_prepare_script_full,
            gvt.gt_vm_prepare_script_client)
        vm_object.runProgramInGuest(gvt.gt_vm_prepare_script_client, False, 'Setup')
    elif target_os_platform.lower() == 'linux':
        # if platform is linux, we should set the account as root to execute rename.
        vm_object.setGuestInfo('root', vm_object.VM_GUESTPWD)
        machine_name = 'vmtest-%s' % uuid.uuid1()
        vm_object.runProgramInGuest(gvt.gt_vm_rename_script_client, False, vm_object.VM_GUESTUSR, machine_name)
        vm_object.setGuestInfo(vm_object.VM_GUESTUSR, vm_object.VM_GUESTPWD)

    vm_object.stopAndWait()

    try:
        # Change Network to NAT and generate new MAC address
        opfilter['ethernet0.connectionType'] = '"nat"'
        opfilter['ethernet0.addressType'] = '"generated"'
        delconf = ('ethernet0.address',)
        #swallow the CommonVmwareException during modifying VMX config
        vm.init_vmx(vm_object.VM_FILE, opfilter, delconf)
    except CommonVmwareException, error:
        LOGGER.warning('Failed to initial set vmx file "%s": %s' % (vm_object.VM_FILE, error))
    return errcode.ER_SUCCESS


def deploy_vm_image(pair_list):
    """
    Deploy VMware Images to the server.

    *Command Format:*
        ``DeployVMImage [MachineID:OSID;MachineID:OSID;...]``

    :param MachineID:
        The `MachineID` column in `Machine_Info` table.
    :param OSID:
        The `OSID` column in `OS_Info` table.

    .. note::
        [machine_id:os_id;machine_id:os_id;...] is a optional parameter.
        * If DeployVMImage does not have this optional parameter,
        it will handle all VMware images for this server.
        * If DeployVMImage has this optional parameter,
        it will only handle the specific VMware images.
    """
    # Get the ServerID and vm_type of current Server
    server_id, vm_db_type = dbx.queryx_table(
        'GhostServer', 'ServerID, ServerType',
        "ServerName = '%s'" % (socket.gethostname()), only_one=True)

    if not pair_list:
        # If there is not any parameter, deploy all VM images
        # for the current server registed in the database.
        # Normally, when the all VM image templates are updated,
        # we could use this command
        pair_list = dbx.queryx_table(
            'Machine_Reimage', 'MachineID, OSID',
            "ServerID = %s and IsVM = 1" % (server_id))

    deploy_result_list = []
    for machine_id, os_id in pair_list:
        LOGGER.info("Deploy Machine %s, OS %s" % (machine_id, os_id))
        try:
            # Since that deploy_vm_image will process multiple machines in one function,
            # so we have to reset the thread local data in deploy_vm_image_single every time.
            deploy_vm_image_single(machine_id, os_id)
            deploy_result_list.append("%s:%s:0" % (machine_id, os_id))
        except Exception, error:
            LOGGER.error('Failed to deploy Machine %s, OS %s: %s' % (machine_id, os_id, error))
            deploy_result_list.append("%s:%s:1" % (machine_id, os_id))
    LOGGER.info("Deploy Result List is %s", deploy_result_list)
    return ';'.join(deploy_result_list)


def archive_vm_image(machine_id, os_id, archive_dst, config):
    """
    Archive the specific VMware image to specific destiantion.

    *Command Format:*
        ``ArchiveVMImage MachineID OSID Destination [Email]``

    :param MachineID:
        The `MachineID` column in `Machine_Info` table.
    :param OSID:
        The `OSID` column in `OS_Info` table.
    :param Destination:
        The archive destination.
    :param Email:
        The email adderss for receiving the notification email of Ghost
        status.
    """
    gvt, hdl = util.export_target_modules()

    qs_res = dbx.queryx_image_info(machine_id, os_id)
    image_full, image_user, image_pwd, server_vm_root = qs_res[1:]

    (machine_name, cur_seq_id) = dbx.queryx_table(
        'Machine_Info', 'MachineName, CurrentSeqID',
        'MachineID=%s' % machine_id, only_one=True)

    target_os_platform = dbx.queryx_target_os_info(os_id)[0]
    if target_os_platform.lower() == 'linux':
        span = re.match(r'/(.+?)/(.+?)/(.+)', gvt.gt_vm_root).span(2)
        gvt.gt_vm_root = gvt.gt_vm_root[:span[0]] + image_user + gvt.gt_vm_root[span[1]:]
        gvt.gt_vm_rename_script_client = gvt.gt_vm_rename_script_client[:span[0]] + image_user + \
                                         gvt.gt_vm_rename_script_client[span[1]:]

    with VmLock(machine_id):
        vm_object = Vmrun(image_full, image_user, image_pwd)

        vm_image_dir_dst = os.path.dirname(image_full)
        vm_install_log_dst = os.path.join(vm_image_dir_dst, gv.g_vm_install_log)

        # Try to start the target image
        (vm_cmd, vm_res) = vm_object(is_raise=False, level='warning').startAndWait()

        # if image start failed, won't need to execute copy log file
        # or stop image action
        if not vm_res:
            vm_install_log_src = gvt.gt_vm_root + gvt.gt_sep + gv.g_vm_script_log
            #Try to copy the install log file
            vm_object(is_raise=False, level='warning').copyFileFromGuestToHost(
                vm_install_log_src, vm_install_log_dst)
            # Try to stop the image before archive
            vm_object.stopAndWait()

        # copy the images to clone destination
        # For the clone dest root, we append a uniq id dir after machine_name dir to solve this problem:
        # If previous clone image can't be stopped due to 3rd party vmtools crashed,
        # the next archiveImage request will also fail because it can't delete the previous clone image.
        vm_img_archive_dir_dst = os.path.join(gv.g_vm_image_archive_root, machine_name, str(uuid.uuid4()))
        vm_image_vmx_dst = os.path.join(vm_img_archive_dir_dst, os.path.basename(image_full))
        vm_install_log_archive_dst = os.path.join(vm_img_archive_dir_dst, gv.g_vm_install_log)
        util.delete_path(vm_img_archive_dir_dst, is_raise=True)
        if not os.path.exists(vm_img_archive_dir_dst):
            os.makedirs(vm_img_archive_dir_dst)
        LOGGER.info('Archive transfer folder "%s"' % (vm_img_archive_dir_dst))

        # get list of snapshot
        (vm_cmd, vm_res) = vm_object.listSnapshots()
        snapshots = get_snapshot_list(vm_res)
        total_snapshot = len(snapshots)

        # If no extra snapshot was made, we will clone the vm image with removing useless files.
        # Otherwise, we will copy the whole vm folder
        try:
            if total_snapshot <= 1:
                vm_object.clone('"%s"' % vm_image_vmx_dst, 'full', '')
            else:
                vm.copy_vm(vm_image_dir_dst, vm_img_archive_dir_dst)
                vm.init_vmx(vm_image_vmx_dst)
        except Exception, error:
            # try to remove the clone image
            util.delete_path(vm_img_archive_dir_dst)
            raise Exception('Failed to clone vm folder "%s": %s' % (vm_img_archive_dir_dst, error))

        # move the install log file to clone destination
        util.delete_path(vm_install_log_archive_dst)
        try:
            shutil.move(vm_install_log_dst, vm_install_log_archive_dst)
        except Exception, error:
            # continue if error happens during copying installLog.txt
            LOGGER.warning(
                "Failed to move installLog.txt from %s to %s: %s"
                % (vm_install_log_dst, vm_install_log_archive_dst, error))

        # get an instance of clone image
        vm_object_archive = Vmrun(vm_image_vmx_dst, image_user, image_pwd)

        # collect information and insert to dict opfilter
        if not isinstance(config, dict):
            LOGGER.warning("Configuration of VMX has bad format.")
            config = {}
        opfilter = init_opfilter(image_full, cur_seq_id, total_snapshot, args=config)

        #cal vm_prepare_clone_image to [rename machine] & [modify config like CPU or Memory]
        try:
            vm_prepare_clone_image(vm_object_archive, opfilter, target_os_platform)
        except Exception, error:
            util.process_error(error)
            #try to stop the clone image
            vm_object_archive(is_raise=False).stopAndWait()
            #try to remove the clone image
            util.delete_path(vm_img_archive_dir_dst)
            raise Exception("Failed to prepare the environment before clone: %s" % (error))

        # Try to copy the image files from clone destination to archive destination
        LOGGER.info("Begin to copy %s to %s" % (vm_img_archive_dir_dst, archive_dst))
        try:
            if not os.path.exists(archive_dst):
                os.makedirs(archive_dst)
            vm.copy_vm(vm_img_archive_dir_dst, archive_dst)
        except Exception, error:
            LOGGER.error("Failed to copy vm image from clone destination to archive destination: %s" % error)
            raise Exception(error)
        finally:
            # try to remove the clone image
            util.delete_path(vm_img_archive_dir_dst)
            # Start the local image
            vm_object(is_raise=False, level='warning').startAndWait()
    return errcode.ER_SUCCESS


def archive_vm_image_report(machine_id, os_id, archive_dst,
                            email_to, cmd_ret_code):
    """
    Sending archive vm image report to user.

    :param cmd_ret_code:
        The return code for ArchiveVMImage command.

    *Command Format:*
        ``ArchiveVMImage MachineID OSID Destination [Email]``

    :param MachineID:
        The `MachineID` column in `Machine_Info` table.
    :param OSID:
        The `OSID` column in `OS_Info` table.
    :param Destination:
        The archive destination.
    :param Email:
        The email adderss for receiving the notification email of Ghost
        status.

    .. note::
        This command is called only when failed in `ArchiveVMImage`
        command, or `Email` option exists in `ArchiveVMImage` command.
    """

    email_content = report.generate_html_header()
    # Generate status table
    col_name = ['Status', 'Comment', 'Destination']
    email_content += report.generate_table_header('Archive Status', col_name)
    row = []
    status = ''
    comment = ''
    if cmd_ret_code == errcode.ER_SUCCESS:
        status = 'Success'
        comment = 'success'
    else:
        status = 'Failed'
        comment = util.get_error_desr(cmd_ret_code)
    row.append(status)
    row.append(comment)
    row.append(archive_dst)
    email_content += report.generate_row(row)
    email_content += report.generate_table_footer()

    # Generate machine info table
    col_name = ['Machine Info', 'Content']
    email_content += report.generate_table_header('Machine', col_name)

    (machine_name, seq_id) = dbx.queryx_table(
        'Machine_Info', ['MachineName', 'CurrentSeqID'],
        'MachineID=%s' % (machine_id), only_one=True)
    machine_info = ['Machine Name', machine_name]

    qs_res = dbx.queryx_table(
        'OS_Info',
        ["distinct OSName+' '+OSVersion+' ('+convert(varchar,OSBit)+'-bit '+OSPatch+' '+OSLanguage+')' as CombinedOS"],
        "OSID=%s" % (os_id), only_one=True)
    os_info = ['Operating System', qs_res[0]]

    col_value = ""
    if seq_id and seq_id != -1:
        (steps_str,) = dbx.queryx_table(
            'GhostSequences', 'Sequence',
            'SeqID=%s' % (seq_id), only_one=True)
        step_ids = steps_str.split(",")
        for step_id in step_ids:
            try:
                qs_res = dbx.queryx_step_info(step_id)
                (step_type, step_cmd, step_flags, step_basepath,
                 step_path_suffix, step_latest) = qs_res[0:6]
            except Exception, error:
                LOGGER.error("Can not get the Step information of "
                             "StepID<%s>: %s" % (step_id, error))
                continue
            if step_type == 0:
                if step_basepath:
                    col_value += ("Execute command: %s%s %s<br/>"
                                  % (step_basepath, step_cmd, step_flags))
                else:
                    col_value += ("Execute command: %s %s<br/>"
                                  % (step_cmd, step_flags))
            elif step_type == 1:
                if step_latest:
                    col_value += ("Install Latest installer: %s<br/>"
                                  % (step_basepath))
                else:
                    col_value += ("Install installer: %s<br/>"
                                  % (step_basepath))
            else:
                continue
    else:
        col_value = "None of special software had been installed."
    software_info = ['Software Info', col_value]
    email_content += report.generate_row(machine_info)
    email_content += report.generate_row(os_info)
    email_content += report.generate_row(software_info)
    email_content += report.generate_table_footer()
    email_content += report.generate_html_footer()

    # Sending email
    email_object = Mail(gv.g_smtp_server, 25, gv.g_reply_email_from)
    subject = ("[Archive Image Report][%s] %s"
               % (status.upper(), machine_name))
    email_to_cc = None
    if cmd_ret_code != errcode.ER_SUCCESS:
        email_to_cc = [gv.g_sast_group_email]
    email_object.send(email_to, subject, email_content, 'html',
                      'utf-8', email_to_cc)
    return errcode.ER_SUCCESS


def release_machine(machine_id, service_id):
    """
    Release the virtual machine (delete file lock).

    *Command Format:*
        ``ReleaseMachine ServiceID MachineID``

    :param ServiceID:
        The `ServiceID` column in `Service` table.
    :param MachineID:
        The `MachineID` column in `Machine_Info` table.

    .. note::
        This command only applies for vmware machine, to delete file lock
        after failed to ghost.
    """
    VmLock.release_force(machine_id)
    return errcode.ER_SUCCESS


def start_vm(machine_id, os_id):
    """
    Start a virtual machine.

    *Command Format:*
        ``StartVM MachineID [OSID]``

    :param MachineID:
        The `MachineID` column in `Machine_Reimage` table.
    :param OSID:
        The `OSID` column in `Machine_Reimage` table.
    """
    qs_res = dbx.queryx_image_info(machine_id, os_id)
    image_full, image_user, image_pwd = qs_res[1:4]

    with VmLock(machine_id):
        vm_object = Vmrun(image_full, image_user, image_pwd)
        vm_object.startAndWait()
    return errcode.ER_SUCCESS


def shutdown_vm(machine_id, os_id):
    """
    Shutdown a virtual machine.

    *Command Format:*
        ``ShutdownVM MachineID [OSID]``

    :param MachineID:
        The `MachineID` column in `Machine_Reimage` table.
    :param OSID:
        The `OSID` column in `Machine_Reimage` table.
    """
    qs_res = dbx.queryx_image_info(machine_id, os_id)
    image_full, image_user, image_pwd = qs_res[1:4]

    with VmLock(machine_id):
        vm_object = Vmrun(image_full, image_user, image_pwd)
        vm_object.stopAndWait()
    return errcode.ER_SUCCESS


def restart_vm(machine_id, os_id):
    """
    Restart a virtual machine.

    *Command Format:*
        ``RestartVM MachineID [OSID]``

    :param MachineID:
        The `MachineID` column in `Machine_Reimage` table.
    :param OSID:
        The `OSID` column in `Machine_Reimage` table.
    """
    qs_res = dbx.queryx_image_info(machine_id, os_id)
    image_full, image_user, image_pwd = qs_res[1:4]

    with VmLock(machine_id):
        vm_object = Vmrun(image_full, image_user, image_pwd)
        vm_object.resetAndWait()
    return errcode.ER_SUCCESS


def is_vm_running(machine_id, os_id):
    """
    Judge whether virtual machine is running.

    *Command Format:*
        ``IsVMRunning MachineID [OSID]``

    :param MachineID:
        The `MachineID` column in `Machine_Reimage` table.
    :param OSID:
        The `OSID` column in `Machine_Reimage` table.
    """
    qs_res = dbx.queryx_image_info(machine_id, os_id)
    image_full, image_user, image_pwd = qs_res[1:4]

    vm_object = Vmrun(image_full, image_user, image_pwd)
    return vm_object.isRunning()


def list_snapshots(machine_id, os_id):
    """
    List snapshots of virtual machine

    *Command Format:*
        ``ListSnapshots MachineID [OSID]``

    :param MachineID:
        The `MachineID` column in `Machine_Info` table.
    :param OSID:
        The `OSID` column in `OS_Info` table.
        Default is `CurrentOSID` column in `Machine_Info` table.
    """
    qs_res = dbx.queryx_image_info(machine_id, os_id)
    image_full, image_user, image_pwd = qs_res[1:4]

    vm_object = Vmrun(image_full, image_user, image_pwd)
    (vm_cmd, vm_res) = vm_object.listSnapshots()
    snapshots = get_snapshot_list(vm_res)
    return snapshots


def take_snapshot(snapshot_name, machine_id, os_id, shutdown=False):
    """
    Take snapshot of the virtual machine.

    *Command Format:*
        ``TakeSnapshot SnapshotName MachineID [OSID] [Shutdown]``

    :param SnapshotName:
        The name of snapshot.
    :param MachineID:
        The `MachineID` column in `Machine_Reimage` table.
    :param OSID:
        The `OSID` column in `Machine_Reimage` table.
    :param Shutdown:
        Whether shutdown virtual machine before taking snapshot.
        Default is 0.

    .. note::
        This command only applies for vmware machine.
    """
    qs_res = dbx.queryx_image_info(machine_id, os_id)
    image_full, image_user, image_pwd = qs_res[1:4]

    with VmLock(machine_id):
        # Make sure the snapshot name is unique when taking a new snapshot.
        snapshots = list_snapshots(machine_id, os_id)
        snapshots = [x.lower() for x in snapshots]
        if snapshot_name in snapshots:
            raise Exception('Duplicated snapshot name "%s" for Machine %s OS %s'
                % (snapshot_name, machine_id, os_id))
        non_cleansnap_count = sum([x!=gv.g_vm_clean_snap.lower() for x in snapshots])
        if non_cleansnap_count >= gv.g_vm_max_customized_snapshot_num:
            raise Exception('Machine %s OS %s support at most %d customized snapshots.'
                % (machine_id, os_id, gv.g_vm_max_customized_snapshot_num))

        vm_object = Vmrun(image_full, image_user, image_pwd)
        if shutdown:
            vm_object(is_raise=False, level='warning').stopAndWait()
            vm_object.snapshot(snapshot_name)
            vm_object.startAndWait()
        else:
            vm_object.snapshot(snapshot_name)
    return errcode.ER_SUCCESS


def delete_snapshot(snapshot_name, machine_id, os_id):
    """
    Delete snapshot of the virtual machine.

    *Command Format:*
        ``DeleteSnapshot SnapshotName MachineID [OSID]``

    :param SnapshotName:
        The name of snapshot.
    :param MachineID:
        The `MachineID` column in `Machine_Reimage` table.
    :param OSID:
        The `OSID` column in `Machine_Reimage` table.
    """
    qs_res = dbx.queryx_image_info(machine_id, os_id)
    image_full, image_user, image_pwd = qs_res[1:4]

    with VmLock(machine_id):
        vm_object = Vmrun(image_full, image_user, image_pwd)
        vm_object.deleteSnapshot(snapshot_name)
    return errcode.ER_SUCCESS


def revert_snapshot(snapshot_name, machine_id, os_id):
    """
    Revert to snapshot of the virtual machine.

    *Command Format:*
        ``RevertSnapshot SnapshotName MachineID [OSID]``

    :param SnapshotName:
        The name of snapshot.
    :param MachineID:
        The `MachineID` column in `Machine_Reimage` table.
    :param OSID:
        The `OSID` column in `Machine_Reimage` table.
    """
    qs_res = dbx.queryx_image_info(machine_id, os_id)
    image_full, image_user, image_pwd = qs_res[1:4]

    with VmLock(machine_id):
        vm_object = Vmrun(image_full, image_user, image_pwd)
        vm_object.revertToSnapshot(snapshot_name)
    return errcode.ER_SUCCESS


def get_snapshot_list(vm_res):
    """
    Process the result of listSnapshots command.

    :param vm_res:
        The result of command.

    :returns snapshots:
        The list of snapshot name.
    """
    snapshots = []
    try:
        snapshots = [name.rstrip('\r\n') for name in vm_res[1:]]
    except Exception, e:
        LOGGER.error('Process Snapshot Error: %s' % e, extra={'error_level': 2})
    return snapshots


def init_opfilter(vm_image_vmx, seq_id, total_snapshot, args={}):
    """
    Init a opfilter to change config of VMX.
    Add Memory size or CPU info in args in the future.

    :param vm_image_vmx:
        The full path of VMX.
    :param seq_id:
        The SequenceID of current task.
    :param total_snapshot:
        The count of snapshots of current VM.
    :param args:
        The dict of Config to update VMX.

    :returns opfilter:
        Config of VMX.
    """
    opfilter = {}
    try:
        # init display name
        cur_diplay_name = vm.get_vmx_conf(vm_image_vmx, 'displayName')
        if cur_diplay_name:
            LOGGER.info("ArchiveVMImage: Update the display name of "
                        "virtual image based on the sequence name.")
            if seq_id and seq_id != -1:
                try:
                    qs_res = dbx.queryx_table('GhostSequences', 'SeqName',
                        "SeqID=%s" % (seq_id), only_one=True)
                    cur_diplay_name = ('"%s %s"' % (cur_diplay_name.strip('\'"'), qs_res[0]))
                    opfilter['displayName'] = cur_diplay_name
                    LOGGER.info("ArchiveVMImage: Fill key:displayName value:%s"
                                " into opfilter" % (cur_diplay_name))
                except Exception, error:
                    # continue if can't get SeqName
                    util.process_error(error)
            else:
                LOGGER.info("ArchiveVMImage: Keep the original display"
                            " name of virtual image, because "
                            "the sequence ID is %s." % (seq_id))
        else:
            LOGGER.warning("ArchiveVMImage: The original display name of the virtual image is none.")

        # init uuid action
        if total_snapshot > 1:
            opfilter['uuid.action'] = '"keep"'

        # init other config, such as memory size, cpu etc.
        conf = vm.load_vmx_conf(vm_image_vmx)
        for key in args:
            if key in conf:
                opfilter[key] = args[key]
    except Exception, error:
        LOGGER.error("VMX Config opfilter init error: %s" % error, extra={'error_level': 2})
    return opfilter


def get_active_machines():
    """
    Get a list of machine id that images are actived.
    """
    # Get the ServerID and vm_type of current Server
    (server_id,) = dbx.queryx_table(
        'GhostServer', 'ServerID',
        "ServerName = '%s'" % (socket.gethostname()), only_one=True)
    vm_object = Vmrun('NotEmpty', 'NotEmpty', 'NotEmpty')
    (vm_cmd, vm_res) = vm_object.list()
    machine_ids = set([])
    for image in vm_res[1:]:
        machine_name = image.split('\\')[2]
        (machine_id,) = dbx.queryx_table('Machine_Info', 'MachineID',
            "MachineName='%s'" % machine_name, only_one=True)
        machine_ids.add(machine_id)
    return list(machine_ids)


def start_all_machines():
    """
    Start all virtual machines deployed on the server.

    *Command Format:*
        ``StartAllMachine``

    .. note::
        Return a string consist of machine id that can't be started.
    """
    (server_id,) = dbx.queryx_server_id(socket.gethostname())
    machines = dbx.queryx_available_machines(server_id)
    active_machines = get_active_machines()
    ret_val = []
    for machine_id, os_id in machines:
        if (machine_id,) in active_machines:
            continue
        image_full, image_user, image_pwd = dbx.queryx_image_info(machine_id, os_id)[1:4]
        with VmLock(str(machine_id)):
            # start machine by current OS
            vm_object = Vmrun(image_full, image_user, image_pwd)
            (vm_cmd, vm_res) = vm_object.startAndWait()
            if vm_res:
                ret_val.append(str(machine_id))
    return ';'.join(ret_val)


def delete_expired_image(max_age):
    """
    Delete expired VM images on local server.

    *Command Format:*
        ``DeleteExpiredImage``

    :param max_age:
        The function will delete vm images which wasn't used for 'max_age'.
        'max_age' is in days
    """
    (server_id,) = dbx.queryx_server_id(socket.gethostname())
    machines = dbx.queryx_available_machines(server_id)
    for machine_id, os_id in machines:
        with VmLock(str(machine_id)):
            images = dbx.queryx_all_images(
                machine_id, 'ServerID=%s and OSID!=%s' % (server_id, os_id))
            for image_full, _, _ in images:
                vm_root = os.path.dirname(image_full)
                mtime = os.path.getmtime(vm_root)
                # remove expired images
                delta = datetime.now()-datetime.fromtimestamp(mtime)
                if delta.days > max_age:
                    LOGGER.info("Delete expired image [%s]" % vm_root)
                    util.delete_path(vm_root)
    return errcode.ER_SUCCESS


def export_vm(machine_id, os_id):
    """
    Export image to g_export_vmroot. Cleanup will be performed
    if folder size exceeds g_export_images_size_limit.

    *Command Format:*
        ``ExportVM MachineID [OSID]``

    :param MachineID:
        The `MachineID` column in `Machine_Reimage` table.
    :param OSID:
        The `OSID` column in `Machine_Reimage` table.
    """
    vm_dir = []

    (os_name, os_version, os_bit, os_patch, os_language) = map(str, dbx.queryx_table(
        "OS_Info",
        "OSName, OSVersion, OSBit, OSPatch, OSLanguage",
        "OSID=%s" % os_id,
        only_one=True))

    dir_size = 0L
    for root, dirs, files in os.walk(gv.g_export_vmroot):
        dir_size += sum([os.path.getsize(os.path.join(root, name)) for name in files])
        for file_name in files:
            file_suffix = os.path.splitext(file_name)[1][1:]
            if file_suffix.lower() == "vmx":
                vm_dir.append((root, get_last_modified_time(root)))
                break
    if dir_size > gv.g_export_images_size_limit:
        # remove the oldest 10 images if exceeding limit size
        num_to_del = min(len(vm_dir), 10)
        LOGGER.info('Remove the oldest %s image roots under:%s due to size limitation.'
                    % (num_to_del, gv.g_export_vmroot))
        for folder_to_del in sorted(vm_dir, cmp=lambda x, y: cmp(x[1], y[1]))[:num_to_del]:
            util.delete_path(folder_to_del[0])

    ymd = time.strftime('%Y_%m_%d', time.localtime(time.time()))
    hms = time.strftime('%H_%M_%S', time.localtime(time.time()))
    export_path = gv.g_export_vmroot + '\\' + os_name + ' ' + os_version + \
                    '\\' + os_bit + '-bit' + \
                    '\\' + os_patch + ' ' + os_language + \
                    '\\' + machine_id + '_' + os_id + '_' + ymd + '_' + hms

    archive_vm_image(machine_id, os_id, export_path, None)
    return export_path