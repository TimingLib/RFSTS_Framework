'''
This module contains both :class:`NotifyServer` and :class:`NotifyClient`,
so server machine and client machine use the same module.

Through this module, we can define a server by :class:`NotifyServer`.
Also, a client can be defined by :class:`NotifyClient` or :func:`client_send`,
even execute this file directly.

.. doctest::

    >>> notify_server = NotifyServer('ServiceTest')
    >>> notify_client = NotifyClient()
    >>> notify_client.send('sh-lvtest31', 'GhostClient', 'Passed')
    >>> client_send('-s', 'ServiceTest', '-e', 'GhostClient',
                    '--status', 'Passed', 'sh-lvtest31')

    python notify.py -s ServiceTest -e GhostClient --status Passed sh-lvtest31

There are three important differences between this version and previous version.
    #. Add status support.
        According to CAR 378042 & 325972, AutoTest doesn't know whether ghost
        process is passed completely, since that sometimes ghost process is
        finished, but install process is failed. At that situation, everything
        becomes meaningless to AutoTest. So after ghost process is finished,
        notify client also needs to send status to notify server, making other
        services be able to know whether the ghost process is indeed passed
        or not.
    #. Add event support.
        In the past, :class:`NotifyServer` only supports "GhostClient" sending
        and receiving.
        In order to support VDI, it's required to support more commands, while
        previous architecture doesn't suit this requirement for the extension.
        So we redesign the architecture and communicating protocol for it.
        New communicating protocol:
            #) FinishCmd MachineName/MachineID Event Status
                This is used to tell notify server the status of certain machine
                with certain event. Each machine can have multiple events
                simultaneously, but coundn't have multiple same events at the
                same time.
            #) GetCmdStat MachineName/MachineID Event
                This is used to query status from notify server of certain
                machine with certain event.
        While, new communicating protocol is quite different from previous, but
        we cann't obsolete instantly since that we can't make sure all the
        services update their codes to the latest code at the same time.
        It will cause some services broken during the gap time. So we have to
        take compatibility into full consideration. Finally, after all services
        have already depended on the latest codes, it will be the time to remove
        all compatible codes for better maintainability.
    #. Store all information into database.
        Previous version stores all information into memory, while database
        only acts as a log. Previous design has three obvious defects:
            #) It will drop all notifications once notify server restarted.
            #) It's not easy for people to know the current status
                of a certain machine, except writing a script to query.
            #) Obviously, difference exists among windows/linux/mac when
                send/query status, since for different ghost architecture.
        While, above three defects can be avoided once information stored into
        database, not memory.
'''

import os
import sys
import traceback
import socket
import select
import logging
import time
import shlex
import getopt

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from nicu.misc import xsleep, gethostipbyname
try:
    import nicu.config as config
    from nicu.decor import asynchronized
    from nicu.db import init_db, SQLServerDB
except:
    pass

__all__ = [
    "NotifyServer",
    "NotifyClient",
    "client_send",
]

LOGGER = logging.getLogger(__name__)


class NotifyServer():
    """
    Initial NotifyServer, which will start two threads automatically:
        #) Thead 1: poll thread
            Poll whether notification is timeout or expired.
        #) Thead 2: handle thread
            Provide querying current status of machine with certain event,
            or accept the status from notify client with certain event.

    :param server_name:
        The name of notify server.
    :param server_type:
        The type of notify server.
    :param platform:
        The platform where this notify server deployed in.
    :param poll_interval:
        The interval time to poll.

    Every notification will go through two phases in sequence:
        * Phase 1(**Register Phase**):
            After registered, status will be changed to "**InProcess**".
            And step into **Waiting Phase**.

        * Phase 2(**Waiting Phase**):
            This phase can be one of follows based on situation.
            Before the condition is satisfied, status will keep as
            "**InProcess**".

            1) status changes to "**Passed**",
                when receive passed notification from `notify client`.
            2) status changes to "**Timeout**",
                when do not receive completion notification in a timeout time.
            3) status changes to "**InstallFailed**",
                when receive install failed notification from `notify client`.

    .. note::

        `Server ID` stands for `GhostServer ID` when `server_type` is
        `GhostAgent`. And in other cases, `Server ID` stands for
        `NotifyServer ID`.
    """
    def __init__(self, server_name, server_type=None,
                 platform=None, poll_interval=config.NOTIFY_POLL_INTERVAL,
                 **kwargs):
        self.server_name = server_name
        self.server_ip = gethostipbyname(self.server_name)
        self.server_type = server_type
        self.platform = platform
        self.poll_interval = poll_interval

        self._db_cols = ['MachineID', 'Status', 'ServerID', 'Timeout',
                         'Count', 'CountOK', 'StartTime', 'EndTime', 'Event',
                         'LastError']
        self._statuses = ['None', 'InProcess', 'Passed', 'Timeout',
                          'InstallFailed']
        # This is only for compatibility with previous notify.py
        self._default_event = 'GhostClient'

        (self.server_id, self.server_port) = self._get_ns_info()

        self.poll_wait = self.poll()
        xsleep(1)
        self.handle_wait = self.handle()
        return

    def _compatible_event(self, event, default_event=None):
        """
        This is used only for compatibility.
        Since previous notify server doesn't support event, so all of related
        events are None, which actually mean GhostClient.
        """
        return event or default_event or self._default_event

    def _get_ns_info(self):
        """
        Get the server id and port of notify server.
        """
        server_port = None
        server_id = None
        sql_str = ("select NotifyServerID, NotifyPort, Type from NotifyServer"
                   " where ServerName = '%s'" % (self.server_name))
        if self.server_type:
            sql_str += " and Type = '%s'" % (self.server_type)
        if self.platform:
            sql_str += "and Platform = '%s'" % (self.platform)
        result = SQLServerDB.query(sql_str)
        try:
            server_id = int(result[0][0])
            server_port = int(result[0][1])
            server_type = result[0][2]
            if server_type.lower() == 'GhostAgent'.lower():
                sql_str = ("select ServerID from GhostServer"
                           " where ServerName = '%s'"
                           % (self.server_name))
                result = SQLServerDB.query(sql_str)
                server_id = int(result[0][0])
        except Exception, error:
            raise Exception("Inexist server %s in database: %s" %
                            (self.server_name, error))
        return (server_id, server_port)

    def _query_machine_id(self, name):
        """
        This is used to query machine id.

        :param name:
            Machine name.
        """
        sql_str = ''
        machine_id = None
        try:
            sql_str = ("select MachineID from Machine_Info"
                       " where MachineName='%s'" % (name))
            (machine_id, ) = SQLServerDB.query_one(sql_str)
        except Exception, error:
            LOGGER.error('Failed to query table Machine_Info "%s": %s'
                         % (sql_str, error))
        return machine_id

    def _query_machine_name(self, machine_id):
        """
        This is used to query machine name.

        :param machine_id:
            Machine id.
        """
        sql_str = ''
        name = None
        try:
            sql_str = ("select MachineName from Machine_Info"
                       " where MachineID=%s" % (machine_id))
            (name, ) = SQLServerDB.query_one(sql_str)
            name = name.lower()
        except Exception, error:
            LOGGER.error('Failed to query table Machine_Info "%s": %s'
                         % (sql_str, error))
        return name

    def _operate_db(self, record_phase, name, status, timeout=None,
                    start_time=None, end_time=None, event=None):
        """
        Insert or update database record of the machine.

        :param record_phase:
            The phase of the record(new, update, finish).
        :param name:
            Machine name.
        :param status:
            Current status.
        :param timeout:
            Timeout of the record.
        :param start_time:
            Start time of the record.
        :param end_time:
            End time of the record.
        :param event:
            Corresponding event of the record.
        """
        sql_str = ''
        try:
            if status not in self._statuses:
                raise Exception("Unkown status %s on machine %s" %
                                (status, name))
            event = self._compatible_event(event)
            record = self._query_db(name, event)
            if record:
                machine_id = record['MachineID']
                if record_phase in ['new', 'update']:
                    sql_str = ("update Ghost_Info set Status='%s',"
                               "ServerID=%d,Count=%d,LastError=NULL"
                               % (status, self.server_id,
                                  int(record['Count']) + 1))
                    if timeout is not None:
                        sql_str += ",Timeout=%d" % (timeout)
                    if start_time is not None:
                        sql_str += ",StartTime='%s'" % (start_time)
                elif record_phase in ['finish']:
                    if record['ServerID'] != self.server_id:
                        LOGGER.warning(
                            'This finish command should be processed by'
                            ' the server(%d), rather than this server(%s)'
                            % (record['ServerID'], self.server_id))
                    if record['Status'] != 'InProcess':
                        LOGGER.warning(
                            'The status of notification "%s"[%s] has already'
                            ' been set to %s before. So ignore this %s.'
                            % (name, event, record['Status'], status))
                    else:
                        sql_str = (
                            "update Ghost_Info set Status='%s',CountOK=%d,"
                            "EndTime='%s'" %
                            (status, record['CountOK'] + 1, end_time))
                if sql_str:
                    sql_str += ", Event='%s'" % (event)
                    if event == self._default_event:
                        event_con = "(Event='%s' or Event is NULL)" % (event)
                    else:
                        event_con = "Event='%s'" % (event)
                    sql_str += (" where MachineID=%d and %s"
                                % (machine_id, event_con))
            else:
                if record_phase == 'new':
                    machine_id = self._query_machine_id(name)
                    sql_str = ("insert into Ghost_Info(%s)"
                               " values(%d,'%s',%d,%d,%d,%d,'%s',NULL,'%s',NULL)"
                               % (','.join(self._db_cols), machine_id, status,
                                  self.server_id, timeout,
                                  1, 0, start_time, event))
                elif record_phase in ['update', 'finish']:
                    raise Exception("No data about machine %s in Ghost_Info"
                                    " when update or finish" % (name))
            if sql_str:
                SQLServerDB.execute(sql_str)
        except Exception, error:
            LOGGER.error('Failed to operate table Ghost_Info "%s": %s' %
                         (sql_str, error))
            LOGGER.error(traceback.format_exc())
            sql_str = ''
        return (sql_str != '')

    def _query_db(self, name, event):
        """
        This is used to query record info of certain machine with certain event.

        :param name:
            Machine name.
        :param event:
            Corresponding event.
        """
        sql_str = ''
        result = None
        event = self._compatible_event(event)
        try:
            machine_id = self._query_machine_id(name)

            sql_str = ("select %s from Ghost_Info where MachineID=%d"
                       % (','.join(self._db_cols), machine_id))
            if event == self._default_event:
                sql_str += " and (Event='%s' or Event is NULL)" % (event)
            else:
                sql_str += " and Event='%s'" % (event)
            result = SQLServerDB.query(sql_str)
        except Exception, error:
            result = None
            LOGGER.error('Failed to query table Ghost_Info "%s": %s'
                         % (sql_str, error))
            LOGGER.error(traceback.format_exc())
        return dict(zip(self._db_cols, result[0])) if result else None

    def _query_db_unfinished(self):
        """
        This is used to query all record infos which are registed in this notify
        server and haven't finished.
        """
        sql_str = ''
        result = []
        try:
            sql_str = ('select MI.MachineName,GI.%s from Ghost_Info as GI,'
                       ' Machine_Info as MI'
                       ' where (GI.EndTime is NULL or GI.EndTime < GI.StartTime)'
                       ' and GI.ServerID = %d'
                       ' and GI.MachineID=MI.MachineID'
                       % (',GI.'.join(self._db_cols), self.server_id))
            rows = SQLServerDB.query(sql_str)
            cols = ['MachineName'] + self._db_cols
            result = [dict(zip(cols, row)) for row in rows]
        except Exception, error:
            result = []
            LOGGER.error('Failed to query unfinished notification "%s": %s'
                         % (sql_str, error))
            LOGGER.error(traceback.format_exc())
        return result

    def _get_machine_name(self, machine_name_or_id):
        name = ''
        if isinstance(machine_name_or_id, int):
            name = self._query_machine_name(machine_name_or_id)
        elif isinstance(machine_name_or_id, str):
            if machine_name_or_id.isdigit():
                name = self._query_machine_name(int(machine_name_or_id))
            else:
                name = machine_name_or_id.lower()
        else:
            raise Exception('Unknown machine name or id "%s"'
                            % (str(machine_name_or_id)))
        return name

    def register(self, machine_name_or_id=None, is_block=False,
                 timeout=config.NOTIFY_WAIT_TIMEOUT,
                 event=None):
        """
        Register this machine.
        If block mode set, wait unitl reply received or timeout.

        :param machine_name_or_id:
            Machine name or machine id.
            If machine_name_or_id is an integer, it stands for machine name.
            Else if machine_name_or_id is a string, it stands for machine name.
            Otherwise, it will raise an exception.
        :param is_block:
            Block mode or non-block mode.
        :param timeout:
            Timeout of the machine.
        :param event:
            Corresponding event.
        :returns:
            #) non-block mode: True stands for register successfully,
               else False
            #) block mode: Return status
        """
        event = self._compatible_event(event)
        try:
            name = self._get_machine_name(machine_name_or_id)
            start_time = time.strftime('%Y-%m-%d %H:%M:%S',
                                       time.localtime(time.time()))
            record = self._query_db(name, event)
            if record:
                res = self._operate_db('update', name, 'InProcess',
                                       timeout=timeout,
                                       start_time=start_time,
                                       event=event)
                if res:
                    LOGGER.info('Update notification "%s",'
                                ' Original:[Start:%s, TimeOut:%ds, Event:%s],'
                                ' Updated:[Start:%s, TimeOut:%ds, Event:%s]'
                                % (name, record['StartTime'],
                                   record['Timeout'], record['Event'],
                                   start_time, timeout, event))
            else:
                res = self._operate_db('new', name, 'InProcess',
                                       timeout=timeout,
                                       start_time=start_time,
                                       event=event)
                if res:
                    LOGGER.info('Register notification "%s", '
                                'New:[Start:%s, TimeOut:%ds, Event:%s]'
                                % (name, start_time, timeout, event))
        except Exception, error:
            LOGGER.error("Failed to register new notification \"%s\"[%s]: %s"
                         % (machine_name_or_id, event, error))
            LOGGER.error(traceback.format_exc())
            return False if not is_block else 'None'
        if not is_block:
            return True
        # block until finished or time out
        record = self._query_db(name, event)
        while record and record['Status'] == 'InProcess':
            xsleep(1)
            record = self._query_db(name, event)
        return record['Status'] if record else 'None'

    def accept(self, machine_name_or_id, event=None, status='Passed'):
        """
        Deal received message.

        :param machine_name_or_id:
            Machine name or machine id.
        :param event:
            Corresponding event.
        :param status:
            The status of this event.
        """
        event = self._compatible_event(event)
        end_time = time.strftime('%Y-%m-%d %H:%M:%S',
                                 time.localtime(time.time()))
        try:
            name = self._get_machine_name(machine_name_or_id)
            res = self._operate_db('finish', name, status,
                                   end_time=end_time, event=event)
            if res:
                LOGGER.info('Finish notification "%s"' % (name))
        except Exception, error:
            LOGGER.error("Failed to process reply message \"%s\"[%s]: %s"
                         % (machine_name_or_id, event, error))
            LOGGER.error(traceback.format_exc())
            return False
        return True

    def query(self, machine_name_or_id, event=None):
        """
        Get current status of the machine with corresponding event.

        :param machine_name_or_id:
            Machine name or machine id.
        :param event:
            Corresponding event.
        """
        event = self._compatible_event(event)
        ret = ''
        try:
            name = self._get_machine_name(machine_name_or_id)
            record = self._query_db(name, event)
            if not record:
                ret = 'None'
            else:
                ret = record['Status']
                if ret not in self._statuses:
                    LOGGER.error('Exception notification "%s"[%s] flag "%s"'
                                 % (name, event, ret))
                    ret = 'None'
        except Exception, error:
            ret = 'None'
            LOGGER.warning('Failed to query notification "%s"[%s]: %s' %
                           (machine_name_or_id, event, error))
            LOGGER.error(traceback.format_exc())
        return ret

    @asynchronized(True)
    def poll(self):
        """
        Poll whether notification is timeout.
        """
        try:
            while True:
                cur_time_sec = time.time()
                cur_time = time.strftime(
                    '%Y-%m-%d %H:%M:%S', time.localtime(cur_time_sec))
                rows = self._query_db_unfinished()
                for row in rows:
                    name = row['MachineName']
                    status = row['Status']
                    event = self._compatible_event(row['Event'])
                    start_time = row['StartTime']
                    timeout = row['Timeout']
                    if status != 'InProcess':
                        LOGGER.warning(
                            'Notification \"%s\"[%s] should be InProcess now'
                            % (name, event))

                    start_time_sec = time.mktime(start_time.timetuple())
                    if timeout >= 0 and cur_time_sec - start_time_sec > timeout:
                        self._operate_db('finish', name, 'Timeout',
                                         end_time=cur_time, event=event)

                xsleep(self.poll_interval)
        except SystemExit:
            LOGGER.warning("NotifyServer Poll Thread is killed")
        LOGGER.info("Notification poll() exit")
        return

    @asynchronized(True)
    def handle(self):
        """
        Provide querying and updating interfaces for the status of certain
        machine with corresponding event.
        """
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.server_ip, self.server_port))
        server_socket.listen(20)
        server_socket.setblocking(0)
        LOGGER.info("Create notification server socket: %s(%s):%s" %
                    (self.server_name, self.server_ip, self.server_port))

        socket_list = [server_socket]
        while True:
            LOGGER.debug('Waiting for new ghost client notification ...')
            infds, outfds, errfds = ([], [], [])
            while not infds:
                infds, outfds, errfds = select.select(socket_list,
                                                      [], [], 0.1)
            for infd in infds:
                if infd == server_socket:
                    accept_socket, client_addr = server_socket.accept()
                    socket_list.append(accept_socket)
                else:
                    try:
                        data = infd.recv(512)
                        cmdList = shlex.split(data)
                        command = cmdList[0].lower()
                        # Keep GhostFinish & GetGhostStat for compatibility
                        if command == 'GhostFinish'.lower():
                            machine_name_or_id = cmdList[1].lower()
                            LOGGER.info(
                                'Receive GhostFinish %s from %s'
                                % (machine_name_or_id, client_addr))
                            self.accept(machine_name_or_id, self._default_event)
                        elif command == 'GetGhostStat'.lower():
                            machine_name_or_id = cmdList[1].lower()
                            LOGGER.debug(
                                'Receive GetGhostStat %s from %s'
                                % (machine_name_or_id, client_addr))
                            stat = self.query(
                                machine_name_or_id, self._default_event)
                            infd.send(stat)
                        # We begin to use FinishCmd to process all
                        # notifications about task implemented.
                        elif command == 'FinishCmd'.lower():
                            machine_name_or_id = cmdList[1].lower()
                            event = cmdList[2]
                            status = cmdList[3]
                            LOGGER.info(
                                'Receive FinishCmd %s[%s,%s] from %s'
                                % (machine_name_or_id, event, status, client_addr))
                            self.accept(machine_name_or_id, event, status)
                        # We begin to use GetCmdStat to process all queries
                        elif command == 'GetCmdStat'.lower():
                            machine_name_or_id = cmdList[1].lower()
                            event = cmdList[2]
                            LOGGER.debug(
                                'Receive GetCmdStat %s[%s] from %s'
                                % (machine_name_or_id, event, client_addr))
                            stat = self.query(machine_name_or_id, event)
                            infd.send(stat)
                        else:
                            LOGGER.warning(
                                "Receive Unknown notification \"%s\" from %s"
                                % (str(cmdList), client_addr))
                    except SystemExit:
                        LOGGER.warning("NotifyServer Handle Thread is killed")
                        return
                    except Exception, e:
                        LOGGER.error("NotifyServer has a exception: %s" % e)
                    finally:
                        if infd:
                            infd.close()
                        if infd in socket_list:
                            socket_list.remove(infd)
        LOGGER.info("Notification handle() exit")
        return

    def stop(self):
        """
        Stop poll thread and handle thread.
        """
        self.poll_wait.stop()
        self.handle_wait.stop()
        return


class NotifyClient():
    """
    :param server_name:
        The name of notify server
    :param server_port:
        The port of notify server.
    :param server_type:
        The type of notify server.
    :param platform:
        The platform where the notify server deployed in.


    :class:`NotifyClient` supports 3 mode:
        #) Unknown server name:
            Server name/port will be determined automatically
            by notification name.
        #) Known server name, but unknown server port:
            Server port will be determined by server name, type
            and platform.
        #) Known server name, and server port.

    .. note::

        * Mode 1 is used only where notify server is in GhostAgent Server.
        * Mode 3 is mainly used for no :mod:`pymssql` installed in client
          machine, such as the machine has been ghosted and wants to send
          notification to notify server.
    """
    def __init__(self, server_name=None, server_port=None,
                 server_type=None, platform=None):
        self.server_name = server_name
        self.server_port = server_port
        self.server_type = server_type
        self.platform = platform
        return

    def _get_ns_info(self, name):
        """
        Get the name & port of notify server related with this machine.

        :param name:
            Machine name.
        """
        if not self.server_name:
            # This mode is only used in GhostAgent.
            result = SQLServerDB.query("select MachineID from Machine_Info"
                                       " where MachineName='%s'" % (name))
            machine_id = int(result[0][0])
            result = SQLServerDB.query("select ServerID from Ghost_Info"
                                       " where MachineID=%d" % (machine_id))
            server_id = int(result[0][0])
            result = SQLServerDB.query(
                "select ServerName from GhostServer"
                " where ServerID=%d" % (server_id))
            server_name = result[0][0]
            result = SQLServerDB.query(
                "select NotifyPort from NotifyServer"
                " where ServerName='%s'" % (server_name))
            server_port = int(result[0][0])
        elif self.server_name and (not self.server_port):
            sql_str = ("select NotifyPort from NotifyServer"
                       " where ServerName = '%s'" % (self.server_name))
            if self.server_type:
                sql_str += " and Type = '%s'" % (self.server_type)
            if self.platform:
                sql_str += "and Platform = '%s'" % (self.platform)
            result = SQLServerDB.query(sql_str)
            (server_name, server_port) = (self.server_name, int(result[0][0]))
        else:
            (server_name, server_port) = (self.server_name, self.server_port)
        return (server_name, server_port)

    def _query_machine_name(self, machine_id):
        """
        This is used to query machine name.

        :param machine_id:
            Machine id.
        """
        sql_str = ''
        name = None
        try:
            sql_str = ("select MachineName from Machine_Info"
                       " where MachineID=%s" % (machine_id))
            (name, ) = SQLServerDB.query_one(sql_str)
            name = name.lower()
        except Exception, error:
            LOGGER.error('Failed to query table Machine_Info "%s": %s'
                         % (sql_str, error))
        return name

    def _get_machine_name(self, machine_name_or_id):
        name = ''
        if isinstance(machine_name_or_id, int):
            name = self._query_machine_name(machine_name_or_id)
        elif isinstance(machine_name_or_id, str):
            if machine_name_or_id.isdigit():
                name = self._query_machine_name(int(machine_name_or_id))
            else:
                name = machine_name_or_id.lower()
        else:
            raise Exception('Unknown machine name or id "%s"'
                            % (str(machine_name_or_id)))
        return name

    def send(self, machine_name_or_id, event=None, status='Passed'):
        """
        Send message to notify server about the status of this event.

        :param machine_name_or_id:
            Machine name or machine id.
        :param event:
            Corresponding event.
        :param status:
            The status of this event.
        """
        client_socket = None
        try:
            if event is None:
                msg = "GhostFinish %s" % (machine_name_or_id)
            else:
                msg = "FinishCmd %s %s %s" % (machine_name_or_id, event, status)

            name = self._get_machine_name(machine_name_or_id)
            (server_name, server_port) = self._get_ns_info(name)
            server_ip = gethostipbyname(server_name)
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((server_ip, server_port))
            client_socket.sendall(msg)
            LOGGER.info('Successfully send notification "%s"' % (msg))
        except Exception, error:
            LOGGER.error('Failed to send notification "%s": %s' % (msg, error))
            LOGGER.error(traceback.format_exc())
        finally:
            if client_socket:
                client_socket.close()
        return

    def query(self, machine_name_or_id, event=None):
        """
        Query current status of this machine with certain event.

        :param machine_name_or_id:
            Machine name or machine id.
        :param event:
            Corresponding event.
        """
        client_socket = None
        try:
            name = self._get_machine_name(machine_name_or_id)
            (server_name, server_port) = self._get_ns_info(name)
            server_ip = gethostipbyname(server_name)

            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((server_ip, server_port))
            if event is None:
                msg = "GetGhostStat %s" % (name)
            else:
                msg = "GetCmdStat %s %s" % (name, event)
            client_socket.sendall(msg)
            LOGGER.info('Successfully send notification "%s"' % (msg))
            client_socket.settimeout(10)
            status = client_socket.recv(512)
            LOGGER.info('Successfully receive status of %s[%s]: "%s"' %
                        (name, event, status))
        except Exception, error:
            status = 'None'
            LOGGER.error('Failed to receive status of %s[%s]: %s' %
                         (name, event, error))
            LOGGER.error(traceback.format_exc())
        finally:
            if client_socket:
                client_socket.close()
        return status

    @classmethod
    def send_notify(cls, machine_name_or_id, server_name=None, server_port=None,
                    server_type=None, platform=None,
                    event=None, status='Passed'):
        """
        Send message to notify server about status of certain machine with
        certain event.

        :param machine_name_or_id:
            Machine name or machine id.
        :param server_name:
            The name of notify server
        :param server_port:
            The port of notify server.
        :param server_type:
            The type of notify server.
        :param platform:
            The platform where the notify server deployed in.
        :param event:
            Corresponding event.
        :param status:
            The status of this event.
        """
        notify_client = NotifyClient(
            server_name, server_port, server_type, platform)
        notify_client.send(machine_name_or_id, event, status)
        return

    @classmethod
    def query_notify(cls, machine_name_or_id, server_name=None, server_port=None,
                     server_type=None, platform=None, event=None):
        """
        Send message to notify server about status of certain machine with
        certain event.

        :param machine_name_or_id:
            Machine name or machine id.
        :param server_name:
            The name of notify server
        :param server_port:
            The port of notify server.
        :param server_type:
            The type of notify server.
        :param platform:
            The platform where the notify server deployed in.
        :param event:
            Corresponding event.
        """
        notify_client = NotifyClient(
            server_name, server_port, server_type, platform)
        status = notify_client.query(machine_name_or_id, event)
        return status


def client_send(argv):
    '''
    Send message to notify server about status of certain machine with certain
    event.

    :param argv:
        As same as the arguments in command line.
    '''
    notify_name = None
    server_name = None
    server_port = None
    server_type = None
    platform = None
    event = None
    status = 'Passed'
    try:
        options, rest = getopt.getopt(
            argv, 's:p:t:o:e:',
            ['server=', 'port=', 'type=', 'platform=', 'event=', 'status='])
        for opt, value in options:
            if opt in ('-s', '--server'):
                server_name = value
            elif opt in ('-p', '--port'):
                server_port = int(value)
            elif opt in ('-t', '--type'):
                server_type = value
            elif opt in ('-o', '--platform'):
                platform = value
            elif opt in ('-e', '--event'):
                event = value
            elif opt in ('--status'):
                status = value
            else:
                raise Exception()
        notify_name = rest[0]
    except Exception, error:
        LOGGER.error("Invalid command format %s : %s" % (str(argv), error))
        LOGGER.error(traceback.format_exc())
        LOGGER.info("Command format: notify.py"
                    " [-s server_name] [--server=server_name]"
                    " [-p server_port] [--port=server_port]"
                    " [-t server_type] [--type=server_type]"
                    " [-o platform] [--platform=platform]"
                    " [-e event] [--event=event]"
                    " [--status=status]"
                    " notify_name")
    NotifyClient.send_notify(
        notify_name, server_name, server_port, server_type, platform,
        event, status)
    return

if __name__ == '__main__':
    LOGGER.info("Client Command: %s" % (str(sys.argv)))

    try:
        init_db(config.DB_DEFAULT_HOST, config.DB_DEFAULT_USER,
                config.DB_DEFAULT_PASSWORD, config.DB_DEFAULT_DATABASE)

        # init_db(config.DB_TEST_HOST, config.DB_TEST_USER,
        #         config.DB_TEST_PASSWORD, config.DB_TEST_DATABASE)
    except:
        pass

    client_send(sys.argv[1:])
    sys.exit(0)
