#!/usr/bin/python
# Filename: DailyCommand.py
# Usage: DailyCommand.py MachineID
# Send ghost command to non-Windows system for its daily ghost

import pymssql
import socket
import os
import time
import logging
from logging.handlers import TimedRotatingFileHandler
import subprocess
import sys


# Globe Information for Database
g_db_host = 'sast-saas'
g_db_user = 'saas'
g_db_password = 'saassaas'
g_db_name = 'SaaSMetadata'

# Globe Information for Ghost Sequence ini
g_path_of_self = os.path.dirname(os.path.realpath(__file__))


def run_query_sql(sql_statment):
    # Execute Query SQL Statment
    rows = []
    conn = None
    try:
        conn = pymssql.connect(host=g_db_host, user=g_db_user,
                               password=g_db_password, database=g_db_name)
        cur = conn.cursor()
        cur.execute(sql_statment)
        rows = cur.fetchall()
        conn.commit()
        return rows
    except:
        log.error("Failed to execute SQL statment: %s" % sql_statment)
    finally:
        if conn is not None:
            conn.close()


def run_action_sql(sql_statment):
    # Execute Insert/Update SQL Statment
    conn = None
    try:
        conn = pymssql.connect(host=g_db_host, user=g_db_user,
                               password=g_db_password, database=g_db_name)
        cur = conn.cursor()
        cur.execute(sql_statment)
        conn.commit()
        return 0
    except:
        log.error("Failed to execute SQL statment: %s" % sql_statment)
    finally:
        if conn is not None:
            conn.close()


def exe_cmd(cmd, work_dir=None):
    if work_dir is not None:
        os.chdir(work_dir)
    p = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.info(p.stdout.read())
    if p.returncode is None:
        return 0
    else:
        return p.returncode


if __name__ == '__main__':
    # Logging Information
    ISOTIMEFORMAT = '%Y%m%d%H%M%S'
    cur_time = time.strftime(ISOTIMEFORMAT, time.localtime())
    log_root = g_path_of_self + os.sep + "Logs"
    if not os.path.exists(log_root):
        os.makedirs(log_root)
    log_filename = os.path.join(log_root, "DailyGhost.log")
    log = logging.getLogger('DailyCommand.log')
    log.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '[%(asctime)s][%(thread)d][%(levelname)s] %(message)s')
    logfilehandler = TimedRotatingFileHandler(
        log_filename, when='D', interval=7)
    logfilehandler.setLevel(logging.INFO)
    logfilehandler.setFormatter(formatter)
    log.addHandler(logfilehandler)

    # Get the input
    args = sys.argv[1:]
    if len(args) < 1:
        log.error("No parameter for MachineID")
        exit()

    machine_id = args[0]
    # Get the Current Daily Ghost Information
    sql_query = ("select OSID, SeqID from DailyGhost where MachineID=%s and "
                 "CurrentDaily=1" % machine_id)
    result = run_query_sql(sql_query)
    if len(result) != 1:
        log.error("Error in DailyGhost table, there is %s row(s) for "
                  "MachineID<%s>" % (len(result), machine_id))
        exit()

    os_id = result[0][0]
    seq_id = result[0][1]
    # Get the Client Information
    sql_query = ("select GhostServer.ServerName, GhostServer.ServerPort "
                 "from Machine_Reimage, GhostServer where "
                 "Machine_Reimage.MachineID=%s and Machine_Reimage.OSID=%s "
                 "and Machine_Reimage.ServerID=GhostServer.ServerID"
                 % (machine_id, os_id))
    result = run_query_sql(sql_query)
    if len(result) == 0:
        log.error("Could not get server information for Machine<%s> and OS<%s>"
                  % (machine_id, os_id))
        exit()

    server_name = result[0][0]
    server_port = result[0][1]
    server_ip = socket.gethostbyname(server_name)

    # Send the Ghost Command
    client_socket = None
    if seq_id is None:
        cmd_line = "GhostClient %s %s" % (machine_id, os_id)
    else:
        cmd_line = "GhostClient %s %s %s" % (machine_id, os_id, seq_id)
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((server_ip, server_port))
        log.info("Connecting to %s:%s" % (server_ip, server_port))
        client_socket.send(cmd_line)
        log.info("Sending Command: %s" % (cmd_line))
    except socket.error, socket_error:
        log.error("Error when using socket: %s" % (socket_error))
    finally:
        client_socket.close()


