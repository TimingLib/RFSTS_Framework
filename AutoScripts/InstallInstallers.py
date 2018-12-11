"""
Description : Python script intents to installing the software stack with the installers defined from installer.log.
Autor   : Yang
Date    : 6/15
"""

import os
import sys
import time
import argparse
import logging
import logging.handlers

currenttime = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())

def initialize_command_line(argv):
    '''
    Parse the arguments that user provided
    '''
    parser = argparse.ArgumentParser(usage='installInstallers.py -f <File> ',
                                    description='''The Script is used to install the installers which are listed in the <file>.
                                    Requires:
                                    F   <File> SPECIFY THE FILE LISTED THE INSALLERS PATH''',
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
    required_opts = parser.add_argument_group(title='REQUIRED', description='These parameters are required')
    required_opts.add_argument('-f','--file', action='store', required=True, help='''Please input the file including the installer path''')
    settings = parser.parse_args(argv)
    return settings


def validate_command_line_options(settings):
    """
    If there exist error while validate the command, raise exception
    """
    if not os.path.exists(settings.file) or not os.path.isfile(settings.file):
        raise Exception("The file path is invalid")
    else:
        if not os.path.getsize(settings.file):
            raise Exception("There are not available installers")


def init_logger():
    '''
    Initialize the logger setting
    '''
    logger = logging.getLogger()
    logging.raiseExceptions = False

    logger.setLevel(logging.DEBUG)
    log_file_name = (r"C:" + os.sep + "installExcute" + "_" + time.strftime("%Y%m%d", time.localtime()) + ".log")
    # Rotate the log file every three days and keep 10 files at most
    log_file_handler = logging.handlers.TimedRotatingFileHandler(log_file_name, when='D', interval=3, backupCount=10)
    log_file_handler.setLevel(logging.DEBUG)
    logger.addHandler(log_file_handler)
    return logger


def eventLog(logger, event):
    logger.debug('[' + time.ctime() + ']: ' + event)


def execSysCmd(command):
    ret = os.system(command)
    if ret is not 0:
        raise Exception


def install_Installers(installer_file_name):
    '''
    Fetch the installer path and install
    '''
    try:
        with open(installer_file_name) as text:
            for installers in text.readlines():
                time.sleep(10)
                installer = installers.rstrip('\n')
                eventLog(logger, 'Install : %s' % installer)
                (pathname, shortname) = os.path.split(installers)
                if "setup" in shortname:
                    command = 'Start /wait "ANYTHING!" ' + '"' + installer + '"' + ' /q /acceptlicenses yes /log C:\installtrace.log /r:n /confirmCriticalWarnings /disableNotificationCheck'
                    print(command)
                elif "NI_STS_Auxiliary_RF_Tools" in shortname:
                    command = 'Start /wait "ANYTHING!" ' + '"' + installer + '"' + ' /install /passive /norestart'
                    print(command)
                eventLog(logger, 'Command : %s' % command)
                execSysCmd(command)
    except Exception as abc:
        eventLog(logger, str(abc))
        raise abc
    

def main(argv):
    settings = initialize_command_line(argv)
    try:
        validate_command_line_options(settings)
    except Exception as error:
        eventLog(logger, str(error))
        raise error
    eventLog(logger,"Start to install the installers from the file parameter")
    install_Installers(settings.file)
    return 0


if __name__ == '__main__':
    """create a daemon to installe the software stack in the given time"""
    logger = init_logger()
    eventLog(logger,currenttime + ' Start python script to install the installers')
    sys.exit(main(sys.argv[1:]))