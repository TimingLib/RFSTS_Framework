#!/usr/bin/python
# Filename: GhostAgent.py
"""
+------------------------------------------------------+--------------------------------+--------------------------------------------------+
|                     Commands                         |                     Server     |                      Client                      |
+                                                      +---------+-------+--------+-----+---------+-------+--------+------------+----------+
|                                                      | Windows | Linux | MacOSX | VM  | Windows | Linux | MacOSX | VM Windows | VM Linux |
+======================================================+=========+=======+========+=====+=========+=======+========+============+==========+
| GhostClient MachineID OSID [SequenceID] [Email]      | Yes     | Yes   | Yes    | Yes | Yes     | Yes   | Yes    | Yes        |          |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| PauseDaily MachineID                                 | Yes     | Yes   |        | Yes | N/A     | N/A   | N/A    | N/A        | N/A      |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| RestartDaily MachineID                               | Yes     | Yes   |        | Yes | N/A     | N/A   | N/A    | N/A        | N/A      |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| UpdateGhostStat MachineID OSID                       | Yes     | Yes   | Yes    | Yes | N/A     | N/A   | N/A    | N/A        | N/A      |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| UpdateSeqStat MachineID SeqID                        | Yes     | Yes   | Yes    | Yes | N/A     | N/A   | N/A    | N/A        | N/A      |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| LocalCMD                                             | Yes     | Yes   | Yes    | Yes | N/A     | N/A   | N/A    | N/A        | N/A      |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| GrabNewImage MachineID OSID                          | Yes     |       |        | Yes | N/A     | N/A   | N/A    | N/A        | N/A      |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| ReGrabImage MachineID OSID [SequenceID] [Email]      | Yes     |       |        |     | N/A     | N/A   | N/A    | N/A        | N/A      |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| AutoUpgrade                                          | Yes     |       |        | Yes | N/A     | N/A   | N/A    | N/A        | N/A      |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| DeployVMImage [MachineID:OSID;MachineID:OSID;...]    | N/A     | N/A   | N/A    | Yes | N/A     | N/A   | N/A    | Yes        |          |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| ArchiveVMImage MachineID OSID Destination [Email]    | N/A     | N/A   | N/A    | Yes | N/A     | N/A   | N/A    | Yes        |          |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| SetLogLevel Level                                    | Yes     | Yes   | Yes    | Yes | N/A     | N/A   | N/A    | N/A        | N/A      |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
| ReleaseMachine ServiceID MachineID                   |         |       |        |     |         |       |        |            |          |
+------------------------------------------------------+---------+-------+--------+-----+---------+-------+--------+------------+----------+
"""
from __future__ import with_statement
import os
import shutil
import sys
import subprocess
import traceback
import atexit
import logging

# Should import db first, and then import socket.
# Otherwise, some platforms will appear errors:
#   tds_init_winsock wsaenumprotocols failed with 10055
import nicu.db as db
import nicu.misc as misc
import nicu.config as config
from nicu.decor import asynchronized

import globalvar as gv
import util
import util.dbx as dbx
from util.handle import EchoRequestHandler
import socket


LOGGER = logging.getLogger()


@atexit.register
def rm_lock_root():
    """
    Remove `.LockRoot` directory if type of Ghost Server is vmware.
    """
    util.delete_path(gv.g_vm_lock_root)
    return


@asynchronized(True)
def create_handle_server():
    """
    Create a threading TCP server to handle requests with specific port.
    """
    # Create Threading TCP Server
    try:
        server_name = socket.gethostname().split('.')[0]
        while True:
            try:
                (server_port,) = dbx.queryx_table(
                    'GhostServer', 'ServerPort',
                    "ServerName='%s'" % (server_name),
                    only_one=True)
                break
            except Exception, error:
                util.process_error(error)
                LOGGER.info("create_handle_server: retrying in 60 seconds...")
                misc.xsleep(60)

        LOGGER.info("GhostAgent Information: %s:%d"
                    % (gv.g_server_ip, server_port))
        handle_server = util.ThreadedTCPServer(
            (gv.g_server_ip, server_port), EchoRequestHandler)
        LOGGER.info("Request handler in working ...")
        handle_server.serve_forever()  # block call
    except Exception, error:
        LOGGER.error("Error in create_handle_server: %s\n%s"
                     % (error, traceback.format_exc()))
        sys.exit(0)


if __name__ == '__main__':
    # Change the title of windows command line terminal
    if gv.g_platform == "windows":
        os.system('title GhostAgent')

    # initial database
    db.init_db(config.DB_DEFAULT_HOST, config.DB_DEFAULT_USER,
               config.DB_DEFAULT_PASSWORD, config.DB_DEFAULT_DATABASE)

    if os.environ.get('RESTART_RUN_MAIN') == 'true':
        # initial LOGGER
        util.set_logger(LOGGER, 'GhostAgent', level='INFO')

        if gv.g_platform == "windows":
            gv.g_server_ip = misc.gethostipbyname()

        # clean lck environment in case this script is interrupted brutally
        util.delete_path(gv.g_vm_lock_root)
        try:
            LOGGER.debug('make dir %s' % gv.g_vm_lock_root)
            os.makedirs(gv.g_vm_lock_root)
        except Exception, error:
            LOGGER.warn(error)

        # initial NotifyServer
        util.init_notify_server()
        # create Threading TCP Server with a new Thread
        create_handle_server()

        try:
            misc.xsleep(gv.g_check_upgrade_interval)
            while not gv.g_is_upgrade:
                misc.xsleep(gv.g_check_upgrade_interval)

            util.upgrade_ghostagent()
            # should stop notify server here, otherwise this process will
            # never exit.
            gv.g_ns.stop()
            gv.g_is_upgrade = False
            sys.exit(3)
        except KeyboardInterrupt:
            LOGGER.error("keyboard interrupt! PID = %s" % (os.getpid()))
            sys.exit(0)
        except Exception, error:
            LOGGER.error("PID %s failed: %s" % (os.getpid(), error))
            sys.exit(0)
        finally:
            LOGGER.info("process exit, PID = %s" % (os.getpid()))

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

