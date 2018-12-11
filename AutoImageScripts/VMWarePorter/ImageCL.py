"""
Date:10/15/2018
Description:
This script aims to solve problem of cleaning up VM images
under DailyVM. Haochi Wu)

How it works:

        \\cn-sha-rdfs01\RF STS\RF-STS-VM\DailyVM

        The created image will be deleted when the
        living time exceeds 7 days (change it by
        providing --longevity=N for other options)

How to Run:
        *) run it by "python ImageCA.py -h" to see help
"""

import os
import sys
import errno
import stat
import datetime
import traceback
import time
import optparse
import glob
import shutil
import re
import logging
import logging.handlers

LOG_FILE = os.path.join(os.path.dirname(__file__),"ImageGC/ImageCA.log")
try:
    os.makedirs(os.path.dirname(LOG_FILE))
except:
    pass
logger = logging.getLogger(__name__)


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
        
def how_old_are_you(folder_name):  # may throw exception
    """
    compute the difference between the last modified time and now,
    returning in datetime.timedelta
    """
    delta = None
    newest = os.stat(folder_name).st_mtime
    if os.path.isdir(folder_name):
        for r, d, f in os.walk(folder_name):
            if f:
                mtimes = (os.stat(os.path.join(r, _f)).st_mtime for _f in f)
                newest = max(newest, max(mtimes))
    delta = datetime.datetime.now() - datetime.datetime.fromtimestamp(newest)
    return delta


def time_expired(folder_name, longevity=7):
    """
    check if folder_name meets the deletion condtion
    """
    delta = how_old_are_you(folder_name)
    return (delta.days > longevity - 1)


def get_number_of_images(parent_dir):
    """
    Get the number of images under this folder.
    """
    vmx_list = glob.glob(os.path.join(parent_dir, "*\\*.vmx"))
    return len(vmx_list)


def removedirs_and_contents(folder):
    '''
    Remove the expired file
    '''
    logger.debug("Removing %s", folder)
    try:
        shutil.rmtree(folder,
                      ignore_errors=False,
                      onerror=handler_access_error)
        if os.path.exists(folder):
            os.removedirs(folder)
        else:
            os.removedirs(os.path.dirname(folder))
        logger.info('Deleted %s', folder)
    except Exception as e:
        logger.error(e)


class CleanUp(object):
    '''
    Clean up the expired vm image on cn-sha-rdfs01 and local disk.
    '''
    def __init__(self, *img_folders):
        super(CleanUp, self).__init__()
        self.roots = img_folders

    def run(self):
        '''
        Check the vm image is expired or not, delete the expired image.
        '''
        global options
        for root in self.roots:
            if not time_expired(root, options.longevity):
                logger.info('_not_ expired: %s', root)
                continue
            if get_number_of_images(os.path.dirname(root)) <= options.minimum:
                logger.info('reserved: %s', root)
                continue
            logger.info('Time expired: %s', root)
            if not (options and options.test):
                logger.info("Deleting ...")
                try:
                    removedirs_and_contents(root)
                except Exception, e:
                    logger.error("Fail to delete %s.", e)
                    return
                logger.info("Deleted.")
        return


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
    useage = "ImageGC.py [--longevity=LONGEVITY|-l LONGEVITY] \
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
        _root_dailyvm = r"\\cn-sha-rdfs01\RF STS\RF-STS-VM\DailyVM"
        logger.info("====options: %s, args: %s====", options, args)
        folders = [folder for folder in vm_folders(_root_dailyvm)]
        logger.info(folders)
        cleanup = CleanUp(*folders)
        cleanup.run()
    except (SystemExit,  KeyboardInterrupt) as e:
        logger.info('byebye.')
    except Exception, e:
        logger.error(traceback.format_exc())