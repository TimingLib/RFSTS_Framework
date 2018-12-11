#!/usr/bin/python
"""
Filename: VMWareAgent.py

Commands:
    CreateImage OSID IsDaily ExportPath [SequenceID] [Email] [Config]

Explanation about task status
    Waiting -> This task has been created, but not be processed.
    Ghosting -> This task is in ghosting phase.
    Installing -> This task is in the install phase.
    Archiving -> This task is in archiving phase.
    Done-Failed -> This task has failed.
    Done-Success -> This task has completed successfully.

The original task status "Running" has been splited into three different statuses,
since that "Installing" phase occupies the most time, which could be executed
with other phases parallelly.
So we redesign the process flow, and improve it with following restrictions:
    1. Make sure at most a given amount of tasks is in "Ghosting" or "Archiving" phase.
        (This is limited by the vmware workstation performance, and the number
        is specified in database as VMToolConcurrency.)
    2. Multiple "Installing" tasks could be coexistent with each other,
        and with other "Ghosting"/"Archiving" tasks.
        (However, limited by the server performance, the total number of running
        tasks should also be specified, as TaskConcurrency.)
    3. When dump the image tasks, the status should be reverted to "Waiting".
"""

import os
import sys
import re
import time
import shlex
import socket
import platform
import threading
import shutil
import stat
import traceback
import subprocess
import logging
import logging.handlers
from datetime import datetime, timedelta
from SocketServer import TCPServer
from SocketServer import ThreadingMixIn
from SocketServer import StreamRequestHandler
from logging.handlers import TimedRotatingFileHandler

import nicu.db as db
import nicu.misc as misc
import nicu.mail as mail
import nicu.config as config
import nicu.version as version
import nicu.errcode as errcode
from nicu.ghost import GhostCenter
import nicu.sequence as sequence
import nicu.vm as vm
from nicu.resource.machine import Machine
from nicu.decor import asynchronized, synchronized

# basic information for machine setting
_host_name = ''
_host_address = ''
_vmtool_concurrency = 1
_task_concurrency = 1
_ghost_server_port = ''
_vmware_server_port = ''
_vmware_service_id = None

# Email settings
_MAIL_ADDR_FROM = 'vmwareimage_sast@ni.com'
_SMTP_SERVER = 'mailmass'
_ADMIN_LIST = ['Ning.Deng@ni.com']

# default information for machine configuration
_GROUP_ID = 1
_MACHINE_MODEL = 'VMWare Image'
_CPU_MODEL = 'Intel'
_CPU_CORE = 1
_CPU_FREQUENCY = 2.33
_MEMORY_SIZE = 2
_HARDDISK_SIZE = 80
_CURRENT_OS_ID = 0
_TIMEOUT_EACH_STEP = 1800              # 0.5 hour
_GHOST_TIMEOUT = 3600                  # 1 hour
_ARCHIVE_TIMEOUT = 9000                # 2.5 hour

_MAIL_PATTERN = '(.+@[\w\d]+\.[\w]+)+'

# days to find equivalent tasks
_CHECK_DAYS = -1

_ghost_center = None
_will_shutdown = False

# misc info for upgrading vmware agent
_export_server = r"\\cn-sha-rdfs01\RD\SAST\Installer_Services\Services\VMWareAgent"
_va_root = os.path.dirname(os.path.realpath(__file__))
_check_upgrade_interval = 5
_is_upgrade = False

# _mutex is used to limit the concurrency of Ghosting and Archiving tasks
_mutex = threading.BoundedSemaphore(1)

logger = logging.getLogger(__name__)

# SendEmail nicu from CommonUtil 2.0
g_mail = mail.Mail(_SMTP_SERVER, 25, _MAIL_ADDR_FROM)


def pretty(data):
    """
    This function used to format the content sent to user

    accept data example:
    data = [
    {'OsInfo': 'Window 7'},
    {'SoftwareInfo': ['lvenglish 2012', 'lv', 'rio', 'fpga', 'hello']},
    {'name': 'Yanjiang Qian'},
    {'submitted at ': 'Yanjiang Qian'},
    {'error info': 'some info'}
    ]

    return value:
    formated seperated with \n
    """
    output = []
    for item in data:
        if isinstance(item, dict):
            for key, value in item.iteritems():
                if not value:
                    output.append("%-15s" % (str(key)+':'))
                elif isinstance(value, list) or isinstance(value, set):
                    output.append("%-15s" % (str(key)+':'))
                    for v in value:
                        output.append("%s" % (' '*16+str(v)))
                else:
                    output.append("%-15s %s" % (str(key)+':', str(value)))
        else:
            output.append(str(item))
        output.append('')
    return '\n'.join(output)


def generate_email(cmd, task_id):
    columns = 'OSID, SequenceID, SubmitTime, StartTime, EndTime, Comment'
    rows = get_filter_tasks(columns, 'ID=%d' % (task_id))
    (osid, seq_id, submit_time, start_time, end_time, comment) = rows[0]
    content = ''
    time_format = '%Y-%m-%d %H:%M:%S'
    try:
        # Convert OSID to os_info
        os_info = get_os_info_by_osid(osid)
        # Convert sequenceID to software info
        software_info = get_sw_info_by_seq_id(seq_id)
        content_data = []
        content_data.append({'Your request': cmd})
        content_data.append({'OsInfo': os_info})
        content_data.append({'SoftwareInfo': software_info})
        content_data.append({'Submitted at': submit_time.strftime(time_format)})
        content_data.append({'Started at': start_time.strftime(time_format)})
        content_data.append({'Completed at': end_time.strftime(time_format)})
        content_data.append({'Detail info': comment})
        content = pretty(content_data)
    except Exception, e:
        process_error(e, 'generate email')
        content = "Generate Email Error: %s" % e
    return content


def get_srv_info_by_name(srv_name):
    """
    Get ghost server port from GhostServer,
    vmware server port form VMWareImageServer,
    the concurrency count of running vmware tools,
    the concurrency count of parallel tasks,
    and the id of vmware agent service.

    :param srv_name:
        The 'ServerName' column in 'GhostServer'&'VMWareImageServer' table.
    """
    sql_query = ("select ServerPort, VmtoolConcurrency, TaskConcurrency"
        " from VMWareImageServer where ServerName='%s'" % (srv_name))
    rows = db.run_query_sql(sql_query)
    if not rows:
        logger.info("Server<%s> is not registed in the VMWareImageServer table" % srv_name)
        sys.exit(1)
    vmware_server_port, vmtool_concurrency, task_concurrency = rows[0]
    vmtool_concurrency = vmtool_concurrency or 1
    task_concurrency = task_concurrency or 1

    sql_query = ("select ServerPort from GhostServer where ServerName='%s'" % (srv_name))
    rows = db.run_query_sql(sql_query)
    if not rows:
        logger.info("Server<%s> is not registed in the GhostServer table" % srv_name)
        sys.exit(1)
    ghost_server_port = rows[0][0]

    sql_query = ("select cast(ServiceID as varchar(40)) from Services"
        " where ServiceName='VMWareImage Service'")
    rows = db.run_query_sql(sql_query)
    if not rows:
        logger.info("VMWareImage Service is not registed in the ServiceID table")
        sys.exit(1)
    vmware_service_id = str(rows[0][0])

    return (vmware_server_port, vmtool_concurrency, task_concurrency,
        ghost_server_port, vmware_service_id)


def get_os_info_by_osid(osid):
    """
    Get the os info from database.
    """
    ret_val = ''
    sql_query = ("select distinct OSName + ' ' +OSVersion+' (' + "
                 "convert(varchar,OSBit) +'-bit ' +OSPatch+' '+"
                 "OSLanguage+')' as CombinedOS from OS_Info where "
                 "OSID=%s" % osid)
    result = db.run_query_sql(sql_query)
    if result:
        ret_val = result[0][0]
    return ret_val


def get_machine_id_by_name(machine_name):
    """
    Get the machine id from database.
    """
    machine_id = None
    sql_query = "select MachineID from Machine_Info where MachineName='%s'" % machine_name
    result = db.run_query_sql(sql_query)
    if result:
        machine_id = result[0][0]
    return machine_id


def get_sw_info_by_seq_id(seq_id):
    """
    Get the software info of the sequence id from database.
    """
    ret_val = []
    if seq_id == -1:
        ret_val.append('None')
    else:
        seq_query = "select Sequence from GhostSequences where SeqID=%s" % \
                    seq_id
        result = db.run_query_sql(seq_query)
        if result:
            seq_str = result[0][0]
            steps = seq_str.split(',')
            for step in steps:
                step_query = ("select Description from GhostSteps where "
                              "StepID=%s" % step)
                step_result = db.run_query_sql(step_query)
                if step_result:
                    ret_val.append(step_result[0][0])
    return ret_val


def handle_cmd_result(result):
    ret_code = errcode.ER_SUCCESS
    ret_val = ''
    if isinstance(result, Exception):
        ret_code = errcode.ER_EXCEPTION
        ret_val = str(result)
    elif result is socket.timeout:
        ret_code = errcode.ER_TIMEOUT
        ret_val = 'Socket Timeout'
    else:
        try:
            ret_code = int(result)
            ret_val = errcode.strerror(ret_code)
        except Exception:
            ret_code = errcode.ER_FAILED
            ret_val = str(result) or 'Exception Raised'
    return (ret_code, ret_val)


def decide_timeout_by_seq(seq_id):
    """
    Calculate the timeout based on seq_id
    """
    # The default timeout should be increased for the following reasons:
    # 1. the extra time to mount network drive and reboot time.
    # 2. ng installers need more time
    # 3. vmwareagent server supports multiple tasks parallelly. So even though
    #    this task completed, it still need to wait for other Ghosting/Archiving
    #    finished.
    default_timeout = 2 * 60.0 * 60.0 + (_task_concurrency - 1) * _GHOST_TIMEOUT
    if seq_id is None or seq_id == -1:
        return default_timeout
    sql_query = "select distinct Sequence from GhostSequences where SeqID=%s" % seq_id
    rows = db.run_query_sql(sql_query)
    if rows:
        step_str = rows[0][0]
        steps = [step for step in step_str.split(',') if step]
        default_timeout += len(steps) * float(_TIMEOUT_EACH_STEP)
    return default_timeout


def process_error(error, when):
    """
    Print exception error. If error is digit, print the describe of this error,
    else print error directly.

    :param error:
        error code or error string.
    """
    desr = str(error)
    if desr.isdigit():
        desr = errcode.strerror(int(error))
    logger.error("Exception: %s when %s" % (desr, when))
    logger.error(traceback.format_exc())


# Init the VMWareAgent when it start to run
def init_log():
    """Initialize log module"""
    log_path = os.path.dirname(os.path.realpath(__file__))
    log_path_full = os.path.join(log_path, 'Logs')
    if not os.path.exists(log_path_full):
        os.makedirs(log_path_full)
    log_file_full = os.path.join(log_path_full, 'VMWareAgent')
    format = ('%(asctime)-15s:%(levelname)-5s:%(filename)s:%(funcName)s'
              ':T%(thread)d:L%(lineno)-5s:%(message)s')

    logging.basicConfig(level=logging.DEBUG, format=format)
    logging.addLevelName(logging.WARNING, "WARN")

    log_formatter = logging.Formatter(format)
    log_handler = TimedRotatingFileHandler(
        log_file_full, when="D", interval=1, backupCount=30)
    log_handler.suffix = "%Y%m%d_%H%M%S.log"
    log_handler.setFormatter(log_formatter)

    logger.addHandler(log_handler)
    logger.setLevel(logging.DEBUG)


def create_thread_tcp_server():
    """
    Create the tcp server for VMWareAgent to receive the Ghost command
    and verify the server is registed in the database.
    """
    logger.info("start create_thread_tcp_server...")
    try:
        # Create Threading TCP Server
        logger.info("VmWare Server Information: %s:%s" %
                    (_host_address, _vmware_server_port))
        _command_server = ThreadedTCPServer(
            (_host_address, _vmware_server_port), EchoRequestHandler)
        _command_server.serve_forever()
    except Exception, e:
        process_error(e, "Create VMWare Server")
        sys.exit(0)


# Invoked when task is failed
def dump_create_image_task_queue():
    """
    dump those running status tasks into waiting, and decrease their priority
    """
    try:
        rows = get_filter_tasks(
            "ID, Priority, Status, MachineID",
            "Status in ('Ghosting', 'Installing', 'Archiving') and Host='%s'" % (_host_name))
        for row in rows:
            if row[3] and Machine(row[3]).release_machine(_vmware_service_id) != errcode.ER_SUCCESS:
                logger.error('Failed to release machine %s' % (row[3]))
            updated_comment = "Status changed from %s to Waiting due to dump" % (row[2])
            update_task_info(row[0],
                "Status='Waiting', Host='', Priority=%s, Comment='%s',"
                " ParsedSequenceID=NULL, MachineID=NULL" % (row[1]-1, updated_comment))
    except Exception, error:
        process_error(error, "dump task to queue")


def finish_task(task, status, comment, when):
    """handle the finished task and send the notify email"""
    try:
        if 'MachineID' in task:
            machine_id = task['MachineID']
            if Machine(machine_id).release_machine(_vmware_service_id) != errcode.ER_SUCCESS:
                logger.error('Failed to release machine %s' % (machine_id))
            if status != 'Done-Success':
                last_error = _ghost_center.get_last_error(machine_id)
                if last_error:
                    if comment in last_error:
                        comment = last_error
                    else:
                        comment += '\n\t%s' % (last_error)
        update_str = "Status='%s', EndTime=GETDATE(), Comment='%s'" % (
            status, comment.replace("'", "\""))
        if 'EquivalentTaskID' in task:
            update_str += ", EquivalentTaskID=%d" % (task['EquivalentTaskID'])
        update_task_info(task['ID'], update_str)

        # Send Email
        submitter = task['Email'].split(',')
        email_to_list = [addr.strip() for addr in submitter if addr.strip()]
        if not email_to_list:
            email_to_list = _ADMIN_LIST
        subject = "%s [VMWareImage %s]" % (_host_name, status)
        content = generate_email('CreateImage', task['ID'])
        if status == 'Done-Success':
            logger.info("Begin to send email to:%s" % email_to_list)
            g_mail.send(email_to_list, subject, content)
        else:
            logger.info("Begin to send email to:%s cc:%s " %
                        (email_to_list, _ADMIN_LIST))
            g_mail.send(email_to_list, subject, content, cc=_ADMIN_LIST)
        logger.info("Task<%s> %s at %s." % (task['ID'], status, when))
    except Exception, e:
        process_error(e, "try to finish task")


def get_filter_tasks(columns, condition='', order=''):
    """
    Get filter tasks from database.
    """
    if isinstance(columns, list):
        columns = ','.join(columns)
    task_query = "select %s from VMWareImage_TaskStatus" % (columns)
    if condition:
        task_query += " where %s" % (condition)
    if order:
        task_query += " order by %s" % (order)
    rows = db.run_query_sql(task_query)
    return rows


def update_task_info(task_id, info):
    """
    Update the information of specified task ID.
    """
    task_update = ("update VMWareImage_TaskStatus set %s"
                   " where ID=%s; select @@ROWCOUNT" % (info, task_id))
    update_ret = db.run_query_sql(task_update)
    if not update_ret or update_ret[0][0] == 0:
        logger.warning('Failed to update task %s "%s"' % (task_id, info))
        return False
    logger.info('Update task %s "%s" successfully' % (task_id, info))
    return True


def get_installing_task_from_queue():
    """
    Search the installing tasks from queue, and judge whether some task is ready
    to be archived or already timeout. If yes, pop it from the queue.
    """
    columns = ['MachineID', 'ID', 'OSID', 'ExportPath', 'Email',
        'Config', 'StartTime', 'ParsedSequenceID']
    task = None
    try:
        rows = get_filter_tasks(
            columns, "Status='Installing' and Host='%s'" % (_host_name),
            'Priority, SubmitTime')
        for row in rows:
            ghost_status = _ghost_center.get_ghost_stat(row[0])
            if ghost_status == 'InProcess':
                seq_timeout = decide_timeout_by_seq(row[7])
                # if not timeout
                if datetime.now() - row[6] <= timedelta(0, seq_timeout):
                    continue
            task = dict(zip(columns, row))
            task['GhostStatus'] = ghost_status
            break
        if not task:
            return task
        logger.info("Task %s has completed ghost phase(%s), ready to go on"
                    " processing." % (task['ID'], ghost_status))
        if not update_task_info(task['ID'], "Status='Archiving'"):
            task = None
    except Exception, e:
        process_error(e, "try to grab installing task")
        task = None
    return task


def get_waiting_task_from_queue():
    """
    Get the waiting task from queue and set the task status from waiting to ghosting.
    """
    columns = ['ID', 'OSID', 'ExportPath', 'SequenceID', 'Email', 'Config']
    task = None
    try:
        rows = get_filter_tasks(
            columns, "Status='Waiting' and (Host='' or Host='%s')" % (_host_name),
            'Host desc, Priority, SubmitTime')
        if not rows:
            return task
        task = dict(zip(columns, list(rows[0])))
        logger.info("Task %s is waiting, ready to process." % (task['ID']))
        if not update_task_info(task['ID'],
            "Status='Ghosting', Host='%s', StartTime=GETDATE(), Comment=''" % (_host_name)):
            task = None
    except Exception, e:
        process_error(e, "try to grab waiting task")
        task = None
    return task


def find_equivalent_task(task, seq_id, check_days):
    """
    Find whether exists same task within specific days, of which the archive image
    is also existent currently. If exists, we will send email to users that
    a same archived image they want already exists.

    Since that we could only parse windows daily sequence currently,
    and still unable to parse linux/mac daily sequence,
    so we only support to find equivalent windows tasks.
    """
    sql_query = 'select OSPlatform from OS_Info where OSID=%s' % (task['OSID'])
    rows = db.run_query_sql(sql_query)
    if rows[0][0].lower() != 'windows':
        return (None, None)

    if task['Config']:
        config_condition = "Config='%s'" % (task['Config'])
    else:
        config_condition = "(Config='' or Config is NULL)"

    rows = get_filter_tasks(
        "ID, ParsedSequenceID, ExportPath",
        "OSID=%s and Status='Done-Success' and %s and SubmitTime>=DATEADD(Day,-%d, GETDATE())"
        % (task['OSID'], config_condition, check_days),
        "SubmitTime desc")
    try:
        for row in rows:
            # Ignore old records, of which ParsedSequenceID is empty.
            if row[1] in (None, ''):
                continue
            if not sequence.is_equivalent_seq(seq_id, row[1]):
                continue
            if os.path.exists(row[2]):
                # return ID and ExportPath
                return (row[0], row[2])
    except Exception:
        return (None, None)
    else:
        return (None, None)


def find_available_machine():
    """
    Find an available machine, which could be used now.
    """
    available_machine_id = None
    vmname_re = re.compile('^%s_vmware(\d+)$' % (_host_name))
    sql_query = ("select MachineID, MachineName from Machine_Info where"
        " ExpireTime < GETDATE() and MachineName like '%%%s_vmware%%'" % (_host_name))
    rows = db.run_query_sql(sql_query)
    for row in rows:
        vmname_gr = vmname_re.match(row[1])
        if vmname_gr and int(vmname_gr.group(1)) < _task_concurrency:
            available_machine_id = row[0]
            break
    return available_machine_id


@asynchronized(True)
@synchronized(_mutex)
def ghost_task(task):
    """
    Ghost the virtual machine, and update task status to "Installing" when execute
    setup script.

    If find no available machine currently, reput this task into queue.
    Actually, this should never happen, except that specific sast-vm-*_vmware*
    has been checked out by somebody manually, or the available amount of machines
    is less than the value of task_concurrency.
    """
    # initialize variable
    task_id = task['ID']
    osid = task['OSID']
    addr_email = task['Email']
    seq_id = task['ParsedSequenceID']
    timeout = decide_timeout_by_seq(seq_id)

    machine_id = find_available_machine()
    comment = ''
    if not machine_id:
        comment = 'Failed to find available machine now.'
    elif Machine(machine_id).checkout_machine(_vmware_service_id, timeout/3600 + 1):
        # Here, checkout time must be a litter longer than the timeout,
        # since that if the task on this vm finally timeout, it's possible that
        # vmwareagent server finds this vm is available first, and assign another
        # task on this vm immediately. Then vmwareagent server begin to deal
        # with the previous task, and find it already timeout, then release this
        # vm. So as a consequence, this vm is available now while the second
        # task is still running.
        comment = 'Failed to checkout machine %s' % (machine_id)
    if comment:
        logger.warning(comment)
        update_task_info(task_id,
            "Status='Waiting', Comment='%s', ParsedSequenceID=NULL, MachineID=NULL"
            % (comment))
        return False

    update_task_info(task_id, 'MachineID=%d' % (machine_id))


    sql_query = ("select * from Machine_Reimage where MachineID=%s "
                 "and OSID=%s" % (machine_id, osid))
    result = db.run_query_sql(sql_query)
    if not result:
        comment = 'No record in Machine_Reimage about Machine %s OS %s' % (machine_id, osid)
        finish_task(task, 'Done-Failed', comment, 'GhostClient')
        return False

    task['MachineID'] = machine_id
    # call GhostClient to ghost machine
    ghost_errorcode = errcode.ER_EXCEPTION
    ghost_notifier = _ADMIN_LIST[0]
    addr_email_list = _ADMIN_LIST
    if addr_email:
        addr_email_list = [addr.strip() for addr in addr_email.split(',')
                           if addr.strip()]
        ghost_notifier = addr_email_list[0]

    result = _ghost_center.ghost_client(
        machine_id, osid, seq_id, ghost_notifier)
    (ghost_errorcode, ret_val) = handle_cmd_result(result)
    if ghost_errorcode == errcode.ER_TIMEOUT:
        ret_val = 'Timeout when ghosting the virtual machine'
    if ghost_errorcode != errcode.ER_SUCCESS:
        process_error(ghost_errorcode, "execute GhostClient")
        finish_task(task, 'Done-Failed', ret_val, 'GhostClient')
        return False

    update_task_info(task_id, "Status='Installing'")
    return True


def process_equivalent_task(task):
    """
    Judge whether this task has equivalent task.
    If yes, go on processing it, and return True.
    Otherwise, return False directly.
    """
    seq_id = task['ParsedSequenceID']
    update_task_info(task['ID'], 'ParsedSequenceID=%d' % (seq_id))

    export_path = task['ExportPath']
    export_parent_path = os.path.dirname(export_path)
    eq_task_id, eq_export_path = find_equivalent_task(task, seq_id, _CHECK_DAYS)
    if eq_task_id is not None:
        logger.info('Find equivalent task<%d> for task<%d>' % (eq_task_id, task['ID']))
        logger.info('Ready to copy existent image from "%s" to "%s"'
                    % (eq_export_path, export_path))
        try:
            if not os.path.exists(export_parent_path):
                os.mkdir(export_parent_path)
            vm.copy_vm(eq_export_path, export_path)
            # The main purpose of this copy.log is to update the modified time of
            # export_path folder.
            # We have another service "ImageGC.py" to clean up older images on
            # cn-sha-rdfs01 periodically, based on the modification time.
            # However, the modification time of export_path folder won't be updated
            # after copied from eq_export_path. So we need to do some changes
            # under export_path folder, to update the modification time.
            with open(os.path.join(export_path, 'copy.log'), 'w') as fp:
                fp.write('This image is copied from "%s"' % (eq_export_path))
            task['EquivalentTaskID'] = eq_task_id
            comment = "The image has been exported to %s" % export_path
            finish_task(task, 'Done-Success', comment, 'End')
            return True
        except Exception, error:
            logger.error('Failed to copy image "%s": %s' % (eq_export_path, error))
            if os.path.exists(export_path):
                shutil.rmtree(export_path)
    return False


@asynchronized(True)
@synchronized(_mutex)
def archive_task(task):
    """
    Archive virtual machine to server.
    """
    machine_id = task['MachineID']
    osid =  task['OSID']
    export_path = task['ExportPath']
    config = task['Config']

    # call archive image command to copy image to file server
    send_export_path = '"%s"' % repr(export_path)
    try:
        shutil.rmtree(export_path, True)
        logger.info("Remove tree %s successfully" % export_path)
    except Exception, e:
        process_error(e, "remove %s" % export_path)

    result = _ghost_center.archive_vm_image(
        machine_id, osid, send_export_path, config, block_timeout=_ARCHIVE_TIMEOUT)
    (ret_code, ret_val) = handle_cmd_result(result)
    if ret_code == errcode.ER_TIMEOUT:
        ret_val = 'Timeout when archiving the virtual machine'
    if ret_code != errcode.ER_SUCCESS:
        finish_task(task, 'Done-Failed', ret_val, 'ArchiveVMImage')
        return False
    logger.info("Archive Image completes successfully")
    ghost_comment = "The image has been exported to %s" % export_path
    finish_task(task, 'Done-Success', ghost_comment, 'End')
    return True


def do_create_image_task():
    """
    Check the whether server is available and get the ghost task from the
    queue. Send the ghost command to GhostAgent,  export the image to
    cn-sha-rdfs01.
    """
    while not _will_shutdown:
        time.sleep(30)

        if _mutex._Semaphore__value <= 0:
            continue

        # Find whether there is an installing task which has completed.
        task = get_installing_task_from_queue()
        if task:
            if task['GhostStatus'] == 'Passed':
                archive_task(task)
                continue
            if task['GhostStatus'] in ('InProcess', 'Timeout'):
                # timeout already
                comment = 'Timeout when ghosting virtual machine'
            elif task['GhostStatus'] == 'InstallFailed':
                # install failed
                comment = 'Softwares are failed to install correctly'
            else:
                # ghost failed (task['GhostStatus'] == 'None')
                comment = 'Ghost task failed'
            finish_task(task, 'Done-Failed', comment, 'GhostClient')
            continue

        if not find_available_machine():
            continue

        # Then find whether there is a waiting task
        task = get_waiting_task_from_queue()
        if task:
            logger.info("Begin to handle Task<%s>" % task['ID'])
            try:
                # Bring forward to create a new sequence for daily installer,
                # in order to know whether the same task already exists.
                seq_id = sequence.gen_new_seq(task['SequenceID'], throw_exception=True)
                task['ParsedSequenceID'] = seq_id or -1
            except Exception, error:
                finish_task(task, 'Done-Failed', str(error), 'GhostClient')
                continue

            if not process_equivalent_task(task):
                ghost_task(task)
            continue
    return


class ThreadedTCPServer(ThreadingMixIn, TCPServer):
    """
    A tcp server which has the ability to handle exception.
    """
    pass


class EchoRequestHandler(StreamRequestHandler):
    """ StreamRequestHandler Class for ThreadingTCPServer"""
    def parse_cmd_paras(self, cmd_paras):
        seq_id = -1
        email = ''
        vm_conf = '{}'
        email_pat = re.compile(_MAIL_PATTERN)
        for cmd in cmd_paras:
            if cmd.isdigit():
                seq_id = int(cmd)
            elif email_pat.search(cmd):
                email = cmd
            else:
                vm_conf = cmd
        return seq_id, email, vm_conf

    def create_image(self, command_paras, client_addr):
        """
        1. Create an image with specific os and specific StepID list
        2. Send a notification email of ghost status if email address
        provided

        Parameters:
            command_paras:      GhostAgent command and its parameters
            client_addr:    Where we receive this GhostAgent command from

        Command Format:    CreateImage OSID IsDaily ExportPath
                            [SequenceID] [Email] [VmConf]
            OSID:           The 'OSID' column in 'OS_Info' table
            IsDaily:        True if the request is daily, False
                            if the request is on-demand
            ExportPath:     The network path where we can export
                            the vmimage
            SequenceID:     The ID of the sequence user wants to
                            install
            Email:          The email adderss for receiving the
                            notification email of Ghost status
            VmConf:         The config parameters of VMX, such as
                            memsize, numvcpus, cpuid.coresPerSocket.
                            Format: Key,Value;Key,Value; ...
        """
        if len(command_paras) < 4:
            logger.info("Invalid Parameters for CreateImage Command "
                        "from: %s:%s" % (client_addr[0], client_addr[1]))
            return errcode.ER_INVALID_PARAMETER_NUMBER
        ret_code = errcode.ER_SUCCESS
        task = {}
        try:
            paras = self.parse_cmd_paras(command_paras[4:])

            task['OSID'] = command_paras[1]
            task['IsDaily'] = command_paras[2]
            export_folder = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
            export_path = command_paras[3].strip('"')
            task['ExportPath'] = os.path.join(export_path, export_folder)
            task['SequenceID'] = paras[0]
            task['Email'] = paras[1].strip('"')
            task['Config'] = paras[2].strip('"')
            task['SubmitTime'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            task['Comment'] = ''
            task['Status'] = 'Waiting'
            task['Host'] = ''

            # Check whether the OSID is valid
            sql_query = ("select VMwareImage from OS_Info where "
                         "OSID=%s" % task['OSID'])
            result = db.run_query_sql(sql_query)
            if not result or not result[0][0]:
                logger.info("The given OSID %s doesn't have value for "
                            "column <VMwareImage>" % task['OSID'])
                return errcode.ER_INVALID_PARAMETER

            # Decide task priority
            if not cmp(task['IsDaily'].upper(), "True".upper()):
                task['Priority'] = 10
            else:
                task['Priority'] = 5

            # insert this into task status table
            columns = (',').join(task.keys())
            values = (',').join(["'%s'" % v for v in task.values()])
            sql_insert = ("insert into VMWareImage_TaskStatus "
                          "(%s) values(%s);select @@IDENTITY" %
                          (columns, values))
            db.run_query_sql(sql_insert)
            logger.info("put %s with priority %s into database" %
                        (task, task['Priority']))
        except Exception, error:
            process_error(error, "create image task")
            ret_code = errcode.ER_EXCEPTION
        return ret_code

    def auto_upgrade(self, cmd_paras, client_addr):
        """
        Upgrade the VMWareAgent and its related scripts to specific version.

        *Command Format:*
            ``AutoUpgrade``

        .. note::
            If the version on the export server is older than current release,
            skip this command.
        """
        global _is_upgrade
        if platform.system().lower() != "windows":
            logger.info("The Auto update command only support Windows now.")
            return errcode.ER_GA_PF_UNSUPPORT

        if not os.path.exists(_export_server):
            logger.error("The export server <%s> is not exist."
                         % _export_server)
            return errcode.ER_FILE_NONEXIST

        # Get the Target version
        try:
            version_txt_server = os.path.join(_export_server, "version.txt")
            with open(version_txt_server, 'r') as fp:
                file_content = fp.readlines()
        except Exception, error:
            logger.error("Failed to open the export version file<%s> on %s: %s"
                         % (version_txt_server, _export_server, error))
            raise Exception(errcode.ER_FILE_READ_ERROR)

        if len(file_content) < 1:
            logger.error("Invalid version infomation in the export version "
                         "file<%s>." % (version_txt_server))
            raise Exception(errcode.ER_FILE_DATA_WRONG)
        new_version = file_content[0].strip()

        # Get the current version
        version_txt_local = os.path.join(_va_root, "version.txt")
        try:
            with open(version_txt_local, 'r') as fp:
                file_content = fp.readlines()
        except Exception, error:
            logger.error("Failed to open the local version file<%s>: %s"
                         % (version_txt_local, error))
            raise Exception(errcode.ER_FILE_READ_ERROR)

        if len(file_content) < 1:
            logger.error("Invalid version infomation in the local version file"
                         "<%s>." % version_txt_local)
            raise Exception(errcode.ER_FILE_DATA_WRONG)
        cur_version = file_content[0].strip()

        # Compare the target version and current version
        if version.cmp_version(new_version, cur_version) <= 0:
            logger.info("The current version<%s> is newer than the target "
                        "version<%s>." % (cur_version, new_version))
            return errcode.ER_SUCCESS

        # Restart the current script
        _is_upgrade = True
        self.server.shutdown()
        return errcode.ER_SUCCESS

    def handle(self):
        """ handler of ThreadingTCPServer
        """
        command = ""
        command_paras = []
        reply_flag = False
        ret_val = ''
        try:
            logger.info("waiting for new request ...")
            data_recv = self.request.recv(512)
            if not data_recv:
                return
            command_paras = shlex.split(data_recv, posix=False)

            if not command_paras:
                logger.warn("nothing received. handle() exit.")
                return

            client_addr = self.request.getpeername()
            logger.info('RECEIVE COMMAND "%s" from %s'
                        % (data_recv, client_addr))
            command = command_paras[0]
            if (not cmp(command.upper(), "CreateImage".upper())):
                # CreateImage
                ret_code = self.create_image(command_paras, client_addr)
                reply_flag = False
                if ret_code != errcode.ER_SUCCESS:
                    logger.info("Error in CreateImage, Parameters:%s" %
                                (command_paras))
            elif not cmp(command.upper(), "AutoUpgrade".upper()):
                # Upgrade to the latest version on server
                ret_code = self.auto_upgrade(command_paras, client_addr)
                reply_flag = True
                if ret_code != errcode.ER_SUCCESS:
                    logger.info("Error in AutoUpgrade, Parameters:%s" %
                                (command_paras))
            elif not cmp(command.upper(), "GetInfo".upper()):
                ret_code, ret_val = misc.get_info(sys.path[0])
                reply_flag = True
                if ret_code != errcode.ER_SUCCESS:
                    logger.error("Error in GetInfo, Parameters:%s, RetCode "
                                 "%s" % (command_paras, ret_code))
            else:
                logger.error('Invalid Command %s from: %s:%s'
                             % (command, client_addr[0], client_addr[1]))
                logger.error("Commands: %s" % (data_recv))

            if reply_flag:
                try:
                    self.request.send(ret_val)
                except Exception, error:
                    process_error(error, "return message of %s" % command)
            logger.info('FINISH COMMAND "%s" from %s', data_recv, client_addr)
        except SystemExit:
            logger.warning("thread is killed")
        except Exception, error:
            logger.warning("Failed to receive new info from %s: %s"
                           % (client_addr, error))
            logger.error(traceback.format_exc())
        finally:
            if self.request:
                self.request.close()
        logger.info("handle() exit")
        return


def remove_readonly(action, name, exc):
    """
    Clear the readonly flag and delete the folder or file.
    """
    # Add write permission to this folder or file, if it's not a link file.
    if not os.path.islink(name):
        os.chmod(name, os.stat(name).st_mode | stat.S_IWRITE)
    # Make sure that the parent folder has the write permission,
    # otherwise this file/folder still couldn't be removed.
    parent_dir = os.path.dirname(name)
    os.chmod(parent_dir, os.stat(parent_dir).st_mode | stat.S_IWRITE)
    if os.path.isdir(name):
        os.rmdir(name)
    else:
        os.remove(name)
    return


def upgrade_vmwareagent():
    """
    Copy source code of VMWareAgent from file server to local.
    """
    # Copy the target files to local
    logger.info("Start to upgrade VMWareAgent...")
    for directory in os.listdir(_va_root):
        # keep the 'Log' dir, both because the log file
        # maybe in use and we should keep log history
        if directory.lower() == "logs":
            continue

        delpath = os.path.join(_va_root, directory)
        logger.info('Removing "%s"' % delpath)
        try:
            if os.path.isfile(delpath):
                remove_readonly(None, delpath, None)
            elif os.path.exists(delpath):
                shutil.rmtree(delpath, onerror=remove_readonly)
        except Exception, error:
            logger.error('Failed to remove "%s": %s' % (delpath, error))

    # Also need to use system call to copy, to avoid copying failed.
    copy_cmd = ('xcopy "%s" "%s" /e /q /y /r'
                % (_export_server, _va_root))

    logger.info('Execute: %s' % copy_cmd)
    res = os.system(copy_cmd)
    if res == 0:
        logger.info("Upgrade VMWareAgent successfully!")
    else:
        logger.critical("Copy files failed [%s] when doing AutoUpgrade!" % res)
    return


if __name__ == '__main__':
    # Change the title of windows command line terminal
    if platform.system().lower() == "windows":
        os.system('title VMWareAgent')

    # initialize the logging
    init_log()

    # initialize the database
    db.init_db(config.DB_DEFAULT_HOST,
               config.DB_DEFAULT_USER,
               config.DB_DEFAULT_PASSWORD,
               config.DB_DEFAULT_DATABASE)

    if os.environ.get('RESTART_RUN_MAIN') == 'true':
        # initialize some globle variables
        _host_name = socket.gethostname()
        _host_address = misc.gethostipbyname()
        srv_info = get_srv_info_by_name(_host_name)
        (_vmware_server_port, _vmtool_concurrency, _task_concurrency,
            _ghost_server_port, _vmware_service_id) = srv_info
        if _vmtool_concurrency > _task_concurrency:
            logger.warning(
                "TaskConcurrency is smaller than VMToolConcurrency,"
                " which won't make the most of the server performance.")
        # initialize the mutex with vmtool concurrency
        _mutex._initial_value = _vmtool_concurrency
        _mutex._Semaphore__value = _vmtool_concurrency

        _ghost_center = GhostCenter(_host_name, False, _GHOST_TIMEOUT, True)

        # start a threadingtcpserver to handle tcp request
        t = threading.Thread(target=create_thread_tcp_server,
                             name="create_thread_tcp_server")
        t.setDaemon(True)
        t.start()

        t = threading.Thread(target=do_create_image_task,
                             name="do_create_image_task")
        t.setDaemon(True)
        t.start()

        try:
            misc.xsleep(_check_upgrade_interval)
            while not _is_upgrade:
                misc.xsleep(_check_upgrade_interval)

            while len(get_filter_tasks("ID",
                "Status in ('Ghosting', 'Installing', 'Archiving') and Host='%s'" % (_host_name))) > 0:
                misc.xsleep(60)

            upgrade_vmwareagent()
            _is_upgrade = False
            sys.exit(3)
        except KeyboardInterrupt, e:
            logger.info(e)
            logger.info("saving create_image_task to file...")
            _will_shutdown = True
            dump_create_image_task_queue()
            logger.info("pickle done")
            sys.exit(0)
        except Exception, error:
            logger.error("PID %s failed: %s" % (os.getpid(), error))
            sys.exit(0)
        finally:
            logger.info("process exit, PID = %s" % (os.getpid()))

    # Main Process for reload this script
    while True:
        print('PID %s: Reloader Process' % os.getpid())
        args = [sys.executable] + sys.argv
        new_environ = os.environ.copy()
        new_environ['RESTART_RUN_MAIN'] = 'true'
        # Create a new process for receiving commands
        try:
            exit_code = subprocess.call(args, env=new_environ)
            if exit_code != 3:
                print("PID %s: process terminate, exit code: %d"
                      % (os.getpid(), exit_code))
                sys.exit(exit_code)
            else:
                print("PID %s: execution subprocess terminated,"
                      " restart..." % os.getpid())
        except KeyboardInterrupt:
            print("PID %s: Keyboard interrupt" % os.getpid())
            sys.exit(0)
        except Exception, error:
            print("PID %s: %s" % (os.getpid(), error))

    print("PID %s: process exit" % os.getpid())
