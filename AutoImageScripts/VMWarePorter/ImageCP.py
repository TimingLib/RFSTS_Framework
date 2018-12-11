"""
Date:10/16/2018
Description:
This script aims to copy the local VM to server

How to Run:
        *) run it by "python ImageCP.py -h" to see help
"""

import os
import sys
import errno
import stat
import datetime
import time
import optparse
import glob
import traceback
import shutil
import re
import logging
import logging.handlers

LOG_FILE = os.path.join(os.path.dirname(__file__),"ImageGC/ImageCP.log")
try:
    os.makedirs(os.path.dirname(LOG_FILE))
except:
    pass
logger = logging.getLogger(__name__)

dateSuffix=time.strftime("%y_%m_%d_", time.gmtime())

def init_log():
    '''
    initialize the log
    '''
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)-15s:\
%(levelname)-5s:%(filename)s:L%(lineno)-4s:%(message)s')
    logging.addLevelName(logging.WARNING, "WARN")
    formatter = logging.Formatter('%(asctime)-15s:%(levelname)-5s:\
%(filename)s:L%(lineno)-4s:%(message)s')
    fh = logging.handlers.TimedRotatingFileHandler(LOG_FILE,
                                                   when='D',
                                                   interval=3,
                                                   backupCount=10)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    logger.propagate = False


def handler_access_error(func, path, exc):
    '''
    This function will be invoked when the file is readonly which
    can not be deleted.
    '''
    excvalue = exc[1]
    if excvalue.errno == errno.EACCES:
        os.chmod(path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        func(path)
    else:
        raise excvalue  


def copydirs_and_contents(source, destination):
    '''
    Copy the generated VM
    '''
    logger.debug("Copying %s To %s", source, destination)
    try:
        if os.path.exists(destination):
            shutil.rmtree(destination,
                      ignore_errors=False,
                      onerror=handler_access_error)
        shutil.copytree(source, destination)
    except Exception as e:
        logger.error(e)
        return
    logger.info('Copied Successfully')
    return


class CopyVM(object):
    '''
    Copy the vm image to cn-sha-rdfs01 from local disk.
    '''
    def __init__(self, *img_folders):
        super(CopyVM, self).__init__()
        self.roots = img_folders

    def run(self):
        '''
        Copy the vm image to the corresponding server folder.
        '''
        global options
        for root in self.roots:
            if "CDS" in root:
                _root_daily_build = r"\\argo\NISoftwarePrerelease\STS Software\Distributions\18.0.0\STSCoreDevelopment\unverified"
            elif "BUNDLE" in root:
                _root_daily_build = r"\\argo\NISoftwarePrerelease\STS Software\Bundle\18.0\unverified"
            source = root
            version = get_latest_version(_root_daily_build)
            _temp_destination = os.path.join(os.path.dirname(root), dateSuffix + version)
            destination = _temp_destination.replace(r"C:\Users\RFSTS\Desktop", _root_server)
            if not (options and options.test):
                logger.info("Copying ...")
                copydirs_and_contents(source, destination)
        return


def get_latest_version(rootpath):
    files = glob.glob(os.path.join(rootpath, "*"))
    latestFile = max(files,key=os.path.getctime)
    version = os.path.basename(latestFile)
    return version


def vm_folders(*roots):
    """
    this is a generator
    """
    for root in roots:
        for r, dirs, files in os.walk(root):
            try:
                x = glob.iglob(os.path.join(r, "*.vmdk"))
                x.next()
                yield r
            except StopIteration:
                pass


def do_cml_process():
    '''
    process the parameters in the command line.
    '''
    useage = "ImageCP.py [--longevity=LONGEVITY|-l LONGEVITY] \
[--local_longevity=LOCAL_LONGEVITY|-L LOCAL_LONGEVITY] [--test|-t] [-h|--help]"
    parser = optparse.OptionParser(useage)
    parser.add_option("-l", "--longevity",
                      action="store",
                      type="int",
                      default="7",  # keep recent foders in one week
                      dest="longevity",
                      help="(optional) keep folders no greater than n days.")
    parser.add_option("-L", "--local_longevity",
                      action="store",
                      type="int",
                      default="30",
                      dest="local_longevity",
                      help="(optional) keep local folders no greater than n \
days")
    parser.add_option("-t", "--test",
                      action="store_true",
                      default=False,
                      dest="test",
                      help="(optional) just print which folders are expired, \
but no deletion performed.")
    parser.add_option("-m", "--minimum",
                      action="store",
                      type="int",
                      default="3",
                      dest="minimum",
                      help="(optional) keep at least 3 images for one type")

    options, args = parser.parse_args(sys.argv)
    return options, args, parser

options = None
parser = None

if __name__ == "__main__":
    # initialize the log
    init_log()

    try:
        options, args,  parser = do_cml_process()
        _root_server = r"\\cn-sha-rdfs01\RF STS"
        _root_localvm = r"C:\Users\RFSTS\Desktop\RF-STS-VM\DailyVM"
        logger.info("options: %s, args: %s", options, args)
        folders = [folder for folder in vm_folders(_root_localvm)]
        copyvm = CopyVM(*folders)
        copyvm.run()
    except (SystemExit,  KeyboardInterrupt) as e:
        logger.info('byebye.')
    except Exception, e:
        logger.error(traceback.format_exc())
exit(0)