import os
import sys
import stat
import socket
import logging
from logging.handlers import TimedRotatingFileHandler
import shutil
import thread
import traceback
import platform
import SocketServer
import inspect
import re

try:
    # Ignore import error in ghost client machine.
    from nicu.decor import retries, valid_param
    from nicu.notify import NotifyServer
    from nicu.db import SQLServerDB
    import nicu.vm as vm
    import nicu.mail as mail
    import nicu.misc as misc
    import nicu.errcode as errcode
    from nicu.kthread import KThread

    import globalvar as gv
    import util.dbx as dbx
except:
    pass


__all__ = [
    "ThreadedTCPServer",
    "set_logger",
    "retries_default_hook",
    "retries_default",
    "get_error_desr",
    "process_error",
    "remove_old_folders",
    "delete_path",
    "get_platform_bits",
    "update_daily_ghost_task",
    "init_notify_server",
    "upgrade_ghostagent",
    "import_target_modules",
    "export_target_modules",
    "get_mac_addr",
    "get_machine_config",
    "send_ghost_error_email",
    "set_thread_data",
    'get_caller_pos',
]

LOGGER = logging.getLogger(__name__)


class MyThreadingMixIn:
    """Mix-in class to handle each request in a new thread."""

    # Decides how threads will act upon termination of the
    # main process
    daemon_threads = True

    def process_request_thread(self, request, client_address):
        """
        Same as in BaseServer but as a thread.

        In addition, exception handling is done here.
        """
        try:
            self.finish_request(request, client_address)
            self.close_request(request)
        except:
            self.handle_error(request, client_address)
            self.close_request(request)

    def process_request(self, request, client_address):
        """Start a new thread to process the request."""
        t = KThread(target=self.process_request_thread,
                    args=(request, client_address))
        if self.daemon_threads:
            t.setDaemon(1)
        t.start()


class ThreadedTCPServer(MyThreadingMixIn, SocketServer.TCPServer):
    """
    A tcp server which has the ability to handle exception.
    """
    pass


class LastErrorHandler(logging.Handler):
    """
    A handle to record last error, and make codes more intuitive.

    Log this error, and save it to table Ghost_Info.
    If last error has been set in this child thread, it will not be set again.
    So we only reserve the first error, to help us find the original issue.
    However sometimes, we want to try to keep more issues into database,
    which could be overrided by more significant errors.
    So we set level for each error. The smaller number should be more significant.
    """
    def emit(self, record):
        # Only record last error for client machines.
        if not hasattr(gv.g_thread_data, 'machine_id'):
            return
        # If this record hasn't been set with "error_level", ignore it.
        if not hasattr(record, 'error_level'):
            return
        # If this record has a lower priority "error_level" than before, ignore it.
        if hasattr(gv.g_thread_data, 'error_level') \
            and record.error_level >= gv.g_thread_data.error_level:
            return
        gv.g_thread_data.error_level = record.error_level
        gv.g_thread_data.last_error = record.msg
        error_str = record.msg.replace("'", '"')
        if len(error_str) > 255:
            error_str = error_str[:252] + '...'
        dbx.updatex_table('Ghost_Info', 'LastError', error_str,
                          'MachineID=%s' % (gv.g_thread_data.machine_id),
                          quote=True)
        return


def set_logger(logger, file_name, level='INFO'):
    """
    Set the logger property.
    """
    log_dir = 'Logs'
    log_dir_full = os.path.join(gv.g_ga_root, log_dir)
    if not os.path.exists(log_dir_full):
        os.makedirs(log_dir_full)
    log_file_full = os.path.join(log_dir_full, file_name)
    log_handler = TimedRotatingFileHandler(
        log_file_full, when="D", interval=1, backupCount=30)
    log_handler.suffix = "%Y%m%d_%H%M%S.log"
    log_formatter = logging.Formatter(
        '%(asctime)-15s:%(levelname)-5s:%(filename)s:%(funcName)s'
        ':T%(thread)d:L%(lineno)-5s:%(message)s')
    log_handler.setFormatter(log_formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(log_formatter)

    last_error_handler = LastErrorHandler()
    last_error_handler.setLevel(logging.ERROR)

    logger.addHandler(log_handler)
    logger.addHandler(stream_handler)
    logger.addHandler(last_error_handler)
    logger.setLevel(getattr(logging, level))
    return


def retries_default_hook(tries_remaining, exception, delay):
    """
    Default hook, print a warning.

    :param tries_remaining:
        The number of tries remaining.
    :param exception:
        The exception instance which was raised.
    :param delay:
        The delay time to sleep.
    """
    LOGGER.warning('Caught "%s", %d tries remaining, sleeping for %s seconds'
                   % (exception, tries_remaining, delay))
    return


def retries_default(**kwargs):
    """
    Similar with :func:`nicu.decode.retries`, except :func:`retries_default`
    has default values of parameters.

    Default values:
        * max_tries - 3
        * delay - 1
        * backoff - 2
        * exceptions - (:class:`Exception`,)
        * hook - :func:`retries_default_hook`
    """
    def _retries_default(func):
        max_tries = 3 if 'max_tries' not in kwargs else kwargs['max_tries']
        delay = 1 if 'delay' not in kwargs else kwargs['delay']
        backoff = 2 if 'backoff' not in kwargs else kwargs['backoff']
        exceptions = (Exception,) if 'exceptions' not in kwargs \
            else kwargs['exceptions']
        hook = retries_default_hook if 'hook' not in kwargs \
            else kwargs['hook']

        @retries(max_tries, delay, backoff, exceptions, hook)
        def call_func(*args, **kwargs):
            return func(*args, **kwargs)
        return call_func
    return _retries_default


def get_error_desr(error):
    """
    Get describe of error.

    :param error:
        error code or error string.
    :returns: The describe of error.
    """
    desr = str(error)
    if desr.isdigit():
        ret_code = int(desr)
        desr = errcode.strerror(ret_code)
    return desr


def process_error(error, default=None, error_level=3):
    """
    Print exception error. If error is digit, print the describe of this error,
    else print error directly.

    :param error:
        error code or error string.
    :param default:
        the value to return by default.
    :param machine_id:
        store the error into table Ghost_Info if machine_id exists.

    :returns: error code or default error code if exists.
    """
    LOGGER.error(traceback.format_exc())
    ret_code = None
    if isinstance(error, int) or str(error).isdigit():
        ret_code = int(str(error))
    LOGGER.error(get_error_desr(error), extra={'error_level': error_level})
    if default is not None:
        ret_code = ret_code or default
    return ret_code


def remove_old_folders(dailypath, maxkeeps=10):
    """
    Remove old folders, and only keep some copies.

    :param dailypath:
        The daily path to clean up.
    :param maxkeeps:
        The max number of copies to keep.
    """
    LOGGER.info("Remove old folders in %s, only keep %s copies"
                % (dailypath, maxkeeps))
    try:
        ctime_map = {}
        for subdir in os.listdir(dailypath):
            fullpath = os.path.join(dailypath, subdir)
            if not os.path.isdir(fullpath):
                continue
            ctime = os.path.getctime(fullpath)
            ctime_map[ctime] = fullpath
        for ctime in sorted(ctime_map, reverse=True)[maxkeeps:]:
            olddir = ctime_map[ctime]
            delete_path(olddir)
    except Exception, error:
        LOGGER.info("Failed to remove older folders: %s" % (error))
    return


def remove_readonly(action, name, exc):
    """
    Clear the readonly flag and delete the folder or file.
    """
    # Add write permission to this folder or file, if it's not a link file.
    if not os.path.islink(name):
        os.chmod(name, os.stat(name).st_mode + stat.S_IWRITE)
    # Make sure that the parent folder has the write permission,
    # otherwise this file/folder still couldn't be removed.
    parent_dir = os.path.dirname(name)
    os.chmod(parent_dir, os.stat(parent_dir).st_mode + stat.S_IWRITE)
    if os.path.isdir(name):
        os.rmdir(name)
    else:
        os.remove(name)
    return


def delete_path(delpath, is_raise=False):
    """
    Delete the folder or file.

    :param delpath:
        The path of folder or file to delete.
    """
    LOGGER.info('Removing "%s"' % delpath)
    try:
        if os.path.isfile(delpath):
            remove_readonly(None, delpath, None)
        elif os.path.exists(delpath):
            shutil.rmtree(delpath, onerror=remove_readonly)
    except Exception, error:
        LOGGER.error('Failed to remove "%s": %s' % (delpath, error))
        if is_raise:
            raise Exception(error)
        return False
    return True


def get_platform_bits():
    """
    Get windows platform bits.
    """
    model = ''
    if os.name == 'nt' and sys.version_info[:2] < (2,7):
        model = os.environ.get("PROCESSOR_ARCHITEW6432",
                               os.environ.get('PROCESSOR_ARCHITECTURE', ''))
    else:
        model = platform.machine()
    model2bits = {'AMD64': 64, 'x86_64': 64, 'i386': 32, 'x86': 32}
    return model2bits.get(model, None)


@valid_param(mode=(object, 'x==0 or x==1'))  # mode can be 'int' or 'bool'
def update_daily_ghost_task(mode, task_id, task_name, task_command, start_time,
                            server_domain, server_user, server_pwd):
    """
    Update the task status of Windows scheduled task.

    :param mode: pause daily ghost or restart daily ghost.
        * **0** - Pause daily ghost
        * **1** - Restart daily ghost
    :param task_id:
        The `TaskID` column in `DailyGhost` table.
    :param task_name:
        The name of Windows scheduled task.
        GhostAgent Daily Ghost Task: <MachineName>_OSID<OSID>.
    :param task_command:
        The command of Windows scheduled task.
        Command: C:\\Python26\\python.exe "<DailyCommand.py>" <MachineID>
    :param start_time:
        The scheduled start time of Windows scheduled task.
    :param server_domain:
        The domain of Ghost Server machine.
    :param server_user:
        The login user of Ghost Server machine.
    :param server_pwd:
        The password of current server login user.
    """
    # Delete the current daily task
    daily_ghost_cmd = 'schtasks /delete /tn %s /f' % (task_name)
    LOGGER.info("Execute Command: %s" % (daily_ghost_cmd))
    misc.execute(daily_ghost_cmd)

    if mode == 0:
        dbx.updatex_table('DailyGhost', 'Paused', True,
                          'TaskID=%s' % (task_id))
    else:
        # Create new daily task
        daily_ghost_cmd = ('schtasks /create /tn %s /tr "%s" /sc daily'
                           ' /st %s /ru %s\\%s /rp %s'
                           % (task_name, task_command, start_time,
                              server_domain, server_user, server_pwd))
        LOGGER.info("Execute Command: %s" % (daily_ghost_cmd))
        misc.execute(daily_ghost_cmd)
        dbx.updatex_table('DailyGhost', 'Paused', False,
                          'TaskID=%s' % (task_id))
    return


def init_notify_server():
    """
    Initial Notify Server, used to listen notifications from client machine,
    and judge whether the machine has been ghosted.
    """
    notify_type = 'GhostAgent'
    server_name = socket.gethostname().split('.')[0]
    while True:
        try:
            (gv.g_ns_port, ns_platform) = dbx.queryx_table(
                'NotifyServer',
                ['NotifyPort', 'Platform'],
                "ServerName='%s' and Type='%s'" % (server_name, notify_type),
                only_one=True)
            break
        except Exception, error:
            process_error(error)
            LOGGER.info("init_notify_server: retrying in 60 seconds...")
            misc.xsleep(60)
    LOGGER.info("GhostAgent NotifyServer Information: %s:%d"
                % (server_name, gv.g_ns_port))
    gv.g_ns = NotifyServer(server_name=server_name, server_type=notify_type,
                           platform=ns_platform)
    return


def upgrade_ghostagent():
    """
    Copy source code of GhostAgent from file server to local.
    """
    # Copy the target files to local
    for directory in os.listdir(gv.g_ga_root):
        # keep the 'Log' dir, both because the log file
        # maybe in use and we should keep log history
        if directory.lower() == "logs":
            continue
        # keep the exclude.txt, for when use xcopy command to copy files
        # from rdfs01 server, we use this file to exclude some folders.
        if directory.lower() == 'exclude.txt':
            continue
        # keep the 'GhostScripts' dir, because sometimes we may trigger a task
        # directly from Symantec Ghost Console. So we want to reserve it.
        if directory.lower() == "ghostscripts":
            continue
        delete_path(os.path.join(gv.g_ga_root, directory))

    # Also need to use system call to copy, to avoid copying failed.
    copy_cmd = ('xcopy "%s" "%s" /e /q /y /r'
                % (gv.g_export_server, gv.g_ga_root))
    # Since exclude parameters don't support quotes and space,
    # so if if space exists in export server or ghost agent server,
    # we have to use the file in local directory.
    if ' ' not in gv.g_export_server:
        copy_cmd += ' /exclude:%s\\exclude.txt' % (gv.g_export_server)
    elif ' ' not in gv.g_ga_root:
        copy_cmd += ' /exclude:%s\\exclude.txt' % (gv.g_ga_root)
    else:
        copy_cmd += ' /exclude:exclude.txt'

    LOGGER.info('Execute: %s' % copy_cmd)
    res = os.system(copy_cmd)
    if res == 0:
        LOGGER.info("Upgrade GhostAgent successfully!")
    else:
        LOGGER.critical("Copy files failed [%s] when doing AutoUpgrade!" % (res))
    return


def import_target_modules(os_id, is_vm=False):
    """
    Dynamically save modules to dict corresponding to the the target client.

    The key is thread id, and the value is modules based on os & vm.
    """
    sql_str = 'select OSPlatform from OS_Info where OSID=%d' % (int(os_id))
    (target_os_platform, ) = SQLServerDB.query_one(sql_str)
    target_os_platform = target_os_platform.lower()

    if target_os_platform == 'windows':
        import globalvar.gvt_windows as gvt
    elif target_os_platform == 'linux':
        import globalvar.gvt_linux as gvt
    else:
        raise Exception('Unknown os platform: "%s"' % (target_os_platform))

    if is_vm:
        import util.handle.hdl_vm as hdl
    else:
        raise Exception('"IsVM" should be set as True in "Machine_Reimage" table')

    thread_id = thread.get_ident()
    gv.g_thread_lock.acquire()
    gv.g_thread_map[thread_id] = [gvt, hdl]
    gv.g_thread_lock.release()
    return [gvt, hdl]


def export_target_modules():
    """
    Dynamically get modules from dict via current thread id,
    corresponds to :func:`import_target_modules`.
    """
    thread_id = thread.get_ident()
    [gvt, hdl] = gv.g_thread_map[thread_id]
    return [gvt, hdl]


def get_mac_addr(machine_id, image_full):
    """
    Get MAC address from database, if value is NULL,
    then Get MAC address from vmx config and insert
    new MAC address into datebase.
    """
    mac_addr = dbx.queryx_mac_addr(machine_id)[0]
    if not mac_addr:
        mac_addr = vm.get_vmx_conf(image_full, 'ethernet0.generatedAddress').strip('"')
        dbx.updatex_mac_addr(machine_id, mac_addr)
    return '"%s"' % mac_addr


def get_machine_config(machine_id):
    """
    Get CPU and Memory size from Machine_Info table
    """
    machine_config = dbx.queryx_machine_config(machine_id)
    mem_size = int(machine_config[1]) * 1024
    return machine_config[0], mem_size


def send_ghost_error_email():
    """
    Send error message to user when exception happend during `GhostClient`.
    """
    machine_id = gv.g_thread_data.machine_id
    os_id = gv.g_thread_data.os_id
    seq_id = gv.g_thread_data.seq_id
    email_to = gv.g_thread_data.email_to

    mail_server = mail.Mail(gv.g_smtp_server, 25, gv.g_reply_email_from)
    email_list = email_to.split(',')
    machine_name = ''
    os_info = ''
    seq_name = ''
    last_error = ''
    try:
        (machine_name,) = dbx.queryx_table(
            'Machine_Info', 'MachineName', 'MachineID=%s' % machine_id, only_one=True)
        column = ("OSPlatform+' '+OSVersion+' '+CONVERT(varchar, "
                  "OSBit)+'bit '+OSPatch+' '+OSLanguage")
    except Exception, e:
        LOGGER.error(e)
    try:
        (os_info,) = dbx.queryx_table(
            'OS_Info', column, 'OSID=%s' % os_id, only_one=True)
        os_info = os_info.replace('  ', ' ')
    except Exception, e:
        LOGGER.error(e)
    try:
        if seq_id != -1:
            (seq_name,) = dbx.queryx_table(
                'GhostSequences', 'SeqName', 'SeqID=%s' % seq_id, only_one=True)
    except Exception, e:
        LOGGER.error(e)
    try:
        (last_error,) = dbx.queryx_table(
            'Ghost_Info', 'LastError', 'MachineID=%s' % machine_id, only_one=True)
        if not last_error and hasattr(gv.g_thread_data, 'last_error'):
            last_error = gv.g_thread_data.last_error
    except Exception, e:
        LOGGER.error(e)
    subject = "[GhostAgent][Exception] %s" % machine_name
    content = ("There is an exception happend in GhostAgent, "
               "please check your command or contact to administrator.\n\n")
    content += "%-12s %s\n" % ("OS:", os_info)
    if seq_name:
        content += "%-12s %s\n" % ("Sequence:", seq_name)
    content += "%-12s %s" % ("Exception:", last_error.replace(':', '.'))
    mail_server.send(email_list, subject, content, cc=[gv.g_sast_group_email])
    return


def reset_thread_data():
    """
    Reset thread data.
    """
    gv.g_thread_data.__dict__.clear()
    return


def set_thread_data(**kwargs):
    """
    Set data for this thread only.
    """
    for key, value in kwargs.items():
        setattr(gv.g_thread_data, key, value)
    return


def get_caller_pos(level=1):
    '''
    Get the caller position.
    '''
    # Exclude the layer for get_caller_pos and format_stack functions.
    actual_level = level + 2
    frame = inspect.currentframe()
    stack_trace = traceback.format_stack(frame)
    if len(stack_trace) < actual_level:
        return ''
    line = stack_trace[-1 * actual_level].split('\n')[0]
    line_re = re.compile('.*,\s+line\s+(?P<line>\d+),\s+in\s+(?P<caller>.*)')
    line_gr = line_re.match(line)
    if not line_gr:
        return ''
    return '[%s:%s]' % (line_gr.group('caller'), line_gr.group('line'))
