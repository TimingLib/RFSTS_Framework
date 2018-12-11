"""
Description : Python script intents to finding the latest/specified CDS Bundle.\
Finnally, it will write the result to the $workspace/installer.log
Autor   : Yang
Date    : 7/5
"""

import os
import sys
import time
import argparse
import logging.handlers

currenttime = time.strftime("%a, %d %b %Y %H:%M:%S +0800", time.gmtime())
bundledailyfolder = r"\\argo\NISoftwarePrerelease\STS Software\Bundle\18.0\unverified"

def initialize_command_line(argv):
    '''
    Parse the arguments that user provided
    '''
    parser = argparse.ArgumentParser(usage='ListBundlePath.py -s [bundle version]',
                                    description='''The Script is used to parse the path of the latest/specified bundle.
                                    Optional:
                                    s   SPECIFIED THE SOFTWARE BUNDLE VERSION (e.g. 18.0.0.0)''',
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
    optional_opts = parser.add_argument_group(title='OPTIONAL', description='These parameters are optional')
    optional_opts.add_argument('-s','--spec', action='store', help='''List the bundle with the specified version''')
    settings = parser.parse_args(argv)
    return settings

def fetch_bundle(rootdir,version):
    '''
    Parse the folder and return the latest bundle by the creation time
    '''
          
    bundlefolders = os.listdir(rootdir)
    bundlefolders.sort(key = lambda fn : os.path.getctime(rootdir + os.sep + fn) if os.path.isdir(rootdir + os.sep + fn) else 0)

    if version :
        for bundlefolder in bundlefolders:
            if version in bundlefolder:
                latest_folder = os.path.join(rootdir,bundlefolder)
    else: 
        latest_folder = os.path.join(rootdir,bundlefolders[-1])
    for latest_bundle in os.scandir(latest_folder):
        if latest_bundle.name.startswith('STS') and latest_bundle.is_file():
            latest_bundle = os.path.join(latest_folder,latest_bundle.name)
            print(latest_bundle)
            return latest_bundle

def write_path_to_file(bundle, installer_file):
    '''
    write the result to the file
    '''
    try:
        with open(installer_file, 'w+') as result:
            result.write(str(bundle) + '\n')
    except IOError as error:
        raise error

def init_logger():
    '''
    Initialize the logger setting
    '''
    logger = logging.getLogger()
    logging.raiseExceptions = False
    logger.setLevel(logging.DEBUG)
    log_file_name = (r"C:" + os.sep + "parserExcute" + "_" + time.strftime("%Y%m%d", time.localtime()) + ".log")
    log_file_handler = logging.handlers.TimedRotatingFileHandler(log_file_name, when='D', interval=3, backupCount=10)
    log_file_handler.setLevel(logging.DEBUG)
    logger.addHandler(log_file_handler)
    return logger

def event_log(logger, event):
    logger.debug('[' + time.ctime() + ']:' + event)
        
def main(argv):
    settings = initialize_command_line(argv)
    event_log(logger,str(settings))
    write_path_to_file(fetch_bundle(bundledailyfolder,settings.spec),installer_file_name)
    return 0

if __name__ == '__main__':
    '''
    Execute the script with parameters and return the result
    '''
    status = 0
    installer_file_name = (r"C:" + os.sep + "installer.log")
    logger = init_logger()
    event_log(logger,currenttime + ' Start python script to parse the latest installer path')
    status = main(sys.argv[1:])
    sys.exit(status)