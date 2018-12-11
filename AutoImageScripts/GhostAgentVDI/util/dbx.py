"""
This file is an extension of db.py, used in GhostAgent.

All functions operate as follows:
    * **successful** - return result.
    * **failed** - raise exception with related error code.

Error code is one of the following values:
    * **errcode.ER_DB_CDE_ERROR** - CommonDatabaseException
    * **errcode.ER_DB_COMMON_ERROR** - Other Exception
"""
import logging

from nicu.db import SQLServerDB, CommonDatabaseException
import nicu.errcode as errcode
import util


__all__ = [
    "queryx_table",
    "updatex_table",
    "insertx_table",
    "deletex_table",

    "queryx_target_os_info",
    "queryx_target_server_info",
    "queryx_sequence_info",
    "queryx_step_info",
    "queryx_is_general",
    "queryx_general_info",
    "queryx_image_info",
    "queryx_machine_name",
    "queryx_machine_info",
    "queryx_machine_current_os_id",
    "queryx_all_images",
    "queryx_daily_ghost",
    "queryx_server_info",
    "queryx_server_id",
    "queryx_image_snapshot",
    "queryx_mac_addr",
    "queryx_machine_config",
    "queryx_available_machines",
    "updatex_mac_addr",
    "insertx_machine_reimage",
]

LOGGER = logging.getLogger(__name__)


def queryx_table(table, columns, condition, only_one=False):
    """
    Query record(s) of table.

    :param table:
        The table to query.
    :param columns:
        The columns to query, it can be a string or a list of strings.
    :param condition:
        The filter to query.
    :param only_one:
        Whether we only need one result.

    .. doctest::

        >>> queryx_table("Machine_Info", "MachineID, GroupID",
        ...              "MachineName='sh-lvtest01'", True)
        [1, 1]
        >>> queryx_table("Machine_Info", ["MachineID", "GroupID"],
        ...              "MachineName='sh-lvtest01'")
        [[1, 1]]

    .. note::
        When set `only_one` as True:
            * If exists multiple results, return the first result.
            * If doesn't exist any result, raise exception.
    """
    ret_code = 0
    try:
        cols = ','.join(columns) if isinstance(columns, list) else columns
        sql_str = "select %s from %s where %s" % (cols, table, condition)
        if only_one:
            result = SQLServerDB.query_one(sql_str)
        else:
            result = SQLServerDB.query(sql_str)
    except CommonDatabaseException, error:
        LOGGER.error(
            'Failed to query SQL statement "%s": %s' % (sql_str, error),
            extra={'error_level': 3})
        ret_code = errcode.ER_DB_CDE_ERROR
    except Exception, error:
        LOGGER.error(
            'Failed to query SQL statement "%s", may be invalid: %s' % (sql_str, error),
            extra={'error_level': 3})
        ret_code = errcode.ER_DB_COMMON_ERROR
    if ret_code:
        raise Exception(ret_code)
    return result


def updatex_table(table, column, new_value, condition, quote=False):
    """
    Update one record of table.

    :param table:
        The table to update.
    :param column:
        The column to update.
    :param new_value:
        The new value of the record.
    :param condition:
        The filter to update.
    :param quote:
        Whether add single quote to the new value. It is used when to update
        value of a string.

    .. doctest::

        >>> updatex_table("Machine_Info", "MachineID", 2,
        ...               "MachineName='sh-lvtest01'")
        0
        >>> updatex_table("Machine_Info", "MachineName",
        ...               "sh-lvtest01_new", "MachineName='sh-lvtest01'", True)
        0
    """
    ret_code = 0
    try:
        if isinstance(new_value, bool):
            new_value = int(new_value)
        else:
            new_value = new_value if not quote else "'%s'" % (new_value)
        sql_str = ("update %s set %s=%s where %s"
                   % (table, column, new_value, condition))
        SQLServerDB.execute(sql_str)
    except CommonDatabaseException, error:
        LOGGER.error(
            'Failed to execute SQL statement "%s": %s' % (sql_str, error),
            extra={'error_level': 3})
        ret_code = errcode.ER_DB_CDE_ERROR
    except Exception, error:
        LOGGER.error(
            'Failed to execute SQL statement "%s": %s' % (sql_str, error),
            extra={'error_level': 3})
        ret_code = errcode.ER_DB_COMMON_ERROR
    if ret_code:
        raise Exception(ret_code)
    return ret_code


def insertx_table(table, columns, values):
    """
    Insert one record of table.

    :param table:
        The table to insert.
    :param columns:
        The columns to insert, it can be a string or a list of strings.
    :param values:
        The values of the columns, it need be a string.

    .. doctest::

        >>> insertx_table("Machine_Info", "MachineID, MachineName",
        ...               "1, 'sh-lvtest01'")
        0
        >>> insertx_table("Machine_Info", ["MachineID", "MachineName"],
        ...               "1, 'sh-lvtest01'")
        0
    """
    ret_code = 0
    try:
        cols = ','.join(columns) if isinstance(columns, list) else columns
        sql_str = ("insert into %s(%s) VALUES (%s)" % (table, cols, values))
        SQLServerDB.execute(sql_str)
    except CommonDatabaseException, error:
        LOGGER.error(
            'Failed to execute SQL statement "%s": %s' % (sql_str, error),
            extra={'error_level': 3})
        ret_code = errcode.ER_DB_CDE_ERROR
    except Exception, error:
        LOGGER.error(
            'Failed to execute SQL statement "%s": %s' % (sql_str, error),
            extra={'error_level': 3})
        ret_code = errcode.ER_DB_COMMON_ERROR
    if ret_code:
        raise Exception(ret_code)
    return ret_code


def deletex_table(table, condition):
    """
    Delete records of table.

    :param table:
        The table to delete.
    :param condition:
        The filter to delete.

    .. doctest::

        >>> deletex_table("Machine_Info", "MachineID=1")
        0
    """
    ret_code = 0
    try:
        sql_str = ("delete from %s where %s" % (table, condition))
        SQLServerDB.execute(sql_str)
    except CommonDatabaseException, error:
        LOGGER.error(
            'Failed to execute SQL statement "%s": %s' % (sql_str, error),
            extra={'error_level': 3})
        ret_code = errcode.ER_DB_CDE_ERROR
    except Exception, error:
        LOGGER.error(
            'Failed to execute SQL statement "%s": %s' % (sql_str, error),
            extra={'error_level': 3})
        ret_code = errcode.ER_DB_COMMON_ERROR
    if ret_code:
        raise Exception(ret_code)
    return ret_code


def queryx_target_os_info(os_id):
    """
    Query `OSPlatform`, `OSBit`, `VMwareImage` of target `OSID`.

    :param os_id:
        The `OSID` column in `OS_Info` table.
    """
    table = "OS_Info"
    columns = "OSPlatform, OSBit, VMwareImage"
    condition = "OSID=%s" % (os_id)
    row = queryx_table(table, columns, condition, only_one=True)
    (target_os_platform, target_os_bit, target_vm_image_dir) = row
    target_os_platform = target_os_platform.lower()
    return (target_os_platform, target_os_bit, target_vm_image_dir)


def queryx_target_server_info(machine_id, os_id):
    """
    Query `ServerName`, `ServerPort`, `IsVM` of target (`MachineID`, `OSID`).

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    :param os_id:
        The `OSID` column in `OS_Info` table.
    """
    table = "Machine_Reimage as R, GhostServer as G"
    columns = "G.ServerName, G.ServerPort, R.IsVM"
    condition = ("R.ServerID=G.ServerID and R.MachineID=%s and R.OSID=%s"
                 % (machine_id, os_id))
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def queryx_sequence_info(seq_id):
    """
    Query `Sequence`, `IsPublic` of `SeqID`.

    :param seq_id:
        The `SeqID` column in `GhostSequences` table.
    """
    table = "GhostSequences"
    columns = "Sequence, IsPublic"
    condition = "SeqID=%s" % (seq_id)
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def queryx_step_info(step_id):
    """
    Query information of `StepID`.

    :param step_id:
        The `StepID` column in `GhostSteps` table.
    """
    table = "GhostSteps"
    columns = ("Type, Command, Flags, BasePath, PathSuffix, "
               "LatestInstaller, SleepUntilReboot, NotifierHost, "
               "NotifierPort, NotifierMsg, AlwaysRun")
    condition = "StepID=%s" % (step_id)
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def queryx_is_general(machine_id, os_id):
    """
    Query whether image of target (`MachineID`, `OSID`) is general image.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    :param os_id:
        The `OSID` column in `OS_Info` table.
    """
    table = "GhostNew_Info"
    columns = "count(*)"
    condition = "MachineID=%s and OSID=%s" % (machine_id, os_id)
    (count, ) = queryx_table(table, columns, condition, only_one=True)
    return int(count) > 0


def queryx_general_info(machine_id, os_id):
    """
    Query `ImageSource` of target (`MachineID`, `OSID`).

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    :param os_id:
        The `OSID` column in `OS_Info` table.
    """
    table = "GhostNew_Info"
    columns = "ImageSource"
    condition = "MachineID=%s and OSID=%s" % (machine_id, os_id)
    rows = queryx_table(table, columns, condition)
    return [(len(rows) > 0), None if not rows else rows[0][0]]


def queryx_image_info(machine_id, os_id, condition_added=''):
    """
    Query image information of target (`MachineID`, `OSID`).

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    :param os_id:
        The `OSID` column in `OS_Info` table.
    :param condition_added:
        Added filter to query.
    """
    table = "Machine_Reimage as M, GhostServer as G"
    columns = ("M.IsVM, M.ImageSource, M.LoginUsr, M.LoginPwd, G.VMRoot")
    condition = ("G.ServerID=M.ServerID and M.MachineID=%s and M.OSID=%s"
                 % (machine_id, os_id))
    if condition_added:
        condition += ' and %s' % (condition_added)
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def queryx_machine_name(machine_id):
    """
    Query `MachineName` of target `MachineID`.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    """
    table = "Machine_Info"
    columns = "MachineName"
    condition = ("MachineID=%s" % (machine_id))
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def queryx_machine_info(machine_id):
    """
    Query `MachineName`, `GroupName` of target `MachineID`.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    """
    table = "Machine_Info, MachineGroup_Info"
    columns = "Machine_Info.MachineName, MachineGroup_Info.GroupName"
    condition = ("MachineID=%s AND Machine_Info.GroupID="
                 "MachineGroup_Info.GroupID" % (machine_id))
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def queryx_machine_current_os_id(machine_id):
    """
    Query `CurrentOSID` of target `MachineID`.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    """
    table = "Machine_Info"
    columns = "CurrentOSID"
    condition = ("MachineID=%s" % (machine_id))
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def queryx_all_images(machine_id, condition_added=''):
    """
    Query all `ImageSource`, `LoginUsr`, `LoginPwd` of target `MachineID`.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    :param condition_added:
        Added filter to query.
    """
    table = "Machine_Reimage"
    columns = "ImageSource, LoginUsr, LoginPwd"
    condition = "MachineID=%s and IsVM=1" % (machine_id)
    if condition_added:
        condition += ' and %s' % (condition_added)
    rows = queryx_table(table, columns, condition)
    return rows


def queryx_daily_ghost(machine_id):
    """
    Query daily ghost information of target `MachineID`.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    """
    table = "DailyGhost, OS_Info"
    columns = ("DailyGhost.TaskID, DailyGhost.OSID, DailyGhost.SeqID, "
               "DailyGhost.ServerID, DailyGhost.SymantecID, "
               "DailyGhost.Paused, DailyGhost.CurrentDaily, "
               "DailyGhost.StartTime, OS_Info.OSPlatform")
    condition = ("DailyGhost.MachineID=%s and DailyGhost.CurrentDaily = 1 "
                 "and OS_Info.OSID = DailyGhost.OSID" % (machine_id))
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def queryx_server_info(server_id):
    """
    Query server information of target `ServerID`.

    :param server_id:
        The `ServerID` column in `GhostServer` table.
    """
    table = "GhostServer"
    columns = ("ServerName, ServerDomain, LoginUsr, LoginPwd, "
               "ServerType, VMRoot")
    condition = "ServerID=%s" % (server_id)
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def queryx_server_id(server_name):
    """
    Query `ServerID` of target `ServerName`.

    :param server_name:
        The `ServerName` column in `GhostServer` table.
    """
    table = "GhostServer"
    columns = "ServerID"
    condition = "ServerName='%s'" % (server_name)
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def insertx_machine_reimage(machine_id, os_id, server_id):
    """
    Insert a new recode about machine image.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    :param os_id:
        The `OSID` column in `OS_Info` table.
    :param server_id:
        The `ServerID` column in `GhostServer` table.
    """
    table = 'Machine_Reimage'
    columns = 'MachineID, OSID, ServerID, IsVM, LoginUsr, LoginPwd'
    values = ("%s, %s, %s, 0, 'administrator', 'w3L(0m3T3st'"
              % (machine_id, os_id, server_id))
    ret_code = insertx_table(table, columns, values)
    return ret_code


def queryx_image_snapshot(machine_id, os_id):
    """
    Query `ImageSnapshot` of target (`MachineID`, `OSID`).

    :param machine_id:
        The `MachineID` column in `Machine_Reimage` table.
    :param os_id:
        The `OSID` column in `Machine_Reimage` table.
    """
    table = 'Machine_Reimage'
    columns = 'ImageSnapshot'
    condition = "MachineID='%s' and OSID='%s'" % (machine_id, os_id)
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def queryx_mac_addr(machine_id):
    """
    Get Ethernet name of vmware image.

    :param machine_id:
        'MachineID' column of table 'Machine_Info'
    """
    table = 'Machine_Info'
    columns = 'MacAddress'
    condition = "MachineID=%s" % machine_id
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def updatex_mac_addr(machine_id, mac_addr):
    """
    Update the MAC address in Machine_Info table.

    :param machine_id:
        'MachineID' column of table 'Machine_Info'
    :param mac_addr:
        'MacAddress' column of table 'Machine_Info'
    """
    table = 'Machine_Info'
    columns = 'MacAddress'
    values = "'%s'" % mac_addr
    condition = "MachineID=%s" % machine_id
    ret_code = updatex_table(table, columns, values, condition)
    return ret_code


def queryx_machine_config(machine_id):
    """
    Get CPU and Memory size from Machine_Info table

    :param machine_id:
        'MachineID' column of table 'Machine_Info'
    """
    table = 'Machine_Info'
    columns = 'CPUCore, MemorySize'
    condition = "MachineID=%s" % machine_id
    row = queryx_table(table, columns, condition, only_one=True)
    return row


def queryx_available_machines(server_id):
    """
    Get machine_id list deploy on current Server
    """
    table = 'Machine_Info as MI, Machine_Reimage as MR'
    columns = 'MR.MachineID, MI.CurrentOSID'
    condition = ("MR.ServerID=%s and MI.MachineID=MR.MachineID and "
                 "MI.CurrentOSID=MR.OSID" % server_id)
    rows = queryx_table(table, columns, condition)
    return rows
