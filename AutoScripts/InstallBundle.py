"""
Description : Python script intents to installing the CDS Bundle with the Version Selector.
Autor   : Yang
Date    : 7/5
"""

import os
import re
import sys
import time
import argparse
import zipfile
import logging
import logging.handlers

currenttime = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())

def initialize_command_line(argv):
    '''
    Parse the arguments that user provided
    '''
    parser = argparse.ArgumentParser(usage='InstallBundle.py -f <File> ',
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
    '''
    Create the event log
    '''
    logger.debug('[' + time.ctime() + ']: ' + event)


def unzip_bundle_from_server(src, dest):
    '''
    Unzip the zip file to the destination folder
    '''
    try:
        with zipfile.ZipFile(src,'r') as zip:
            for file in zip.namelist():
                zip.extract(file,dest)
    except IOError as err:
        raise err


def del_maintenance_from_definition(defpath):
    '''
    Diable the installition of the maintenance software on VST_01
    '''
    if os.getenv('COMPUTERNAME') == 'RFSTS_VST_01':
        for xml in os.scandir(defpath):
            with open(xml.path, "r+") as fn:
                pattern = re.compile(r"Action\b")
                lines = [line for line in fn.readlines() if pattern.search(line) is None]
                fn.seek(0)
                fn.truncate(0)
                fn.writelines(lines)
        return 0


def main(argv):
    '''
    Execute main function to install the specified bundle
    '''
    verselectorrepo = r"C:\\ProgramData\\National Instruments\\STS Version Selector\\STSSoftwareRepository"
    settings = initialize_command_line(argv)
    try:
        validate_command_line_options(settings)
        with open(settings.file) as text:
            bundlezip = text.readline().rstrip('\n')
            bundlename = os.path.basename(bundlezip).replace(".zip","")
    except Exception as error:
        eventLog(logger, str(error))
        raise error
    eventLog(logger,"Start to install the installers from the file parameter")
    eventLog(logger, 'Install : %s' % bundlezip)
    print("--------Waiting for unzipping the %s zip file!---------" % bundlename)
    print("--------...........................---------")
    unzip_bundle_from_server(bundlezip,verselectorrepo)
    print("--------Unzipping the %s zip file Done!----------" % bundlename)
    del_maintenance_from_definition(os.path.join(verselectorrepo,"Bundle Definitions"))
    return 0


if __name__ == '__main__':
    """create a daemon to pre-install the bundle in the given time"""
    status = 0
    logger = init_logger()
    eventLog(logger,currenttime + ' Start python script to install the installers')
    status = main(sys.argv[1:])
    sys.exit(status)
