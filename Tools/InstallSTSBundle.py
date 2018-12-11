"""
Description : Python script is mainly intented to install the latest CDS Bundle.
Autor   : Yang
Date    : 8/14
"""
from __future__ import with_statement
import os
import re
import sys
import time
import zipfile
import contextlib
import logging
import logging.handlers


def fetch_bundle(rootdir):
    '''
    Parse the folder and return the latest bundle by the creation time
    '''
    bundlefolders = os.listdir(rootdir)
    bundlefolders.sort(key = lambda fn : os.path.getctime(rootdir + os.sep + fn) if os.path.isdir(rootdir + os.sep + fn) else 0)
    latest_folder = os.path.join(rootdir,bundlefolders[-1])
    for latest_bundle in os.listdir(latest_folder):
        if os.path.basename(latest_bundle).startswith('STS') and os.path.isfile(os.path.join(latest_folder,latest_bundle)):
            latest_bundle = os.path.join(latest_folder,latest_bundle)
            print(r'[' + time.ctime() + r'][INFO]: Executing:"' + latest_bundle + r'"')
            return latest_bundle

def init_logger(name):
    '''
    Initialize the logger setting
    '''
    logger = logging.getLogger(name)
    logging.raiseExceptions = False
    logger.setLevel(logging.DEBUG)
    log_path = os.path.abspath(r"C:\Incoming")
    if not os.path.exists(log_path):
        os.makedirs(log_path)
    log_file_name = (log_path + os.sep + "parserExcute" + "_" + time.strftime("%Y%m%d", time.localtime()) + ".log")
    log_file_handler = logging.handlers.TimedRotatingFileHandler(log_file_name, when='D', interval=3, backupCount=10)
    log_file_handler.setLevel(logging.DEBUG)
    logger.addHandler(log_file_handler)
    return logger

def event_log(logger, event):
    logger.debug('[' + time.ctime() + ']:' + event)

def unzip_bundle_from_server(src, dest):
    '''
    Unzip the STS bundle from the server to the version selector repository
    '''
    event_log(logger, '--------Waiting for unzipping the %s---------' % src)
    zip = zipfile.ZipFile(src,'r')
    for file in zip.namelist():
        zip.extract(file,dest)
    zip.close()
    event_log(logger, '--------Unzipping the %s zip file Done!--------' % src)
    return True

def write_installer_info(log,info):
    '''
    Delete the py script itself inof
    Append the installer info to the script log for the bg image
    '''
    try:
        with open(log,'r') as fn_r:
            lines = fn_r.readlines()
            lines.append(r'[' + time.ctime() + r'][INFO]: Executing:"' + info + '\n')
        with open(log,'w') as fn_w:
            #write the fake installer info log for bg script
            for line in lines:
                if "InstallSTSBundle" in line:
                    continue
                fn_w.write(line)
    except Exception as err:
        event_log(logger,currenttime + str(err))

def main():
    '''
    Execute the action to unzip the bundle and install it with the version selector.
    '''
    sts_bundle = fetch_bundle(bundledailyfolder)
    event_log(logger, 'LatestBundle : %s' % sts_bundle)
    write_installer_info(script_log,sts_bundle)
    unzip_bundle_from_server(sts_bundle,verselectorrepo)
    #Install STS Bundle
    command = r'Start /wait "" "C:\\Program Files\\National Instruments\\STS Version Selector\\VersionSelector.exe" /activate "NISTS18.0.0" /r:n'
    event_log(logger, 'Execute the command : %s' % command)
    ret = os.system(command)
    #Delete the MSW from the starup folder
    command = r'Del "%AppData%\Microsoft\Windows\Start Menu\Programs\Startup\NI STS Maintenance Software.lnk" /F /S /Q'
    event_log(logger, 'Execute the command : %s' % command)
    ret = os.system(command)
    time.sleep(2)
    return ret

if __name__ == '__main__':
    '''
    Execute the script with parameters and return the result
    '''
    status = 0
    currenttime = time.strftime("%a, %d %b %Y %H:%M:%S +0800", time.gmtime())
    bundledailyfolder = r"\\cn-sha-argo\NISoftwarePrerelease\STS Software\Bundle\18.0\unverified"
    verselectorrepo = r"C:\\ProgramData\\National Instruments\\STS Version Selector\\STSSoftwareRepository"
    script_log = r"C:\Incoming\scriptOut.log"
    logger = init_logger(__name__)
    event_log(logger,currenttime + '****************************************************')
    event_log(logger,currenttime + ' Start python script to install the latest STS Bundle')
    sys.exit(main())