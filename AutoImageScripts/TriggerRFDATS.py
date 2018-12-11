#!/usr/bin/env python
"""
Python script to trigger RFDATS in a given time for RFSTS
"""
import multiprocessing
import os
import sys
import time
import re
import logging
import logging.handlers
import optparse

# [8:00AM, 9:00PM] @NIC
expectTimeRange = (0, 23)
currenttime = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
localDir = ''
_trunk_ver_pat = re.compile(r'^\d{1,2}.\d$')

def process_command_line(argv):
    parser = optparse.OptionParser(usage='TriggerRFDATS.py [options]',
                                   description='''The Script is used to trigger RFDATS.
                                   Requires: 
                                   trunkversion = <trunk version>,
                                   vst0 = <vst0 target name>,
                                   vst1 = <vst1 target name>,
                                   vst2 = <vst2 target name>''',
                                   formatter=optparse.TitledHelpFormatter(width=50))

    required_opts = optparse.OptionGroup(parser, 'REQUIRED', 'These parameters are required')
    required_opts.add_option('--trunkversion', action='store', type='float', default=None, help='''This is the trunk version for the prerelease.''')
    required_opts.add_option('--vst0', action='store', default=None, help='''This is target test name for no hardware related.''')
    required_opts.add_option('--vst1', action='store', default=None, help='''This is target test name for only one VST available.''')
    required_opts.add_option('--vst2', action='store', default=None, help='''This is target test name for T2.''')
    parser.add_option_group(required_opts)
    settings, args = parser.parse_args(argv)
    return settings, args


def triggerRFDATS(timeRangeL, timeRangeH, vst0, vst1, vst2):
    logger = init_logger()
    while True:
        # poll local time every 60 seconds
        time.sleep(10)
        hour = time.localtime()[3]
        if hour not in range(timeRangeL, timeRangeH + 1):
            continue
        try:
            eventLog(logger, 'Start to trigger FDATS')
            if vst0:
                print(vst0)
            if vst1:
                print(vst1)
            if vst2:
                print(vst2)
            time.sleep(10)
#            execSysCmd(vst0)
#            execSysCmd(vst1)
#            execSysCmd(vst2)
        except Exception as error:
            eventLog(logger, 'Error found when triggering FDATS: %s' % error)
            print(str(error))
        finally:
            eventLog(logger, 'Quit the monitoring script')
            break


def validate_command_line_options(settings):
    """
    If there exist error while validate the command, return true
    """
    if settings.trunkversion is None:
        print("Error: Please specify the trunk version")
        return True
    elif not _trunk_ver_pat.match(str(settings.trunkversion)):
        print("Error: Invalid trunk version: " + settings.trunkversion)
        return True

    if ((settings.vst0 is None) and (settings.vst1 is None) and (settings.vst2 is None)):
        print("Error: Please specify at least one target name ")
        return True

    return False


def main(argv):
    settings, args = process_command_line(argv)
    error = validate_command_line_options(settings)
    if error:
        return 1

    vst0 = preset_target + ' "' + 'Deploy Images\\RFSTS\\rfdats-' + str(settings.vst0) + '-deploy' + '"'
    vst1 = preset_target + ' "' + 'Deploy Images\\RFSTS\\rfdats-' + str(settings.vst1) + '-deploy' + '"'
    vst2 = preset_target + ' "' + 'Deploy Images\\RFSTS\\rfdats-' + str(settings.vst2) + '-deploy' + '"'

    daemon = multiprocessing.Process(name='TriggerRFDATS', target=triggerRFDATS, args=expectTimeRange+(vst0, vst1, vst2))
    daemon.daemon = True
    daemon.start()
    daemon.join()


def execSysCmd(command):
    ret = os.system(command)
    if ret is not 0:
        raise Exception("Invalid Command: %s" % command)


def eventLog(logger, event):
    logger.debug('[' + time.ctime() + ']: ' + event)


def init_logger():
    """This function initializes the logger setting."""
    logger = logging.getLogger()
    logging.raiseExceptions = False

    logger.setLevel(logging.DEBUG)
    log_path = os.path.abspath(os.path.dirname(__file__))
    if not os.path.exists(log_path):
        os.makedirs(log_path)

    log_file_name = (log_path + os.sep + "FDATS_" +
                     time.strftime("%Y%m%d", time.localtime()) + ".log")

    # Rotate the log file every three days and keep 10 files at most
    log_file_handler = logging.handlers.TimedRotatingFileHandler(
        log_file_name, when='D', interval=3, backupCount=10)
    log_file_handler.setLevel(logging.DEBUG)
    logger.addHandler(log_file_handler)
    return logger


if __name__ == '__main__':
    """create a daemon to trigger RFDATS in the given time"""
    status = 0
    localDir = os.path.abspath(os.path.dirname(__file__))
    preset_target = str(localDir) +'/triggerGhostServerTask.py'

    logger = init_logger()
    eventLog(logger, 'Start python script to trigger RFDATS for RFSTS at ' + currenttime)
    if not os.path.exists(localDir + '/triggerRFDATS.token'):
        eventLog(logger, 'Token file not found, start to monitor the local time')
        status = main(sys.argv)
    else:
        eventLog(logger, "Token file found, the monitoring script won't be triggered")
    sys.exit(status)
