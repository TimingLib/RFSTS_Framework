#!/usr/bin/python
# Filename: GhostNotifyEmail.py

import os
import sys
import re
import ConfigParser
import platform
import smtplib
import socket
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from util.report import *


# Configuration for Email
COMMASPACE = ', '
g_addr_from = 'donotreply_sast@ni.com'
g_addr_to_admnin_list = ['SAST.Installer.N.Services@ni.com']

# Configuration for Log
g_log_file = 'scriptOut.log'
g_log_pattern = '\[(INFO|WARNING|ERROR)\]: (.*)'
g_step_begin_pattern = '\[INFO\]: Executing step: (.*)'
g_step_end_pattern = '\[INFO\]: Finished step: (.*)'
g_installer_pattern = '\[INFO\]: Latest installer folder detected is: (.*)'

# Configuration for ini
g_script_ini = 'script.ini'
if platform.system() == "Linux":
    g_script_ini = '/mnt/mainboot/script.ini'
elif platform.system() == "Darwin":
    g_script_ini = '/Volumes/Storage/Testfarm/script.ini'

# Configuration for ghost status
g_status_log_file = 'ghostStatus.log'


def get_os_info():
    def machine():
        """Return type of machine."""
        if os.name == 'nt' and sys.version_info[:2] < (2, 7):
            return os.environ.get(
                "PROCESSOR_ARCHITEW6432",
                os.environ.get('PROCESSOR_ARCHITECTURE', ''))
        else:
            return platform.machine()

    def os_bits():
        """Return bitness ('32bit' or '64bit') of operating system"""
        machine2bits = {'AMD64': '64bit', 'x86_64': '64bit', 'i386': '32bit',
                        'x86': '32bit'}
        return machine2bits.get(machine(), '32bit')

    return ("Current OS Information: %s_%s (%s %s)"
            % (platform.system(), platform.release(), os_bits(), machine()))


def generate_step_row(step_name, step_logs, step_status=True):
    ''' Get step inforamtion from the ini file, and generate step report
        step_name: step name
        step_logs: logs for this step
        step_status: True=Success; False=Failed
    '''
    script_parser = ConfigParser.ConfigParser()
    script_parser.readfp(open(g_script_ini))

    step_type = script_parser.get(step_name, "type")
    cmd_str = ''
    source_path = ''
    path_suffix = ''
    loc_cmd = ''
    loc_cmd_paras = ''
    installer_export = ''

    # Generate command
    if step_type in ('command', 'latest_installer', 'installer'):
        source_path = script_parser.get(step_name, "path")
        if script_parser.has_option(step_name, "path_suffix"):
            path_suffix = script_parser.get(step_name, "path_suffix")
        loc_cmd = script_parser.get(step_name, "command")
        loc_cmd_paras = script_parser.get(step_name, "flags")
        if step_type == 'command' or step_type == 'installer':
            cmd_str = "%s%s %s" % (source_path, loc_cmd, loc_cmd_paras)
        if step_type == 'latest_installer':
            is_latest = script_parser.get(step_name, "find_latest")
            if is_latest == "1":
                installer_pat = re.compile(g_installer_pattern)
                for line in step_logs:
                    result = installer_pat.search(line)
                    if result:
                        installer_export = result.group(1)
                cmd_str = ("%s%s%s%s %s"
                           % (source_path, installer_export, path_suffix,
                              loc_cmd, loc_cmd_paras))
            else:
                cmd_str = "%s%s %s" % (source_path, loc_cmd, loc_cmd_paras)
    if step_type == 'notifier':
        notify_host = script_parser.get(step_name, "host")
        notify_port = script_parser.get(step_name, "port")
        notify_msg = script_parser.get(step_name, "message")
        cmd_str = ("Sending Msg to %s:%s. The message is [%s]."
                   % (notify_host, notify_port, notify_msg))
    if step_type == 'reboot':
        cmd_str = "Reboot System"

    # get step result
    if step_status:
        step_result = 'Success'
    else:
        step_result = 'Failed'

    # Generate Row
    step_row = generate_row(
        [step_name, step_type, step_result, cmd_str], step_result)
    return step_row


def update_ghost_stat(ghost_stat, ghost_srv_host, ghost_srv_port,
                      ghost_srv_msg, ghost_req_host, ghost_req_port):
    email_content = ""
    if ghost_stat:
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((ghost_srv_host, ghost_srv_port))
            client_socket.send(ghost_srv_msg)
            res = ("Succeed to send msg(%s) to Ghost Server(%s:%s)"
                   % (ghost_srv_msg, ghost_srv_host, str(ghost_srv_port)))
        except socket.error, socket_error:
            print "Error when using socket: ", socket_error
            res = ("Failed to send msg(%s) to Ghost Server(%s:%s): %s"
                   % (ghost_srv_msg, ghost_srv_host, str(ghost_srv_port),
                      socket_error))
        finally:
            email_content += generate_row(["Notify Ghost Server", res])
            client_socket.close()

    return email_content


def generate_email(filepath, ghost_srv_host, ghost_srv_port, ghost_srv_msg,
                   ghost_req_host, ghost_req_port):
    ''' Reading the log file, and generating the email
        filepath: ghost log file
    '''
    # Ghost Status
    step_report_header = ["Step Name", "Step Type", "Status", "Comments"]
    step_report_name = "ghoststatus"
    log_report_header = ["Log"]
    log_report_name = "log"
    ghost_status = "Success"
    ghost_report = [socket.gethostname(), "Ghost", ghost_status, get_os_info()]
    result = []

    email_content = generate_html_header()
    email_content += generate_table_header(step_report_name, step_report_header)
    email_content += generate_row(ghost_report, ghost_status)
    full_log = ''
    try:
        fsock = open(os.path.normcase(filepath), "r")
        try:
            # Get the log content
            flines = fsock.readlines()
            fsock.close()

            # Genertate Regular Pattern
            log_pat = re.compile(g_log_pattern)
            step_begin_pat = re.compile(g_step_begin_pattern)

            # Set initial flags
            step_begin_flag = False
            step_fail_flag = True
            line_tmp = []
            step_name = ''
            for line in flines:
                common_line = log_pat.search(line)
                step_begin_line = step_begin_pat.search(line)

                # Generate Full Log
                full_log += line + "<br>"

                # Get log information for each step
                if step_begin_line:
                    if step_begin_flag:
                        email_content += generate_step_row(
                            step_name, line_tmp, step_fail_flag)
                        step_fail_flag = True
                        line_tmp = []
                        step_name = ''
                    # begin of one step
                    step_begin_flag = True
                    step_name = step_begin_line.group(1)

                if step_begin_flag and common_line:
                    # log for one step
                    line_tmp.append(line)
                    if common_line.group(1) == 'ERROR':
                        # Step failed
                        step_fail_flag = False
                        ghost_status = "ERROR"

                # Failed in initialization.
                # Get Error Message Before Execute Step.
                if (not step_begin_flag) and \
                        common_line and common_line.group(1) == 'ERROR':
                    email_content += "Error before executing steps.<br>"
                    break
            else:
                email_content += generate_step_row(
                    step_name, line_tmp, step_fail_flag)
            email_content += generate_table_footer()
        except IOError:
            print "IOError"
            ghost_status = 'Failed'
    except IOError:
        print "IOError"
        ghost_status = 'Failed'
    finally:
        if ghost_status == 'Failed':
            res = "Failed when parsing the script.log"
        elif ghost_status == 'ERROR':
            res = "Failed when executing the steps in the script.ini"
        elif ghost_status == 'Success':
            res = "Succeed to execute the steps in the script.ini"

        # Generating Final result information table
        email_content += "<HR>"
        email_content += generate_table_header(
            "NotifyActionsSummary", ["Notify Actions", "Summary"])
        email_content += generate_row(["Execute Steps", res])
        email_content += update_ghost_stat(
            (ghost_status == 'Success'), ghost_srv_host, int(ghost_srv_port),
            ghost_srv_msg, ghost_req_host, int(ghost_req_port))
        email_content += generate_table_footer()
        email_content += generate_html_footer()

        # Generating log detail information table
        email_content += "<HR>"
        email_content += generate_table_header(log_report_name,
                                               log_report_header)
        email_content += generate_row([full_log])
        email_content += generate_table_footer()
        email_content += generate_html_footer()

        result.append(ghost_status)
        result.append(email_content)

        return result


def send_email(smtp_server, ghost_status, mail_to, html_part, plain_part=''):
    # Generate mailto List
    mail_to_list = []

    # Mail Root
    email_root = MIMEMultipart('related')
    email_root['Subject'] = ("[Ghost Status Report][%s] %s"
                             % (ghost_status.upper(), socket.gethostname()))
    email_root['From'] = g_addr_from
    if mail_to != "":
        mail_to_list.append(mail_to)
        email_root['To'] = COMMASPACE.join(mail_to_list)

    if ghost_status == 'ERROR':
        print "CC Error Notify Email to Administrators."
        email_root['Cc'] = COMMASPACE.join(g_addr_to_admnin_list)
        mail_to_list.extend(g_addr_to_admnin_list)

    if len(mail_to_list) == 0:
        print "Skip sending email."
        return 0

    # Encapsulate the plain and HTML versions of the message body in an
    # 'alternative' part, so message agents can decide which they want to
    # display.
    msg_alternative = MIMEMultipart('alternative')
    email_root.attach(msg_alternative)

    # Setting TEXT Information
    MsgText = MIMEText(plain_part, 'plain', 'utf-8')
    msg_alternative.attach(MsgText)

    # Setting HTML Information
    msg_html = MIMEText(html_part, 'html', 'utf-8')
    msg_alternative.attach(msg_html)

    smpt = smtplib.SMTP(smtp_server)
    smpt.ehlo()
    try:
        print "Sending Email to ", mail_to_list
        smpt.sendmail(g_addr_from, mail_to_list, email_root.as_string())
    except Exception, ex:
        print Exception, ex
    finally:
        smpt.quit()


def store_ghost_status(ghost_status):
    try:
        print 'Store ghost status to file "%s"' % (g_status_log_file)
        with open(g_status_log_file, 'w') as fp:
            fp.write('Passed' if ghost_status == 'Success' else 'InstallFailed')
    except Exception, ex:
        print Exception, ex
    return


if __name__ == '__main__':
    # if do not specific a log file, use the g_log_file as default
    args = sys.argv[1:]
    log_file_path = g_log_file
    if len(args) == 1:
        log_file_path = args[0]

    # Get Mail Information
    script_parser = ConfigParser.ConfigParser()
    try:
        script_parser.readfp(open(g_script_ini))

        step_list_str = script_parser.get("steps", "orderlist")
        step_list = step_list_str.split('&')
        for step in step_list:
            step_status = script_parser.get("steps", step)
            step_always_run = 0
            if script_parser.has_option(step, "always_run"):
                step_always_run = script_parser.get(step, "always_run")
            if step_always_run == '0' and step_status == '1':
                print "The steps have not finished yet."
                exit()

        smtp_server = script_parser.get("emailconfiguration", "mailserver")
        if smtp_server == 'mailmass':
            smtp_server = 'mailmass.natinst.com'
        mail_to = script_parser.get("emailconfiguration", "mailto")

        ghost_srv_host = script_parser.get("updateseqstatus", "srvhost")
        ghost_srv_port = script_parser.get("updateseqstatus", "srvport")
        ghost_srv_msg = script_parser.get("updateseqstatus", "srvmessage")

        ghost_req_host = script_parser.get("updateseqstatus", "reqhost")
        ghost_req_port = script_parser.get("updateseqstatus", "reqport")

        # Generate the Email Content
        result = generate_email(log_file_path, ghost_srv_host, ghost_srv_port,
                                ghost_srv_msg, ghost_req_host, ghost_req_port)

        store_ghost_status(result[0])
        # Send Email
        if result[0] == 'Failed':
            send_email(smtp_server, 'ERROR', mail_to,
                       'Error When parsing the log file.')
        else:
            email_content_html = result[1]
            send_email(smtp_server, result[0], mail_to, email_content_html)
    except Exception, ex:
        print Exception, ex

