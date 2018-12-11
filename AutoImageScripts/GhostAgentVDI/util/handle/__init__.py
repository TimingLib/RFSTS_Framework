from __future__ import with_statement
import os
import re
import socket
import logging
import shlex
import traceback
from SocketServer import StreamRequestHandler

from nicu.decor import valid_param
import nicu.misc as misc
import nicu.errcode as errcode
import nicu.version as version
import nicu.notify as notify

import globalvar as gv
import util
import util.dbx as dbx
import hdl_vm


__all__ = [
    'EchoRequestHandler',
]

LOGGER = logging.getLogger(__name__)


class EchoRequestHandler(StreamRequestHandler):
    """
    All methods follow the rules below:

    :param cmd_paras:
        GhostAgent command and its parameters.
    :param client_addr:
        Where we receive this GhostAgent command from.
    :returns:
        the return code.
    return code is one of the following values:
        * **0**       - Success!
        * **Other**   - Failed, 1value is error code.
    """

    @valid_param(cmd_paras=(list, 'len(x)>=3 and len(x)<=5'))
    def ghost_machine(self, cmd_paras, client_addr, is_grab_image=False):
        """
        Ghost a machine with specific OS, execute a serial of steps
        after ghost, and send a notification email of ghost status.

        :param is_grab_image:
            Whether grab new image or not.

        *Command Format:*
            ``GhostClient MachineID OSID [SequenceID] [Email]``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
        :param SequenceID:
            The `SeqID` column in `GhostSequences` table.
        :param Email:
            The email adderss for receiving the notification email of Ghost
            status.
        """
        ret_code = errcode.ER_SUCCESS
        machine_id = None
        os_id = None
        email_to = ''
        try:
            # Analyze the GhostAgent command and its parameters
            machine_id = cmd_paras[1]
            os_id = cmd_paras[2]
            seq_id = -1
            if len(cmd_paras) == 5:
                # GhostClient machine_id os_id SequenceID Email
                seq_id = cmd_paras[3]
                email_to = cmd_paras[4]
            elif len(cmd_paras) == 4:
                temp = cmd_paras[3]
                email_re = re.compile('(.*)@(.*).(.*)')
                is_email = email_re.search(temp)
                email_to = temp if is_email else ''
                seq_id = -1 if is_email else temp

            util.set_thread_data(
                machine_id=machine_id, os_id=os_id, seq_id=seq_id, email_to=email_to)

            # Get detail information about Machine, OS from Database
            qs_res = dbx.queryx_machine_info(machine_id)
            machine_name = qs_res[0]

            # Need to register at the beginning
            gv.g_ns.register(machine_name, False)

            qs_res = dbx.queryx_image_info(machine_id, os_id)
            is_vm_image = qs_res[0]

            gvt, hdl = util.import_target_modules(os_id, is_vm_image)

            ret_code = hdl.ghost_machine(
                machine_id, os_id, seq_id, email_to, client_addr, is_grab_image)
        except Exception, error:
            notify.NotifyClient().send(machine_id, 'GhostClient', 'None')
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
            util.send_ghost_error_email()
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x)>=2'), mode=(object, 'x==0 or x==1'))
    def daily_ghost(self, cmd_paras, mode, client_addr):
        """
        For Daily Ghost, we do not use the scheduled task of Ghost Console.
        We create a Windows scheduled task for each machine(including Windows,
        Linux and Mac) on a Windows Server. In this Windows scheduled task,
        it will run the "DailyCommand.py" to trigger the daily ghost for each
        machine.

        :param mode: pause daily ghost or restart daily ghost.
        mode is one of the following values:
            * **0** - Pause daily ghost
            * **1** - Restart daily ghost

        *Command Format:*
            ``PauseDaily MachineID``

            ``RestartDaily MachineID``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        """
        ret_code = errcode.ER_SUCCESS
        try:
            machine_id = cmd_paras[1]
            util.set_thread_data(machine_id=machine_id)

            # Get detail information about Machine from Database
            qs_res = dbx.queryx_machine_info(machine_id)
            machine_name = qs_res[0]
            qs_res = dbx.queryx_daily_ghost(machine_id)
            (task_id, os_id), server_id = qs_res[:2], qs_res[3]
            start_time = qs_res[7]
            qs_res = dbx.queryx_server_info(server_id)
            (server_domain, server_user, server_pwd) = qs_res[1:4]
            # Generate the task name and command of Windows scheduled task
            task_name = ('"GhostAgent Daily Ghost Task - %s_OSID%s"'
                         % (machine_name, os_id))
            daily_command = os.path.join(gv.g_incoming_local, "DailyCommand.py")
            daily_command = daily_command.replace("\\", "\\\\")
            task_command = ("C:\\Python26\\python.exe \\\"%s\\\" %s"
                            % (daily_command, machine_id))
            # Update the task status of Windows scheduled task
            util.update_daily_ghost_task(
                mode, task_id, task_name, task_command, start_time,
                server_domain, server_user, server_pwd)
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x)==3'))
    def update_ghost_stat(self, cmd_paras, client_addr):
        """
        Update the current OS information of a machine.

        *Command Format:*
            ``UpdateGhostStat MachineID OSID``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
        """
        ret_code = errcode.ER_SUCCESS
        try:
            (machine_id, os_id) = cmd_paras[1:]

            util.set_thread_data(machine_id=machine_id, os_id=os_id)

            # Update Ghost Status
            dbx.updatex_table('Machine_Info', 'CurrentOSID', os_id,
                              'MachineID=%s' % (machine_id))
            # Update IP
            dbx.updatex_table('Machine_Info', 'MachineIP', client_addr[0],
                              'MachineID=%s' % (machine_id), quote=True)
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x)==3'))
    def update_seq_stat(self, cmd_paras, client_addr):
        """
        Update the current software information of a machine.

        *Command Format:*
            ``UpdateSeqStat MachineID OSID``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
        """
        ret_code = errcode.ER_SUCCESS
        try:
            (machine_id, seq_id) = cmd_paras[1:]
            seq_id = seq_id if int(seq_id) != -1 else 'NULL'
            util.set_thread_data(machine_id=machine_id, seq_id=seq_id)

            dbx.updatex_table('Machine_Info', 'CurrentSeqID', seq_id,
                              'MachineID=%s' % (machine_id))
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x)>=2'))
    def exe_local_cmd(self, cmd_paras, client_addr):
        """
        Execute a local command on current machine.

        *Command Format:*
            ``LocalCMD Para1 Para2 ... Para3``

        :param ParaN:
            The parameter of local command.
        """
        ret_code = errcode.ER_SUCCESS
        try:
            local_cmd = " ".join(cmd_paras[1:])

            LOGGER.info("Execute a Local Command: %s" % local_cmd)
            misc.execute(local_cmd)
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x)==3'))
    def grab_new_image(self, cmd_paras, client_addr):
        """
        Grab a new image with specific OS for target machine.

        *Command Format:*
            ``GrabNewImage MachineID OSID``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
        """
        ret_code = errcode.ER_SUCCESS
        try:
            (machine_id, os_id) = cmd_paras[1:]
            util.set_thread_data(machine_id=machine_id, os_id=os_id)

            # Get the ServerID of current Server
            (server_id, ) = dbx.queryx_server_id(socket.gethostname())

            qs_res = dbx.queryx_image_info(
                machine_id, os_id,
                condition_added='M.ServerID=%s' % (server_id))
            is_vm_image = qs_res[0]

            gvt, hdl = util.import_target_modules(os_id, is_vm_image)

            ret_code = hdl.grab_new_image(machine_id, os_id, server_id)
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    def re_grab_image(self, cmd_paras, client_addr):
        """
        Ghost the target machine to specific OS, execute a specific seq on
        the target machine, and grab the image of target machine and
        replace the old image.

        *Command Format:*
            ``ReGrabImage MachineID OSID [SequenceID] [Email]``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
        :param SequenceID:
            The `SeqID` column in `GhostSequences` table.
        :param Email:
            The email adderss for receiving the notification email of Ghost
            status.

        .. note::
            In order to grab the image of target machine and replace the old
            image, we create a new step in the INI script file. In this step,
            we will send a GrabNewImage command to GhostServer.
        """
        # Ghost the target machine, execute the seq,
        # and add grab image step into the script
        ret_code = self.ghost_machine(cmd_paras, client_addr, True)
        return ret_code

    def auto_upgrade(self, cmd_paras, client_addr):
        """
        Upgrade the GhostAgent and its related scripts to specific version.

        *Command Format:*
            ``AutoUpgrade``

        .. note::
            If the version on the export server is older than current release,
            skip this command.
        """
        if gv.g_platform != "windows":
            LOGGER.info("The Auto update command only support Windows now.")
            return errcode.ER_GA_PF_UNSUPPORT

        if not os.path.exists(gv.g_export_server):
            LOGGER.error("The export server <%s> is not exist."
                         % gv.g_export_server)
            return errcode.ER_FILE_NONEXIST

        # Get the Target version
        try:
            version_txt_server = gv.g_export_server + "\\" + gv.g_version_txt
            with open(version_txt_server, 'r') as fp:
                file_content = fp.readlines()
        except Exception, error:
            LOGGER.error("Failed to open the export version file<%s> on %s: %s"
                         % (version_txt_server, gv.g_export_server, error))
            raise Exception(errcode.ER_FILE_READ_ERROR)

        if len(file_content) < 1:
            LOGGER.error("Invalid version infomation in the export version "
                         "file<%s>." % (version_txt_server))
            raise Exception(errcode.ER_FILE_DATA_WRONG)
        new_version = file_content[0].strip()

        # Get the current version
        version_txt_local = os.path.join(gv.g_ga_root, gv.g_version_txt)
        try:
            with open(version_txt_local, 'r') as fp:
                file_content = fp.readlines()
        except Exception, error:
            LOGGER.error("Failed to open the local version file<%s>: %s"
                         % (version_txt_local, error))
            raise Exception(errcode.ER_FILE_READ_ERROR)

        if len(file_content) < 1:
            LOGGER.error("Invalid version infomation in the local version file"
                         "<%s>." % version_txt_local)
            raise Exception(errcode.ER_FILE_DATA_WRONG)
        cur_version = file_content[0].strip()

        # Compare the target version and current version
        if version.cmp_version(new_version, cur_version) <= 0:
            LOGGER.info("The current version<%s> is newer than the target "
                        "version<%s>." % (cur_version, new_version))
            return errcode.ER_SUCCESS

        # Restart the current script
        gv.g_is_upgrade = True
        self.server.shutdown()
        return errcode.ER_SUCCESS

    @valid_param(cmd_paras=(list, 'len(x)<=2'))
    def deploy_vm_image(self, cmd_paras, client_addr):
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
        res_str = ''
        try:
            pair_list = []
            if len(cmd_paras) == 2:
                pair_list = [tuple(x.split(':')) for x in cmd_paras[1].split(";")]

            res_str = hdl_vm.deploy_vm_image(pair_list)
        except Exception, error:
            util.process_error(error)
        return res_str

    @valid_param(cmd_paras=(list, 'len(x) in [4,5]'))
    def archive_vm_image(self, cmd_paras, client_addr):
        """
        Archive the specific VMware image to specific destiantion.

        *Command Format:*
            ``ArchiveVMImage MachineID OSID Destination [Config]``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
        :param Destination:
            The archive destination.
        :param Config:
            The Config parameters to VMX.
        """
        ret_code = errcode.ER_SUCCESS
        try:
            machine_id = cmd_paras[1]
            os_id = cmd_paras[2]
            util.set_thread_data(machine_id=machine_id, os_id=os_id)
            archive_dst = cmd_paras[3]
            # Skip the starting ' or " in the archive destination
            while archive_dst.startswith('"') or archive_dst.startswith("'"):
                archive_dst = archive_dst[1:-1]
            config = None
            if len(cmd_paras) == 5:
                conf_pat = re.compile(r'([\w\d:\.]+),(.+?);')
                confs = conf_pat.findall(cmd_paras[4])
                config = dict(confs)

            gvt, hdl = util.import_target_modules(os_id, True)
            ret_code = hdl.archive_vm_image(
                machine_id, os_id, archive_dst, config)
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x) == 5'))
    def archive_vm_image_report(self, cmd_paras, client_addr, cmd_ret_code):
        """
        Sending archive vm image report to user.

        :param cmd_ret_code:
            The return code for ArchiveVMImage command.

        *Command Format:*
            ``ArchiveVMImage MachineID OSID Destination Email``

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
        ret_code = errcode.ER_SUCCESS
        try:
            machine_id = cmd_paras[1]
            os_id = cmd_paras[2]
            archive_dst = cmd_paras[3].strip('"')
            email_to = [cmd_paras[4]]

            gvt, hdl = util.import_target_modules(os_id, True)
            ret_code = hdl.archive_vm_image_report(
                machine_id, os_id, archive_dst, email_to, cmd_ret_code)
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    def start_all_machines(self, cmd_paras, client_addr):
        """
        Start all virtual machines deployed on the server.

        *Command Format:*
            ``StartAllMachine``

        .. note::
            Return a string consist of machine id that can't be started.
        """
        res_str = ''
        try:
            res_str = hdl_vm.start_all_machines()
        except Exception, error:
            util.process_error(error)
        return res_str

    @valid_param(cmd_paras=(list, 'len(x)==2'))
    def delete_expired_image(self, cmd_paras, client_addr):
        """
        Delete expired VM image on local server.

        *Command Format:*
            ``DeleteExpiredImage max_age``
            'max_age' is in days
        """
        ret_code = errcode.ER_SUCCESS
        try:
            ret_code = hdl_vm.delete_expired_image(int(cmd_paras[1]))
        except Exception, error:
            ret_code = util.process_error(error)
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x) == 2'))
    def set_log_level(self, cmd_paras, client_addr):
        """
        Setting the log level at run time.

        *Command Format:*
            ``SetLogLevel Level``

        :param Level:
            The level of logger handlers.
        `Level` is one of the following values:
            * **CRITICAL**
            * **ERROR**
            * **WARNING**
            * **INFO**
            * **DEBUG**
        """
        ret_code = errcode.ER_SUCCESS
        try:
            level = cmd_paras[1].upper()

            handlers = [x for x in LOGGER.handlers]
            for handler in handlers:
                handler.setLevel(getattr(logging, level))
        except KeyError, error:
            LOGGER.error("Failed to set the log level <%s>: %s"
                         % (level, error))
            ret_code = errcode.ER_GA_HANDLE_EXCEPTION
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x) >= 2'))
    def release_machine(self, cmd_paras, client_addr):
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
        ret_code = errcode.ER_SUCCESS
        try:
            service_id = cmd_paras[1]
            machine_id = cmd_paras[2]

            util.set_thread_data(machine_id=machine_id)

            LOGGER.info("Service with ID <%s> is trying to release machine %s"
                        % (service_id, machine_id))
            ret_code = hdl_vm.release_machine(machine_id, service_id)
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x) in [2, 3]'))
    def start_vm(self, cmd_paras):
        """
        Start a virtual machine.

        *Command Format:*
            ``StartVM MachineID [OSID]``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
            Default is `CurrentOSID` column in `Machine_Info` table.
        """
        ret_code = errcode.ER_SUCCESS
        try:
            machine_id = cmd_paras[1]
            if len(cmd_paras) == 3:
                os_id = cmd_paras[2]
            else:
                (os_id,) = dbx.queryx_machine_current_os_id(machine_id)

            util.set_thread_data(machine_id=machine_id, os_id=os_id)

            LOGGER.info("Start virtual machine %s os %s" % (machine_id, os_id))
            ret_code = hdl_vm.start_vm(machine_id, os_id)
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x) in [2, 3]'))
    def shutdown_vm(self, cmd_paras):
        """
        Shutdown a virtual machine.

        *Command Format:*
            ``ShutdownVM MachineID [OSID]``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
            Default is `CurrentOSID` column in `Machine_Info` table.
        """
        ret_code = errcode.ER_SUCCESS
        try:
            machine_id = cmd_paras[1]
            if len(cmd_paras) == 3:
                os_id = cmd_paras[2]
            else:
                (os_id,) = dbx.queryx_machine_current_os_id(machine_id)

            util.set_thread_data(machine_id=machine_id, os_id=os_id)

            LOGGER.info("Shutdown virtual machine %s os %s" % (machine_id, os_id))
            ret_code = hdl_vm.shutdown_vm(machine_id, os_id)
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x) in [2, 3]'))
    def restart_vm(self, cmd_paras):
        """
        Restart a virtual machine.

        *Command Format:*
            ``RestartVM MachineID [OSID]``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
            Default is `CurrentOSID` column in `Machine_Info` table.
        """
        ret_code = errcode.ER_SUCCESS
        try:
            machine_id = cmd_paras[1]
            if len(cmd_paras) == 3:
                os_id = cmd_paras[2]
            else:
                (os_id,) = dbx.queryx_machine_current_os_id(machine_id)

            util.set_thread_data(machine_id=machine_id, os_id=os_id)

            LOGGER.info("Restart virtual machine %s os %s" % (machine_id, os_id))
            ret_code = hdl_vm.restart_vm(machine_id, os_id)
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x) in [2, 3]'))
    def is_vm_running(self, cmd_paras):
        """
        Judge whether virtual machine is running.

        *Command Format:*
            ``IsVMRunning MachineID [OSID]``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
            Default is `CurrentOSID` column in `Machine_Info` table.
        """
        is_running = False
        try:
            machine_id = cmd_paras[1]
            if len(cmd_paras) == 3:
                os_id = cmd_paras[2]
            else:
                (os_id,) = dbx.queryx_machine_current_os_id(machine_id)

            util.set_thread_data(machine_id=machine_id, os_id=os_id)

            LOGGER.info("Query running status of machine %s os %s" % (machine_id, os_id))
            is_running = hdl_vm.is_vm_running(machine_id, os_id)
        except Exception, error:
            util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return is_running

    @valid_param(cmd_paras=(list, 'len(x) in [2, 3]'))
    def list_snapshots(self, cmd_paras):
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
        ret_str = ''
        try:
            machine_id = cmd_paras[1]
            if len(cmd_paras) == 3:
                os_id = cmd_paras[2]
            else:
                (os_id,) = dbx.queryx_machine_current_os_id(machine_id)

            util.set_thread_data(machine_id=machine_id, os_id=os_id)

            LOGGER.info("List snapshots of machine %s os %s" % (machine_id, os_id))
            ret_str = '\n'.join(hdl_vm.list_snapshots(machine_id, os_id))
        except Exception, error:
            util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_str

    def process_snapshot(self, cmd_paras):
        """
        Take/Delete/Revert Snapshot of virtual machine

        *Command Format:*
            ``TakeSnapshot SnapshotName MachineID [OSID] [Shutdown]``
            ``DeleteSnapshot SnapshotName MachineID [OSID]``
            ``RevertSnapshot SnapshotName MachineID [OSID]``

        :param SnapshotName
            The Name of the Snapshot
        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
            Default is `CurrentOSID` column in `Machine_Info` table.
        :param Shutdown:
            Whether shutdown virtual machine before taking snapshot.
            The value could be "yes/no/true/false", and case insensitive.
            Default is "no".
        """
        ret_code = errcode.ER_SUCCESS
        try:
            operation = cmd_paras[0].upper()
            if operation in map(str.upper, ['TakeSnapshot', 'DeleteSnapshot', 'RevertSnapshot']):
                snapshot_name = cmd_paras[1]
                machine_id = cmd_paras[2]
                if len(cmd_paras) >= 4:
                    os_id = cmd_paras[3]
                else:
                    (os_id,) = dbx.queryx_machine_current_os_id(machine_id)
                if operation == 'TakeSnapshot'.upper():
                    if len(cmd_paras) == 4 and not cmd_paras[3].isdigit():
                        # TakeSnapshot SnapshotName MachineID Shutdown
                        (os_id,) = dbx.queryx_machine_current_os_id(machine_id)
                        shutdown_str = cmd_paras[3].upper()
                    elif len(cmd_paras) == 5:
                        # TakeSnapshot SnapshotName MachineID OSID Shutdown
                        shutdown_str = cmd_paras[4].upper()
                    else:
                        shutdown_str = 'NO'
                    shutdown = shutdown_str in ('YES', 'TRUE')
            else:
                raise Exception('Unknown command "%s"' % (cmd_paras[0]))

            util.set_thread_data(machine_id=machine_id, os_id=os_id)

            LOGGER.info("%s<%s> of machine %s os %s"
                        % (cmd_paras[0], snapshot_name, machine_id, os_id))
            if operation == 'TakeSnapshot'.upper():
                ret_code = hdl_vm.take_snapshot(snapshot_name, machine_id, os_id, shutdown)
            elif operation == 'DeleteSnapshot'.upper():
                ret_code = hdl_vm.delete_snapshot(snapshot_name, machine_id, os_id)
            else:
                # RevertSnapshot
                ret_code = hdl_vm.revert_snapshot(snapshot_name, machine_id, os_id)
        except Exception, error:
            ret_code = util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return ret_code

    @valid_param(cmd_paras=(list, 'len(x) in [3, 4, 5]'))
    def take_snapshot(self, cmd_paras):
        """
        Take snapshot of virtual machine

        *Command Format:*
            ``TakeSnapshot SnapshotName MachineID [OSID] [Shutdown]``
        """
        return self.process_snapshot(cmd_paras)

    @valid_param(cmd_paras=(list, 'len(x) in [3, 4]'))
    def delete_snapshot(self, cmd_paras):
        """
        Delete snapshot of virtual machine

        *Command Format:*
            ``DeleteSnapshot SnapshotName MachineID [OSID]``
        """
        return self.process_snapshot(cmd_paras)

    @valid_param(cmd_paras=(list, 'len(x) in [3, 4]'))
    def revert_snapshot(self, cmd_paras):
        """
        Revert to snapshot of virtual machine

        *Command Format:*
            ``RevertSnapshot SnapshotName MachineID [OSID]``
        """
        return self.process_snapshot(cmd_paras)

    @valid_param(cmd_paras=(list, 'len(x) in [2, 3]'))
    def export_vm(self, cmd_paras, client_addr):
        """
        Export image to g_export_vmroot. Cleanup will be performed
        if folder size exceeds g_export_images_size_limit.

        *Command Format:*
            ``ExportVM MachineID [OSID]``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
            Default is `CurrentOSID` column in `Machine_Info` table.
        """
        ret_str = ''
        export_path = ''
        try:
            machine_id = cmd_paras[1]
            if len(cmd_paras) == 3:
                os_id = cmd_paras[2]
            else:
                (os_id,) = dbx.queryx_machine_current_os_id(machine_id)
            util.set_thread_data(machine_id=machine_id, os_id=os_id)

            LOGGER.info("Export Image to %s" % export_path)
            gvt, hdl = util.import_target_modules(os_id, True)
            export_path = hdl.export_vm(machine_id, os_id)
        except Exception, error:
            util.process_error(error, errcode.ER_GA_HANDLE_EXCEPTION)
        return export_path

    def handle(self):
        """
        Handle of ThreadingTCPServer, to process all the commands.
        """
        cmd = ""
        cmd_paras = []
        reply_flag = False
        ret_code = errcode.ER_FAILED
        try:
            LOGGER.info("waiting for new request ...")
            data_recv = self.request.recv(512)
            if not data_recv:
                return
            cmd_paras = shlex.split(data_recv)
            if not cmd_paras:
                LOGGER.warn("nothing received. handle() exit.")
                return

            client_addr = self.request.getpeername()
            LOGGER.info('RECEIVE COMMAND "%s" from %s'
                        % (data_recv, client_addr))
            cmd = cmd_paras[0].upper()
            if not cmp(cmd, "GhostClient".upper()):
                # Ghost
                ret_code = self.ghost_machine(cmd_paras, client_addr)
                try:
                    (req_ip, req_port) = self.request.getpeername()
                    client_socket = socket.socket(socket.AF_INET,
                                                  socket.SOCK_STREAM)
                    client_socket.connect((req_ip, req_port + 1))
                    client_socket.send(str(ret_code))
                except Exception, error:
                    if '[Errno 10060]' in str(error) or '[Errno 10061]' in str(error):
                        # [Errno 10061]:
                        #   No connection could be made
                        #   because the target machine actively refused it
                        # [Errno 10060]:
                        #   A connection attempt failed because the connected
                        #   party did not properly respond after a period of time,
                        #   or established connection failed because connected
                        #   host has failed to respond
                        #
                        # Since that client often sends "GhostClient" to server,
                        # and exit directly without waiting the result of GhostClient,
                        # so an error will raise because server couldn't reply the result.
                        pass
                    else:
                        LOGGER.warning("Failed when trying to send return message"
                                       " of %s<%s>: %s" % (cmd, ret_code, error))
                finally:
                    client_socket.close()
                reply_flag = False
            elif not cmp(cmd, "PauseDaily".upper()):
                # Pause Daily Ghost
                ret_code = self.daily_ghost(cmd_paras, 0, client_addr)
                reply_flag = True
            elif not cmp(cmd, "RestartDaily".upper()):
                # Restart Daily Ghost
                ret_code = self.daily_ghost(cmd_paras, 1, client_addr)
                reply_flag = True
            elif not cmp(cmd, "UpdateGhostStat".upper()):
                # Update Ghost Status
                ret_code = self.update_ghost_stat(cmd_paras, client_addr)
                reply_flag = False
            elif not cmp(cmd, "UpdateSeqStat".upper()):
                # Update Ghost Status
                ret_code = self.update_seq_stat(cmd_paras, client_addr)
                reply_flag = False
            elif not cmp(cmd, "LocalCMD".upper()):
                # Execute a Local Command
                ret_code = self.exe_local_cmd(cmd_paras, client_addr)
                reply_flag = False
            elif not cmp(cmd, "ReGrabImage".upper()):
                # ReGrab a new image with a specific seq
                ret_code = self.re_grab_image(cmd_paras, client_addr)
                reply_flag = False
            elif not cmp(cmd, "GrabNewImage".upper()):
                # Grab a new image for target machine
                ret_code = self.grab_new_image(cmd_paras, client_addr)
                reply_flag = False
            elif not cmp(cmd, "AutoUpgrade".upper()):
                # Grab a new image for target machine
                ret_code = self.auto_upgrade(cmd_paras, client_addr)
                reply_flag = True
            elif not cmp(cmd, "DeployVMImage".upper()):
                # Deploy VMware images for the current server
                res_str = self.deploy_vm_image(cmd_paras, client_addr)
                LOGGER.info("Result of deploy_vm_image(%s): %s"
                            % (str(cmd_paras), res_str))
                try:
                    self.request.send(res_str)
                except Exception, error:
                    LOGGER.warning("Failed when trying to send return message"
                                   " of %s<%s>: %s" % (cmd, res_str, error))
                reply_flag = False
                ret_code = errcode.ER_SUCCESS
            elif not cmp(cmd, "ArchiveVMImage".upper()):
                # Archive the specific VMware image to specific destiantion
                reply_flag = True
                try:
                    ret_code = self.archive_vm_image(cmd_paras, client_addr)
                    if len(cmd_paras) == 5:
                        self.archive_vm_image_report(cmd_paras, client_addr, ret_code)
                except Exception, e:
                    try:
                        self.request.send(e)
                    except Exception, error:
                        LOGGER.warning("Failed when trying to send return "
                                       "message of %s: %s" % (cmd, error))
                    reply_flag = False
            elif not cmp(cmd, "StartAllMachines".upper()):
                # Start all virtual machines when server is reboot
                res_str = self.start_all_machines(cmd_paras, client_addr)
                LOGGER.info("Result of startup_machine(%s): %s"
                            % (str(cmd_paras), res_str))
                try:
                    self.request.send(res_str)
                except Exception, error:
                    LOGGER.warning("Failed when trying to send return message"
                                   " of %s<%s>: %s" % (cmd, res_str, error))
                reply_flag = False
                ret_code = errcode.ER_SUCCESS
            elif not cmp(cmd, "DeleteExpiredImage".upper()):
                # delete expired vm images on local server
                ret_code = self.delete_expired_image(cmd_paras, client_addr)
                reply_flag = False
            elif not cmp(cmd, "SetLogLevel".upper()):
                # Change the logging level run-time
                ret_code = self.set_log_level(cmd_paras, client_addr)
                reply_flag = True
            elif not cmp(cmd, "ReleaseMachine".upper()):
                # Release the machine (file lock)
                ret_code = self.release_machine(cmd_paras, client_addr)
                reply_flag = True
            elif not cmp(cmd, "GetInfo".upper()):
                ret_code, info = misc.get_info(gv.g_ga_root)
                reply_flag = False
                try:
                    self.request.send(info)
                except Exception, error:
                    LOGGER.warning("Failed when trying to send return message"
                                   " of %s<%s>: %s" % (cmd, ret_code, error))
            elif not cmp(cmd, "StartVM".upper()):
                ret_code = self.start_vm(cmd_paras)
                reply_flag = False
            elif not cmp(cmd, "ShutdownVM".upper()):
                ret_code = self.shutdown_vm(cmd_paras)
                reply_flag = False
            elif not cmp(cmd, "RestartVM".upper()):
                ret_code = self.restart_vm(cmd_paras)
                reply_flag = False
            elif not cmp(cmd, "IsVMRunning".upper()):
                is_vm_running = self.is_vm_running(cmd_paras)
                res_str = 'yes' if is_vm_running else 'no'
                reply_flag = False
                try:
                    self.request.send(res_str)
                except Exception, error:
                    LOGGER.warning("Failed when trying to send return message"
                                   " of %s<%s>: %s" % (cmd, res_str, error))
                ret_code = errcode.ER_SUCCESS
            elif not cmp(cmd, "TakeSnapshot".upper()):
                ret_code = self.take_snapshot(cmd_paras)
                reply_flag = False
            elif not cmp(cmd, "DeleteSnapshot".upper()):
                ret_code = self.delete_snapshot(cmd_paras)
                reply_flag = False
            elif not cmp(cmd, "RevertSnapshot".upper()):
                ret_code = self.revert_snapshot(cmd_paras)
                reply_flag = False
            elif not cmp(cmd, "ListSnapshots".upper()):
                res_str = self.list_snapshots(cmd_paras)
                reply_flag = False
                try:
                    self.request.send(res_str)
                except Exception, error:
                    LOGGER.warning("Failed when trying to send return message"
                                   " of %s<%s>: %s" % (cmd, res_str, error))
                ret_code = errcode.ER_SUCCESS
            elif not cmp(cmd, "ExportVM".upper()):
                res_str = self.export_vm(cmd_paras, client_addr)
                reply_flag = False
                try:
                    self.request.send(res_str)
                except Exception, error:
                    LOGGER.warning("Failed when trying to send return message"
                                   " of %s<%s>: %s" % (cmd, res_str, error))
                ret_code = errcode.ER_SUCCESS
            else:
                LOGGER.error('Invalid Command %s from: %s:%s'
                             % (cmd, client_addr[0], str(client_addr[1])))
                LOGGER.error("Commands: %s" % (data_recv))

            if ret_code != errcode.ER_SUCCESS:
                LOGGER.error('Error in handle command: "%s", ret_code: %s'
                             % (cmd_paras, ret_code))
            if reply_flag:
                try:
                    self.request.send(str(ret_code))
                except Exception, error:
                    LOGGER.warning("Failed when trying to send return message"
                                   " of %s<%s>: %s" % (cmd, ret_code, error))
            LOGGER.info('FINISH COMMAND "%s" from %s', data_recv, client_addr)
        except SystemExit:
            LOGGER.warning("thread is killed")
        except Exception, error:
            LOGGER.warning("Failed to receive new info from %s: %s"
                           % (client_addr, error))
            LOGGER.error(traceback.format_exc())
        finally:
            if self.request:
                self.request.close()
        LOGGER.info("handle() exit")
        return
