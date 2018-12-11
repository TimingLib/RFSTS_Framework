import time
import copy
import socket
import logging

from config import GHOST_CMD_TIMEOUT, GHOST_WAIT_TIMEOUT
import nicu.misc as misc
import nicu.db as db
import nicu.errcode as errcode


__all__ = [
    "GhostCenter",
]

LOGGER = logging.getLogger(__name__)


class GhostCenter:
    """
    :param server_name:
      The server name of `GhostAgent Server` to connect.
      If empty, it will be set temporarily, according to target machine.
    :param throw_exception:
      If failed or timeout, log it or raise exception.
    :param block_timeout:
      After command executed, return directly or wait reply.
          #) **0** stands for non-block
          #) **<0** stands for block until receive reply
          #) **>0** stands for the timeout to block
    :param raw:
      Only apply for ghost commands when require the return value.
      If it's True, ghost commands will return unprocessed value immediately
      after:func:`misc.remote_execute` or :func:`misc.remote_execute_diff_port`.
      Otherwise, ghost commands will return processed value.

    Support commands are:

    |------|-----------------|----------------|---------------------|
    | Num. |     Command     | Classification | (non-)block support |
    |======|=================|================|=====================|
    |    1 | GhostClient     | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |    2 | PauseDaily      | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |    3 | RestartDaily    | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |    4 | UpdateGhostStat | Ghost Command  | non-block           |
    |------|-----------------|----------------|---------------------|
    |    5 | UpdateSeqStat   | Ghost Command  | non-block           |
    |------|-----------------|----------------|---------------------|
    |    6 | LocalCMD        | Ghost Command  | non-block           |
    |------|-----------------|----------------|---------------------|
    |    7 | ReGrabImage     | Ghost Command  | non-block           |
    |------|-----------------|----------------|---------------------|
    |    8 | GrabNewImage    | Ghost Command  | non-block           |
    |------|-----------------|----------------|---------------------|
    |    9 | AutoUpgrade     | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |   10 | DeployVMImage   | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |   11 | ArchiveVMImage  | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |   12 | SetLogLevel     | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |   13 | ReleaseMachine  | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |   14 | GetInfo         | Ghost Command  | block               |
    |------|-----------------|----------------|---------------------|
    |   15 | StartVM         | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |   16 | ShutdownVM      | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |   17 | RestartVM       | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |   18 | IsVMRunning     | Ghost Command  | block               |
    |------|-----------------|----------------|---------------------|
    |   19 | ListSnapshots   | Ghost Command  | block               |
    |------|-----------------|----------------|---------------------|
    |   20 | TakeSnapshot    | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |   21 | DeleteSnapshot  | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |   22 | RevertSnapshot  | Ghost Command  | block & non-block   |
    |------|-----------------|----------------|---------------------|
    |   23 | ExportVM        | Ghost Command  | block               |
    |------|-----------------|----------------|---------------------|
    |   24 | GetGhostStat    | Notify Command | block               |
    |------|-----------------|----------------|---------------------|
    |   25 | WaitGhostFinish | Notify Command | block               |
    |------|-----------------|----------------|---------------------|
    |   26 | GetEventStat    | Notify Command | block               |
    |------|-----------------|----------------|---------------------|
    |   27 | WaitEventFinish | Notify Command | block               |
    |------|-----------------|----------------|---------------------|

    Each `Ghost Command` can be called in two ways.

    .. doctest::

      >>> ghost_client(machineID=99, OSID=6, seqID=12345, email='person@ni.com')
      >>> ghost_client(cmd_line='GhostClient 99 6 12345 person@ni.com')

    If both methods exist in one call, method 1 is prior to method 2.

    .. doctest::

      >>> ghost_client(machineID=99, OSID=6, cmd_line='GhostClient 77 4')
    Then real triggle is `GhostClient 99 6`, and `GhostClient 77 4` is ignored.

    `Ghost Command` supports **block mode** and **non-block mode**, and returned value
    keeps in touch with `GhostAgent Server` reply.

    * **Block mode:**
      Support timeout mechanism.
      Returned value of each command presents in one of four conditions:
        #) Command executed successfully in GhostAgent
            --> Return `ER_SUCCESS`
        #) Command executed failed in GhostAgent, and don't throw exception
            --> Return value(!=ER_SUCCESS) from GhostAgent
        #) Timeout or failed in :class:`GhostCenter`, and don't throw exception
            --> Return `ER_FAILED`
        #) Timeout or failed, and throw exception
            --> Raise Exception and no returned value
    * **Non-block mode:**
      Returned value of each command presents in one of three conditions:
        #) Command sent successfully
            --> Return `ER_SUCCESS`
        #) Command sent failed, and don't throw exception
            --> Return `ER_FAILED`
        #) Command sent failed, and throw exception
            --> Raise Exception and no returned value
    """

    def __init__(self, server_name='', throw_exception=False,
                 block_timeout=0, raw=False):
        """
        Initial :class:`GhostCenter`. All member variables can be reset
        temporarily, when member function called.
        """
        self.server_name = server_name
        self.server_port = None
        self.notify_port = None
        if self.server_name:
            self.server_port = self.get_gs_port(self.server_name)
            self.notify_port = self.get_ns_port(self.server_name)

        self.throw_exception = throw_exception
        self.block_timeout = block_timeout
        self.raw = raw

        self._block_mode = (self.block_timeout != 0)
        # the index of machineID in argument command
        self._index_of_mid = None

    def set(self, attr, value):
        """
        Reset value of member variable, and return the original value.

        .. doctest::

          >>> instance = A()
          >>> instance.m = 100
          >>> instance.set('m', 200)
          100
          >>> instance.m
          200
        """
        res = getattr(self, attr)
        setattr(self, attr, value)
        return res

    def set_attrs(self, arg_dict):
        """
        Reset value of member variables, and return the original values.

        .. doctest::

          >>> instance = A()
          >>> instance.m = 100
          >>> instance.n = 101
          >>> instance.set_attrs({'m': 200, 'n': 201})
          {'m': 100, 'n': 101}
          >>> instance.__dict___
          {'m': 200, 'n': 201}
        """
        arg_dict_org = {}
        for attr, value in arg_dict.items():
            if hasattr(self, attr):
                value_org = self.set(attr, value)
                arg_dict_org[attr] = value_org
        if 'block_timeout' in arg_dict:
            self._block_mode = (self.block_timeout != 0)
        if 'server_name' in arg_dict:
            self.server_port = None
            self.notify_port = None
            if arg_dict['server_name']:
                self.server_port = self.get_gs_port(self.server_name)
                self.notify_port = self.get_ns_port(self.server_name)
        return arg_dict_org

    def restore_attrs(self, arg_dict_org):
        """
        Restore original value of member variables.

        .. doctest::

          >>> instance = A()
          >>> instance.m = 200
          >>> instance.n = 201
          >>> instance.restore_attrs({'m': 100, 'n': 101})
          >>> instance.__dict___
          {'m': 100, 'n': 101}
        """
        for attr, value in arg_dict_org.items():
            self.set(attr, value)
        if 'block_timeout' in arg_dict_org:
            self._block_mode = (self.block_timeout != 0)
        if 'server_name' in arg_dict_org:
            self.server_port = None
            self.notify_port = None
            if arg_dict_org['server_name']:
                self.server_port = self.get_gs_port(self.server_name)
                self.notify_port = self.get_ns_port(self.server_name)
        return

    def _get_throw_ex(self, **args):
        """
        Get current exception thrown tag.
        """
        throw_ex = self.throw_exception
        if 'throw_exception' in args:
            throw_ex = args['throw_exception']
        return throw_ex

    def _base_cmd(self, command, **args):
        """Base function to execute command."""
        arg_dict_org = self.set_attrs(args)

        notify_cmd_flag = ('_notify_flag' in args
                           and args['_notify_flag'] is True)
        (server, port) = self.get_machine_server_addr(
            command, notify_cmd_flag)
        is_recv = self._block_mode
        res_bool = not self._block_mode
        if "res_bool" in args:
            res_bool = args["res_bool"]
        timeout = self.block_timeout
        raw = self.raw
        LOGGER.info("Start Execute command: %s" % (command))
        res = misc.remote_execute(server, port, command,
                                  isrecv=is_recv,
                                  resbool=res_bool,
                                  timeout=timeout)
        self.restore_attrs(arg_dict_org)

        if not notify_cmd_flag:
            if is_recv:
                if raw:  # Return unprocessed value
                    return res
                # Most commands return an error code to client.
                # But command "ArchiveVMImage" & "GetInfo" return a string.
                # Ao, if return value is an interger, judge whether
                # success or fail.
                # At any other circumstance, we don't verify the return value.
                if res is socket.timeout:
                    res = errcode.ER_FAILED
                elif isinstance(res, Exception):
                    res = errcode.ER_FAILED
                elif str(res).isdigit():
                    res = int(res)
            else:
                res = [errcode.ER_FAILED, errcode.ER_SUCCESS][res]
            if isinstance(res, int) and res != errcode.ER_SUCCESS:
                self._deal_exception(
                    'Failed to Execute command, ',
                    'server<%s>, port<%s>, is_recv<%s>, '
                    'command<"%s">, result<"%s">' %
                    (server, port, is_recv, command, errcode.strerror(res)),
                    self._get_throw_ex(**args))
            else:
                LOGGER.info("Successfully Execute command: %s" % (command))
        else:
            if res is socket.timeout:
                res = "Timeout"
            elif isinstance(res, Exception):
                res = "None"
        return res

    def _base_cmd_nonblock(self, command, **args):
        """
        Execute base command and do not wait returned value.
        """
        args['block_timeout'] = 0
        return self._base_cmd(command, **args)

    def _base_cmd_block(self, command, **args):
        """
        Execute base command and wait returned value.
        Default timeout is 3600 seconds.
        """
        #if current value of timeout is 0, set value to 3600.
        timeout = self.block_timeout
        if 'block_timeout' in args:
            timeout = args['block_timeout']
        if timeout == 0:
            args['block_timeout'] = GHOST_CMD_TIMEOUT
        return self._base_cmd(command, **args)

    def _deal_exception(self, tips, error, throw_exception=None):
        """Raise the exception to upper or log it simply."""
        msg = (tips and "%s: " % (tips)) + str(error)
        throw_ex = self.throw_exception
        if throw_exception is not None:
            throw_ex = throw_exception
        if throw_ex:
            raise Exception(msg)
        else:
            LOGGER.error("%s" % (msg))
        return

    def get_machineID_by_name(self, machine_name):
        """Get machine ID via machine name."""
        machineID = None
        result = db.run_query_sql("select MachineID from Machine_Info"
                                  " where MachineName = '%s'" % (machine_name))
        if result:
            machineID = int(result[0][0])
        return machineID

    def get_machineID(self, cmd_line):
        """Get machine ID from cmd_line"""
        machineID = int(cmd_line.split()[self._index_of_mid])
        return machineID

    def get_machine_OSID(self, machineID):
        """Get current OSID of the machine"""
        OSID = None
        result = db.run_query_sql("select CurrentOSID from Machine_Info"
                                  " where MachineID = %d" % (machineID))
        if result:
            OSID = int(result[0][0])
        return OSID

    def get_machine_name_by_id(self, machineID):
        """
        This is used to query machine name.
        """
        name = None
        sql_str = ("select MachineName from Machine_Info"
                   " where MachineID=%s" % (machineID))
        result = db.run_query_sql(sql_str)
        if result:
            name = result[0][0].lower()
        return name

    def get_machine_name(self, machine_name_or_id):
        name = None
        if isinstance(machine_name_or_id, int):
            name = self.get_machine_name_by_id(machine_name_or_id)
        elif isinstance(machine_name_or_id, str):
            if machine_name_or_id.isdigit():
                name = self.get_machine_name_by_id(int(machine_name_or_id))
            else:
                name = machine_name_or_id.lower()
        else:
            name = None
        return name

    def get_image_ga_server_addr(self, machineID, OSID):
        """
        Get the address of GhostAgent Server, related with this image.
        """
        serverID = None
        result = db.run_query_sql("select ServerID from Machine_Reimage"
                                  " where MachineID = %d and OSID = %d"
                                  % (machineID, OSID))
        if result:
            serverID = int(result[0][0])
        server_addr = None
        result = db.run_query_sql("select ServerName, ServerPort from"
                                  " GhostServer where ServerID = %d"
                                  % (serverID))
        if result:
            server_addr = (result[0][0], int(result[0][1]))
        return server_addr

    def get_gs_port(self, server_name):
        """
        Get the port of GhostAgent Server.
        """
        server_port = None
        result = db.run_query_sql("select ServerPort from GhostServer"
                                  " where ServerName = '%s'"
                                  % (server_name))
        if result:
            server_port = int(result[0][0])
        return server_port

    def get_ns_port(self, server_name):
        """
        Get the port of :class:`nicu.notify.NotifyServer`.
        """
        server_port = None
        result = db.run_query_sql(
            "select NotifyPort from NotifyServer where ServerName = '%s'"
            " and Type = 'GhostAgent'" % (server_name))
        if result:
            server_port = int(result[0][0])
        return server_port

    def get_machine_server_addr(self, command, notify_cmd_flag=False):
        """
        Get address of server.

        * If command belongs to `Ghost Command`, returns
          (`GhostServer` Name, `GhostServer` Port).
        * If command belongs to `Notify Command`, returns
          (:class:`nicu.notify.NotifyServer` Name,
          :class:`nicu.notify.NotifyServer` Port).

        .. note::
            `GhostServer` name is same as :class:`nicu.notify.NotifyServer`
            name.
        """
        server = self.server_name
        if not server:
            # If _index_of_mid is None, it means that this function must be
            # called with server name. We can't get the server name
            # automatically, like functions:
            #   auto_upgrade, local_cmd, set_log_level
            # The functions are irrelevant with some special client machine.
            if not self._index_of_mid:
                raise Exception("Can't get server name automatically.")
            machineID = self.get_machineID(command)
            OSID = self.get_machine_OSID(machineID)
            server_addr = self.get_image_ga_server_addr(machineID, OSID)
            server = server_addr[0]
            if notify_cmd_flag:
                port = self.get_ns_port(server)
            else:
                port = server_addr[1]
        elif server:
            server_port = self.server_port or self.get_gs_port(server)
            notify_port = self.notify_port or self.get_ns_port(server)
            port = [server_port, notify_port][notify_cmd_flag]
        return (server, port)

    def is_server_keep_run(self, server_name):
        """
        Used to discern whether server keep running when ghost one machine.
        Because if server is linux/mac physical machine, the server is stopped
        at this condition.
        """
        result = db.run_query_sql(
            "select ServerType from GhostServer where ServerName = '%s'"
            % (server_name))
        server_type = int(result[0][0])
        if server_type != 0:
            return False
        result = db.run_query_sql(
            "select Platform from NotifyServer where ServerName = '%s'"
            % (server_name))
        server_platfrom = result[0][0].lower()
        if server_platfrom in ('linux', 'mac'):
            return False
        return True

    def get_ghost_db_status(self, server_name, machineID):
        """
        Get ghost status from database.
        """
        result = db.run_query_sql(
            "select ServerID from GhostServer where ServerName = '%s'"
            % (server_name))
        serverID = int(result[0][0])
        result = db.run_query_sql(
            "select Status from Ghost_Info where ServerID = %d"
            " and MachineID = %d" % (serverID, machineID))
        status = result[0][0]
        return status

    def ghost_client(self, machineID=None, OSID=None,
                     seqID=-1, email='', **args):
        """
        Ghost the target machine with specific os and sequence.

        *Command Sent Format:*
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
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 1
        try:
            if machineID and OSID:
                if seqID == -1:
                    base_cmd_line = "GhostClient %d %d %s" % (
                        machineID, OSID, email)
                else:
                    base_cmd_line = "GhostClient %d %d %d %s" % (
                        machineID, OSID, seqID, email)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No machine ID/OS or integrated GhostClient command")
            # This command is different from others,
            # because GhostAgent/GhostNotifyEmail reply the result with
            # another connection, which port add 1.
            block_mode = self._block_mode
            if 'block_timeout' in args:
                block_mode = (args['block_timeout'] != 0)
            if block_mode:
                arg_dict_org = self.set_attrs(args)
                raw = self.raw
                (server, port) = self.get_machine_server_addr(base_cmd_line)
                LOGGER.info("Start Execute command: %s" % (base_cmd_line))
                res = misc.remote_execute_diff_port(server,
                                                    port,
                                                    base_cmd_line,
                                                    timeout=self.block_timeout)
                self.restore_attrs(arg_dict_org)
                if raw:  # Return unprocessed value
                    return res
                if res is socket.timeout:
                    res = errcode.ER_FAILED
                elif isinstance(res, Exception):
                    res = errcode.ER_FAILED
                else:
                    res = int(res)
                if res != errcode.ER_SUCCESS:
                    self._deal_exception(
                        'Failed to Execute command, ',
                        'server<%s>, port<%s>, is_recv<True>, '
                        'command<"%s">, result<"%s">' %
                        (server, port, base_cmd_line, errcode.strerror(res)),
                        self._get_throw_ex(**args))
                else:
                    LOGGER.info("Successfully Execute command: %s" %
                                (base_cmd_line))
            else:
                res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Ghost Client", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    # The machineID parameter of this function is still in discussion,
    # so the bug about possibility of undefined "machineID, OSID" will
    # be repaired later.
    def create_vm_image(self, machineID=None, OSID=None, isDaily=False,
                        exportPath='', seqID=-1, email='', **args):
        """
        Ghost the VMImage with specific os and sequence.

        *Command Sent Format:*
            ``CreateImage OSID IsDaily ExportPath [SequenceID] [Email]``

        :param OSID:
            The `OSID` column in `OS_Info` table.
        :param IsDaily:
            Whether request for daily image.
        :param ExportPath:
            The network path to export the vmware image.
        :param SequenceID:
            The `SeqID` column in `GhostSequences` table.
        :param Email:
            The email adderss for receiving the notification email of Ghost
            status.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        try:
            if machineID and OSID:
                base_cmd_line = (
                    "CreateImage %d %s %s %d %s"
                    % (OSID, isDaily, exportPath, seqID, email))
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No machine ID/OS or integrated GhostClient command")

            sql_query = ("select gs.ServerName, vs.ServerPort from "
                         "GhostServer as gs, VMWareImageServer as vs "
                         "where gs.ServerName=vs.ServerName and "
                         "gs.ServerID=(select ServerID from "
                         "Machine_Reimage where MachineID='%s' and "
                         "OSID='%s')" % (machineID, OSID))
            res = db.run_query_sql(sql_query)
            if not res:
                raise Exception("No such vm machine in database")
            args['block_timeout'] = 0
            self.server_name = res[0][0]
            self.server_port = int(res[0][1])
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to create VM image", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def pause_daily(self, machineID=None, **args):
        """
        Pause a daily ghost task.

        *Command Sent Format:*
            ``PauseDaily MachineID``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 1
        try:
            if machineID:
                base_cmd_line = "PauseDaily %d" % (machineID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No machine ID or integrated PauseDaily command")
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Pause Daily", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def restart_daily(self, machineID=None, **args):
        """
        Start/Restart a daily ghost task.

        *Command Sent Format:*
            ``RestartDaily MachineID``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 1
        try:
            if machineID:
                base_cmd_line = "RestartDaily %d" % (machineID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No machine ID or integrated RestartDaily command")
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Restart Daily", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def update_ghost_stat(self, machineID=None, OSID=None, **args):
        """
        Update the current OS information of the target machine.

        *Command Sent Format:*
            ``UpdateGhostStat MachineID OSID``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 1
        try:
            if machineID and OSID:
                base_cmd_line = "UpdateGhostStat %d %d" % (machineID, OSID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No machine ID/OS or integrated UpdateGhostStat command")
            res = self._base_cmd_nonblock(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Update Ghost Stat", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def update_seq_stat(self, machineID=None, seqID=None, **args):
        """
        Update the current software information of the target machine.

        *Command Sent Format:*
            ``UpdateSeqStat MachineID OSID``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 1
        try:
            if machineID and seqID:
                base_cmd_line = "UpdateSeqStat %d %d" % (machineID, seqID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No machine ID/SEQUENCE or "
                    "integrated UpdateSeqStat command")
            res = self._base_cmd_nonblock(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Update Sequence Stat", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def deploy_vm_image(self, machineID_list=None, OSID_list=None,
                        machine_pair_list=None, **args):
        """
        Setup the ghost server environment for virtual machines based ghost.
        These virtual machines must be deployed by the same GhostAgent.

        *Command Sent Format:*
            ``DeployVMImage [MachineID:OSID;MachineID:OSID;...]``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.

        Call Format (four methods):
            #) `deploy_vm_image(machineID_list, OSID_list)`
                | priority: high
                | `machineID_list` can be 2 formats:
                    (*) 99
                    (*) [54, 99]
                | `OSID_list` can be 3 formats:
                    (*) 5
                    (*) [5]
                    (*) [1,2,3,4,3,1]
                | format 1 & 2, stands for all machines using same os
            #) `deploy_vm_image(machine_pair_list)`
                | priority: middle
                | each element in `machine_pair_list` can be 2 formats:
                    (*) `[machineID, OSID]`
                    (*) `"machineID:OSID"`
            #) `deploy_vm_image(cmd_line)`
                | priority: low
            #) `deploy_vm_image()`
                | priority: lowest
                | handle/update all virtual images registered on the server
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = None
        #copy it to another variable, avoiding to modify original variable
        machineID_list_copy = copy.deepcopy(machineID_list)
        OSID_list_copy = copy.deepcopy(OSID_list)
        try:
            if machineID_list_copy and OSID_list_copy:
                if isinstance(machineID_list_copy, int):
                    machineID_list_copy = [machineID_list_copy]
                if isinstance(OSID_list_copy, int):
                    OSID_list_copy = [OSID_list_copy]
                if len(machineID_list_copy) == 1:
                    machineID_list_copy = machineID_list_copy * len(OSID_list_copy)
                if len(OSID_list_copy) == 1:
                    OSID_list_copy = OSID_list_copy * len(machineID_list_copy)
                if len(machineID_list_copy) != len(OSID_list_copy):
                    raise Exception(
                        'Unmatch machine ID list "%s" and OS list "%s"' %
                        (str(machineID_list_copy), str(OSID_list_copy)))
                base_cmd_line = 'DeployVMImage "'
                for index in range(len(machineID_list_copy)):
                    base_cmd_line += '%d:%d;' % (
                        machineID_list_copy[index], OSID_list_copy[index])
                base_cmd_line = base_cmd_line.strip(';') + '"'
            elif machine_pair_list:
                base_cmd_line = 'DeployVMImage "'
                for machine_pair in machine_pair_list:
                    if isinstance(machine_pair, list):
                        base_cmd_line += '%d:%d;' % (
                            machine_pair[0], machine_pair[1])
                    elif type(machine_pair) in [type(''), type(u'')]:
                        base_cmd_line += '%s;' % (machine_pair)
                    else:
                        raise Exception(
                            "Unknown machine_pair_list: %s" %
                            (str(machine_pair_list)))
                base_cmd_line = base_cmd_line.strip(';') + '"'
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            #all arguments are empty
            elif not (machineID_list_copy and OSID_list_copy):
                base_cmd_line = 'DeployVMImage'
            else:  # Only exist either of machineID_list or OSID_list
                raise Exception(
                    "Only exist either of machineID_list or OSID_list")

            server_name = self.server_name
            if 'server_name' in args:
                server_name = args['server_name']
            if not server_name:
                assert(len(base_cmd_line.split()) > 1)
                machineID = int(base_cmd_line.split('"')[1].split(':')[0])
                OSID = self.get_machine_OSID(machineID)
                server_addr = self.get_image_ga_server_addr(machineID, OSID)
                args['server_name'] = server_addr[0]
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Deploy VMImage", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def archive_vm_image(self, machineID=None, OSID=None,
                         dest='', email='', **args):
        """
        Archive the specific image to a file server.

        *Command Sent Format:*
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
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 1
        try:
            if machineID and OSID and dest:
                if dest[0] != '"':
                    dest = '"' + dest.strip() + '"'
                base_cmd_line = "ArchiveVMImage %d %d %s %s" % (
                    machineID, OSID, dest, email)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    'No machine ID/OS/Dest or '
                    'integrated ArchiveVMImage command')
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Archive VMImage", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def auto_upgrade(self, **args):
        """
        Auto upgrade the GhostAgent.

        *Command Sent Format:*
            ``AutoUpgrade``
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = 'AutoUpgrade'
        self._index_of_mid = None
        try:
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to AutoUpgrade", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def local_cmd(self, arguList=None, **args):
        """
        Execute a local command on GhostAgent server.

        *Command Sent Format:*
            ``LocalCMD Para1 Para2 ... Para3``

        :param ParaN:
            The parameter of local command.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = None
        try:
            if arguList:
                if type(arguList) in [type(''), type(u'')]:
                    base_cmd_line = "LocalCMD %s" % (arguList)
                else:
                    base_cmd_line = "LocalCMD " + " ".join(arguList)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No command arguments or integrated LocalCMD command")
            res = self._base_cmd_nonblock(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to LocalCMD", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def re_grab_image(self, machineID=None, OSID=None,
                      seqID=-1, email='', **args):
        """
        Grab the image of target machine with specific OS and sequence.

        *Command Sent Format:*
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
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 1
        try:
            if machineID and OSID:
                if seqID == -1:
                    base_cmd_line = "ReGrabImage %d %d %s" % (
                        machineID, OSID, email)
                else:
                    base_cmd_line = "ReGrabImage %d %d %d %s" % (
                        machineID, OSID, seqID, email)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No machine ID/OS or integrated ReGrabImage command")
            res = self._base_cmd_nonblock(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to ReGrab Image", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def grab_new_image(self, machineID=None, OSID=None, **args):
        """
        Grab a new image with specific OS for target machine.

        *Command Sent Format:*
            ``GrabNewImage MachineID OSID``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 1
        try:
            if machineID and OSID:
                base_cmd_line = "GrabNewImage %d %d" % (machineID, OSID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No machine ID/OS or integrated GrabNewImage command")
            res = self._base_cmd_nonblock(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Grab New Image", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def set_log_level(self, level='', **args):
        """
        Set the log level at run time.

        *Command Sent Format:*
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
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = None
        try:
            if level:
                base_cmd_line = "SetLogLevel %s" % (level.upper())
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception("No level or integrated SetLogLevel command")
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Set Log Level", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def release_machine(self, serviceID=None, machineID=None, **args):
        """
        Release the virtual machine.

        *Command Sent Format:*
            ``ReleaseMachine ServiceID MachineID``

        :param ServiceID:
            The `ServiceID` column in `Services` table.
        :param MachineID:
            The `MachineID` column in `Machine_Info` table.

        .. note::
            This command only applies for vmware machine, to delete file lock
            after failed to ghost.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 2
        try:
            if serviceID and machineID:
                base_cmd_line = "ReleaseMachine %s %d" % (serviceID, machineID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No service/machine or integrated ReleaseMachine command")
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Release Machine", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def process_vm_power(self, cmd_type, machineID, OSID, **args):
        """
        Start/Restart/Shutdown a virtual machine.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 1
        cmd_token = "%sVM" % (cmd_type)
        try:
            if machineID:
                base_cmd_line = "%s %d" % (cmd_token, machineID)
                if OSID is not None:
                    base_cmd_line += " %d" % (OSID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception("No machine or integrated %s command" % (cmd_token))
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to %s Virtual Machine" % (cmd_type), error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def start_vm(self, machineID, OSID=None, **args):
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
        return self.process_vm_power('Start', machineID, OSID, **args)

    def shutdown_vm(self, machineID, OSID=None, **args):
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
        return self.process_vm_power('Shutdown', machineID, OSID, **args)

    def restart_vm(self, machineID, OSID=None, **args):
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
        return self.process_vm_power('Restart', machineID, OSID, **args)

    def is_vm_running(self, machineID, OSID=None, **args):
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
        res = False
        base_cmd_line = ''
        self._index_of_mid = 1
        try:
            if machineID:
                base_cmd_line = "IsVMRunning %d" % (machineID)
                if OSID is not None:
                    base_cmd_line += " %d" % (OSID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No machine or integrated IsVMRunning command")
            max_block_timeout = 60
            args['block_timeout'] = min(
                max_block_timeout, args.get('block_timeout', GHOST_CMD_TIMEOUT))
            status = self._base_cmd_block(base_cmd_line, **args)
            res = (status == 'yes')
        except Exception, error:
            self._deal_exception("Fail to Get Running Status", error,
                                 self._get_throw_ex(**args))
        return res

    def list_snapshots(self, machineID, OSID=None, **args):
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
        res = ''
        base_cmd_line = ''
        self._index_of_mid = 1
        try:
            if machineID:
                base_cmd_line = "ListSnapshots %d" % (machineID)
                if OSID is not None:
                    base_cmd_line += " %d" % (OSID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No snapshot/machine or integrated TakeSnapshot command")
            res = self._base_cmd_block(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Take Snapshot", error,
                                 self._get_throw_ex(**args))
        return res

    def take_snapshot(self, snapshot, machineID, OSID=None, shutdown=None, **args):
        """
        Take snapshot of virtual machine

        *Command Format:*
            ``TakeSnapshot SnapshotName MachineID [OSID] [Shutdown]``

        :param SnapshotName
            The Name of the Snapshot
        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
            Default is `CurrentOSID` column in `Machine_Info` table.
        :param Shutdown:
            Whether shutdown virtual machine before taking snapshot.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 2
        try:
            if snapshot and machineID:
                base_cmd_line = "TakeSnapshot %s %d" % (snapshot, machineID)
                if OSID is not None:
                    base_cmd_line += " %d" % (OSID)
                if shutdown is not None:
                    base_cmd_line += " %s" % ("yes" if shutdown else "no")
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No snapshot/machine or integrated TakeSnapshot command")
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Take Snapshot", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def delete_snapshot(self, snapshot, machineID, OSID=None, **args):
        """
        Delete snapshot of virtual machine

        *Command Format:*
            ``DeleteSnapshot SnapshotName MachineID [OSID]``

        :param SnapshotName
            The Name of the Snapshot
        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
            Default is `CurrentOSID` column in `Machine_Info` table.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 2
        try:
            if snapshot and machineID:
                base_cmd_line = "DeleteSnapshot %s %d" % (snapshot, machineID)
                if OSID is not None:
                    base_cmd_line += " %d" % (OSID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No snapshot/machine or integrated DeleteSnapshot command")
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Delete Snapshot", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def revert_snapshot(self, snapshot, machineID, OSID=None, **args):
        """
        Revert to snapshot of virtual machine

        *Command Format:*
            ``RevertSnapshot SnapshotName MachineID [OSID]``

        :param SnapshotName
            The Name of the Snapshot
        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
            Default is `CurrentOSID` column in `Machine_Info` table.
       """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 2
        try:
            if snapshot and machineID:
                base_cmd_line = "RevertSnapshot %s %d" % (snapshot, machineID)
                if OSID is not None:
                    base_cmd_line += " %d" % (OSID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No snapshot/machine or integrated RevertSnapshot command")
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Revert Snapshot", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def export_vm(self, machineID, OSID=None, **args):
        """
        Export image to g_export_vmroot.

        *Command Format:*
            ``ExportVM MachineID [OSID]``

        :param MachineID:
            The `MachineID` column in `Machine_Info` table.
        :param OSID:
            The `OSID` column in `OS_Info` table.
            Default is `CurrentOSID` column in `Machine_Info` table.
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = 1
        try:
            if machineID:
                base_cmd_line = "ExportVM %d" % (machineID)
                if OSID is not None:
                    base_cmd_line += " %d" % (OSID)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No machine or integrated ExportVM command")
            max_block_timeout = 1800
            args['block_timeout'] = min(
                max_block_timeout, args.get('block_timeout', GHOST_CMD_TIMEOUT))
            res = self._base_cmd_block(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Export VM Image", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def get_info(self, **args):
        """
        Get version information of `GhostAgent Server`.

        *Command Sent Format:*
            ``GetInfo``
        """
        res = errcode.ER_SUCCESS
        base_cmd_line = ''
        self._index_of_mid = None
        try:
            base_cmd_line = "GetInfo"
            # This command only has block mode.
            timeout = self.block_timeout
            if 'block_timeout' in args:
                timeout = args['block_timeout']
            if not timeout:
                args['block_timeout'] = -1
            res = self._base_cmd(base_cmd_line, **args)
        except Exception, error:
            self._deal_exception("Fail to Get Version", error,
                                 self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def get_event_stat(self, machine_name_or_id='', event=None, **args):
        """
        Get current event status of the target machine.

        *Command Sent Format:*
            ``GetCmdStat MachineName Event``
            ``GetCmdStat MachineID Event``

        Returned value presents in one of four conditions:
            #) Command executed successfully in
               :class:`nicu.notify.NotifyServer`
                --> Return **Passed**/**InProcess**/**InstallFailed**
                If this event is `GhostClient` and exception is raised
                during installation on client machine, return **InstallFailed**.
            #) Timeout in :class:`GhostCenter` or
               :class:`nicu.notify.NotifyServer`
                --> Return **Timeout**
            #) Failed in :class:`GhostCenter` or
               :class:`nicu.notify.NotifyServer`, and don't throw exception
                --> Return **None**
            #) Failed in :class:`GhostCenter` or
               :class:`nicu.notify.NotifyServer`, and throw exception
                --> Raise :class:`Exception` and no returned value

        .. note::
            #) Once ghosted, `GhostAgent` related in database may be changed.
            #) When ghost linux/mac physical machine, GhostAgent will shut down,
               due to Server and Client deployed on the same machine.
        """
        res = ''
        base_cmd_line = ''
        self._index_of_mid = None

        server_name = self.server_name
        if 'server_name' in args:
            server_name = args['server_name']
        machineID = None
        try:
            if machine_name_or_id and event:
                base_cmd_line = 'GetCmdStat %s %s' % (machine_name_or_id, event)
            elif "cmd_line" in args:
                base_cmd_line = args["cmd_line"]
            else:
                raise Exception(
                    "No machine or integrated GetCmdStat command")

            machine_name_or_id = base_cmd_line.split()[1]
            machine_name = self.get_machine_name(machine_name_or_id)
            machineID = self.get_machineID_by_name(machine_name)
            # If server name is None, set server name here, to conveniently
            # judge whether server is linux/mac physical machine or not.
            if not server_name:
                OSID = self.get_machine_OSID(machineID)
                server_name = self.get_image_ga_server_addr(machineID, OSID)[0]
                args['server_name'] = server_name

            # If server is deployed in linux/mac physical machine,
            # it will be shut down when ghost a machine.
            # So, we can only get status from Ghost_Info table.
            if not self.is_server_keep_run(server_name):
                res = self.get_ghost_db_status(server_name, machineID)
                return res

            args['_notify_flag'] = True
            # This function should receive replying message instantly.
            # If user has set a large "block_timeout" for this, we should
            # decrease it. Otherwise, once one package is missing during
            # tranmission, it will block several hours, which is unexpected.
            max_block_timeout = 60
            args['block_timeout'] = min(
                max_block_timeout, args.get('block_timeout', GHOST_CMD_TIMEOUT))
            res = self._base_cmd_block(base_cmd_line, **args)
            if res not in ['None', 'Timeout', 'InProcess', 'Passed',
                           'InstallFailed']:
                raise Exception(
                    "Ghost notification \"%s\" nonexistence" % (base_cmd_line))
        except Exception, error:
            self._deal_exception("Fail to Get Ghost Stat", error,
                                 self._get_throw_ex(**args))
            res = 'None'
        return res

    def get_ghost_stat(self, machine_name_or_id='', **args):
        """
        Get current ghost status of the target machine.

        *Command Sent Format:*
            ``GetCmdStat GhostClient MachineName``
            ``GetCmdStat GhostClient MachineID``
        """
        return self.get_event_stat(machine_name_or_id, 'GhostClient', **args)

    def wait_event_finish(self, machine_name_or_id='', event=None,
                          break_condition='False', **args):
        """
        Wait event until finished or timeout.

        :param machine_name_or_id:
            Machine name or machine id.
        :param event:
            Corresponding event.
        :param break_condition:
            If the condition is satisfied, stop waiting and return.
        :param args:
            The dict to set member variables temporarily.
            After exit from the function, all variables will be reset,
            like other functions.

        Returned value presents in one of three conditions:
            #) Ghost machine successfully
                --> Return ER_SUCCESS
            #) Failed or timeout in ghosting machine,
               and don't throw exception
                --> Return ER_FAILED
            #) Failed or timeout in ghosting machine,
               and don't throw exception
                --> Raise Exception and no returned value
        """
        res = errcode.ER_FAILED
        #if current value of timeout is 0, set value to 3600.
        timeout = self.block_timeout
        if 'block_timeout' in args:
            timeout = args['block_timeout']
        if timeout == 0:
            timeout = GHOST_WAIT_TIMEOUT
            args['block_timeout'] = timeout

        # Sometime, a package may be lost during tranmission. And remote_execute
        # will wait until timeout. At that situation, get_ghost_stat will return
        # "Timeout", which is unexpected. But when we query the status again,
        # it reverts to normal.
        # So I add one variable "repeat_count" here, which means the loop will
        # go on, until when status isn't "InProcess" continuously for
        # "repeat_count" times, or the break condition is True.
        # The default value of "repeat_count" is 3.
        # Client can modify this value by passing arguments.
        repeat_count_default = args.get('repeat_count', 3)
        repeat_count = repeat_count_default
        start_time = time.time()
        try:
            stat = 'None'
            while (timeout == -1) or (time.time() - start_time < timeout):
                stat = self.get_event_stat(machine_name_or_id, event, **args)
                if stat in ["None", "Timeout", "Passed", "InstallFailed"]:
                    repeat_count -= 1
                    if repeat_count <= 0:
                        break
                elif stat not in ['InProcess']:
                    raise Exception(
                        'Unknown machine %s ghost status "%s"' %
                        (machine_name_or_id, stat))
                else:
                    repeat_count = repeat_count_default
                if eval(break_condition):
                    LOGGER.info('Meet the breaking condition when waiting'
                                ' machine %s ghost finished.'
                                % (machine_name_or_id))
                    break
                interval = max(1, min(60, timeout - 2))
                misc.xsleep(interval)
            if stat == 'InstallFailed':
                raise Exception(
                    'Failed in machine %s software installation.'
                    % (machine_name_or_id))
            elif stat == 'Timeout':
                raise Exception(
                    'Machine %s ghost process has been time out'
                    % (machine_name_or_id))
            elif stat == 'InProcess':
                raise Exception(
                    'Timeout or meeting the breaking condition when waiting'
                    ' machine %s ghost finished.'
                    % (machine_name_or_id))
            elif stat == 'Passed':
                res = errcode.ER_SUCCESS
                LOGGER.info(
                    'Ghost machine %s Successfully' % (machine_name_or_id))
            else:
                raise Exception(
                    'Exception occurs during machine %s ghost process'
                    % (machine_name_or_id))
        except Exception, error:
            self._deal_exception('', error, self._get_throw_ex(**args))
            res = errcode.ER_FAILED
        return res

    def wait_ghost_finish(self, machine_name_or_id='',
                          break_condition='False', **args):
        """
        Wait ghosting until finished or timeout.
        """
        return self.wait_event_finish(
            machine_name_or_id, 'GhostClient', break_condition, **args)

    @classmethod
    def get_ghost_center(cls, server_name='',
                         throw_exception=False,
                         block_timeout=0):
        """
        Get and initial Ghost Center.

        :param server_name:
            The server name of `GhostAgent Server` to connect.
            If empty, it will be set temporarily, according to target machine.
        :param throw_exception:
            If failed or timeout, log it or raise exception.
        """
        ghost_center = GhostCenter(server_name=server_name,
                                   throw_exception=throw_exception,
                                   block_timeout=block_timeout)
        return ghost_center

    def get_last_error(self, machine_name_or_id):
        """
        Get last error of specific machine.
        """
        if isinstance(machine_name_or_id, int) or machine_name_or_id.isdigit():
            machineID = int(machine_name_or_id)
        else:
            machineID = self.get_machineID_by_name(machine_name_or_id)
        result = db.run_query_sql("select LastError from Ghost_Info"
                                  " where MachineID = %s" % (machineID))
        return result[0][0] if (result and result[0][0]) else ""