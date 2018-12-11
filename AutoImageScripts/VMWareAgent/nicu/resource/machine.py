import logging
from datetime import datetime
from datetime import timedelta
import nicu.db as db
import nicu.ghost as ghost
import nicu.errcode as errcode

__all__ = [
    'Machine',
    'get_current_max_machine_id',
    'get_machine_id_by_name'
]

LOGGER = logging.getLogger(__name__)

_MACHINE_INFO_COLS = ['MachineID', 'MachineName', 'GroupID', 'MachineModel',
                      'CPUModel', 'CPUCore', 'CPUFrequency', 'MemorySize',
                      'HardDiskSize', 'HardwareIDList', 'StartTime',
                      'ExpireTime', 'ServiceID', 'Owner', 'CurrentOSID',
                      'CurrentSeqID', 'Comment', 'MachineIP']
_GHOST_SERVER_COLS = ['ServerName', 'ServerPort']


def get_current_max_machine_id():
    '''
    Return the current max machine_id in Machine_Info table
    '''
    sql_query = ("select max(MachineID) from Machine_Info")
    result = db.run_query_sql(sql_query)
    try:
        return result[0][0]
    except Exception, e:
        return None


def get_machine_id_by_name(machine_name):
    '''
    Return the machine_id column according to the machine_name
    '''
    sql_query = ("select MachineID from Machine_Info where "
                 "MachineName='%s'" % machine_name)
    result = db.run_query_sql(sql_query)
    try:
        return result[0][0]
    except Exception, e:
        return None


class Machine:
    '''
    This class can be used to manage all the machine resouces.
        1. get_machine_info()
        2. set_machine_info()
        3. checkout_machine()
        4. release_machine()
        5. ghost_machine()
    '''

    def __init__(self, machine_id, **args):
        '''
        args value:
            server_name:
              the server name of GhostAgent Server to connect.
              If empty, it will be set temporarily, according
              to target machine.
            throw_exception:
              if failed or timeout, log it or raise exception
            block_timeout:
              After command executed, return directly or wait reply.
              1) 0 stands for non-block
              2) <0 stands for block until receive reply
              3) >0 stands for the timeout to block
        '''
        self.machine_id = machine_id
        self.server_name = ''
        self.throw_exception = False
        self.block_timeout = 3600
        for key, val in args.items():
            setattr(self, key, val)
        self.ghost_center = ghost.GhostCenter(self.server_name,
                                              self.throw_exception,
                                              self.block_timeout)

    def get_machine_info(self):
        '''
        Get the machine information
        '''
        machine_info = None
        cols = ','.join(_MACHINE_INFO_COLS)
        sql_query = ("select %s from Machine_Info where "
                     "MachineID='%s'" % (cols, self.machine_id))
        try:
            results = db.run_query_sql(sql_query)
            if results and len(results) > 0:
                machine_info = dict(zip(_MACHINE_INFO_COLS, results[0]))
        except Exception, e:
            LOGGER.error('[get_machine_info_by_id] Get Machine '
                         'Info failed: %s' % e)
        return machine_info

    def set_machine_info(self, info={}, **args):
        '''
        This function can update the machine information in database

        parameter:
            info:
                the dict of the machine info to update
                example: {
                    'MachineID': '',
                    'MachineName': '',
                    'GroupID': '',
                    'MachineModel': '',
                    'CPUModel': '',
                    'CPUCore': '',
                    'CPUFrequency': '',
                    'MemorySize': '',
                    'HardDiskSize': '',
                    'HardwareIDList': '',
                    'StartTime': '',
                    'ExpireTime': '',
                    'ServiceID': '',
                    'Owner': '',
                    'CurrentOSID': '',
                    'CurrentSeqID': '',
                    'Comment': '',
                    'MachineIP': ''
                }
            args:
                set the machine info
                If you set the parameter in args like MachineID=0, the
                MachineID in info will be replaced by 0.
        '''
        ret_code = errcode.ER_FAILED
        try:
            sql_update = "update Machine_Info set %s where MachineID='%d'"
            info = dict(info)
            for item in args:
                if item in _MACHINE_INFO_COLS:
                    info[item] = args[item]
            if not info:
                raise Exception('No machine info is set')
            datas = []
            for (key, val) in info.items():
                if val and isinstance(val, datetime):
                    val = val.strftime('%Y-%m-%d %H:%M:%S')
                datas.append("%s='%s'" % (key, val))
            sql_update = sql_update % (','.join(datas), self.machine_id)
            sql_update = sql_update.replace("='None'", '=NULL')
            ret_code = db.run_action_sql(sql_update)
        except Exception, e:
            LOGGER.error('[set_machine_info] Set machine '
                         'information failed: %s' % e)
        return ret_code

    def checkout_machine(self, owner=None, reserve_time=1):
        '''
        Checkout a machine with given id or name.
        '''
        ret_code = errcode.ER_FAILED
        try:
            if owner:
                sql_update = ("update Machine_Info set "
                              "ExpireTime=DATEADD(HH, %s, GETDATE()), "
                              "Owner='%s' where MachineID='%s' and "
                              "ExpireTime < GETDATE();" % (reserve_time,
                                                           owner,
                                                           self.machine_id))
            else:
                sql_update = ("update Machine_Info set "
                              "ExpireTime=DATEADD(HH,%s, GETDATE()) "
                              "where MachineID='%s' and ExpireTime < "
                              "GETDATE();" % (reserve_time, self.machine_id))
            ret_code = db.run_action_sql(sql_update)
            if ret_code:
                raise Exception('Machine has been reserved')
        except Exception, e:
            LOGGER.error('[checkout_machine] Checkout machine failed: %s' % e)
        return ret_code

    def release_machine(self, service_id=None):
        '''
        Release a machine with the given ID
        '''
        ret_code = errcode.ER_FAILED
        try:
            sql_query = ("select MachineModel from Machine_Info where "
                         "MachineID='%s'" % self.machine_id)
            res = db.run_query_sql(sql_query)
            if not res:
                raise Exception("No such machine in Machine_Info table")
            if res[0][0] != 'VMWare Image':
                if self.restart_daily() != errcode.ER_SUCCESS:
                    LOGGER.error("[release_machine] Daily ghost restart "
                                 "failed, but machine will still be released")
            elif service_id:
                ret_code = self.ghost_center.release_machine(
                    service_id, self.machine_id)
            reserve_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sql_update = ("update Machine_Info set ExpireTime='%s' "
                          "where MachineID='%s'" % (reserve_time,
                                                    self.machine_id))
            ret_code = db.run_action_sql(sql_update)
        except Exception, e:
            LOGGER.error('[release_machine] Release machine failed: %s' % e)
        return ret_code

    def ghost_machine(self, os_id=None, seq_id=None, email='', **args):
        '''
        Support commands are:
        |------|-----------------|----------------|---------------------|
        | Num. |     Command     | Classification | (non-)block support |
        |======|=================|================|=====================|
        |    1 | GhostClient     | Ghost Command  | block & non-block   |
        |------|-----------------|----------------|---------------------|
        1) ghost_machine(OSID=6, seqID=12345,
                        email='person@ni.com')
        2) ghost_machine(cmd_line='GhostClient 99 6 12345
                        person@ni.com')
           cmd_line='GhostClient machineID OSID seqID email'
        '''
        ret_code = errcode.ER_FAILED
        try:
            if self.pause_daily() != errcode.ER_SUCCESS:
                raise Exception('Pause daily ghost failed')
            if 'cmd_line' in args:
                cmd = args['cmd_line']
                ret_code = self.ghost_center.ghost_client(cmd_line=cmd)
            else:
                ret_code = self.ghost_center.ghost_client(
                    self.machine_id, os_id, seq_id, email)
        except Exception, e:
            LOGGER.error('[ghost_machine] Machine ghost failed: %s' % e)
        return ret_code

    def get_ghost_server(self, os_id):
        '''
        Get name and port of Ghost Server on specific machine

        Returned value:
            res = ('ServerName', 'ServerPort')
        '''
        ghost_server = None
        try:
            ghost_server = \
                self.ghost_center.get_image_ga_server_addr(self.machine_id,
                                                           os_id)
        except Exception, e:
            LOGGER.error('[get_ghost_server] Get Ghost Server '
                         'info failed: %s' % e)
        return ghost_server

    def get_ghost_stat(self):
        """
        Get current ghost status of the target machine.
        Make sure that server_name isn't empty, because once ghosted,
        GhostAgent related in database may be changed.

        Command Format: GetGhostStat machineName.

        Returned value presents in one of four conditions:
          1) Command executed successfully in NotifyServer
              --> Return "Passed"/"InProcess"
          2) Timeout in GhostCenter or NotifyServer
              --> Return "Timeout"
          3) Failed in GhostCenter or NotifyServer,
             and don't throw exception
              --> Return "None"
          4) Failed in GhostCenter or NotifyServer,
             and throw exception
              --> Raise Exception and no returned value
        """
        res = 'None'
        try:
            result = self._get_name_by_id()
            if not result:
                raise Exception('No such machine')
            res = self.ghost_center.get_ghost_stat(result[0][0])
        except Exception, e:
            LOGGER.error('[get_ghost_stat] Get ghost '
                         'status failed: %s' % e)
        return res

    def wait_ghost_finish(self, break_condition='False', block_timeout=3600):
        """
        Wait ghosting until finished or timeout.

        Returned value presents in one of three conditions:
            #) Ghost machine successfully
                --> Return ER_SUCCESS
            #) Failed or timeout in ghosting machine,
               and don't throw exception
                --> Return ER_FAILED
            #) Machine Info Error
                --> Return ER_EXCEPTION
            #) Failed or timeout in ghosting machine,
               and don't throw exception
                --> Return GhostAgent error code
        """
        res = errcode.ER_EXCEPTION
        try:
            result = self._get_name_by_id()
            if result:
                res = self.ghost_center.wait_ghost_finish(
                    result[0][0], break_condition=break_condition,
                    block_timeout=block_timeout)
        except Exception, e:
            LOGGER.error('[wait_ghost_finish] Wait ghost error: %s' % e)
        return res

    def pause_daily(self):
        """
        Pause a daily ghost task.
        """
        res = errcode.ER_SUCCESS
        try:
            sql_query = ("select Paused from DailyGhost where MachineID='%s' "
                         "and CurrentDaily=1" % self.machine_id)
            result = db.run_query_sql(sql_query)
            if result:
                res = self.ghost_center.pause_daily(self.machine_id,
                                                    block_timeout=60)
        except Exception, e:
            LOGGER.error('[pause_daily] Pause daily ghost failed: %s' % e)
            res = errcode.ER_FAILED
        return res

    def restart_daily(self):
        """
        Start/Restart a daily ghost task.
        """
        res = errcode.ER_SUCCESS
        try:
            sql_query = ("select Paused from DailyGhost where MachineID='%s' "
                         "and CurrentDaily=1" % self.machine_id)
            result = db.run_query_sql(sql_query)
            if result:
                res = self.ghost_center.restart_daily(self.machine_id,
                                                      block_timeout=60)
        except Exception, e:
            LOGGER.error('[restart_daily] Start/Restart '
                         'daily ghost failed: %s' % e)
            res = errcode.ER_FAILED
        return res

    def _get_name_by_id(self):
        result = None
        try:
            sql_query = ("select MachineName from Machine_Info "
                         "where MachineID='%s'" % self.machine_id)
            result = db.run_query_sql(sql_query)
        except Exception, e:
            LOGGER.error('[_get_name_by_id] get machine name failed: %s' % e)
        return result
