"""
Description : Python script intents to finding the latest/verified installer from the XML file which the user defined.
Finnally, it will write the result to the $workspace/installer.log
Autor   : Yang
Date    : 6/15

"""

import os
import re
import sys
import time
import argparse
import xml.etree.ElementTree as xmlTree
import logging
import logging.handlers
from collections import OrderedDict

currenttime = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
installer_file_name = r""

def initialize_command_line(argv):
    '''
    Parse the arguments that user provided
    '''
    parser = argparse.ArgumentParser(usage='LatestInstaller.py  -f [...xml path] -m [...product modules]',
                                    description='''The Script is used to parse the path of the latest/specified installer.
                                    Requires:
                                    f   THE PATH OF XML FILE INCLUDING THE DEFINITION OF SOFTWARE STACK
                                    Optional:
                                    m   THE SPECIFIED PRODUCT MODULE TO INSTALL''',
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
    required_opts = parser.add_argument_group(title='REQUIRED', description='These parameters are required')
    required_opts.add_argument('-f','--file', action='store', required=True, help='''The XML file which contain the defintion of the serarch path''')
    optional_opts = parser.add_argument_group(title='OPTIONAL', description='These parameters are optional')
    optional_opts.add_argument('-m','--module', action='store', nargs='+', default="", help='''The modules to install''')
    settings = parser.parse_args(argv)
    return settings

def validate_command_line_options(settings):
    '''
    If there exist error while validate the command, return true
    '''
    if os.path.exists(settings.file):
        (shortname, extension) = os.path.splitext(os.path.abspath(settings.file))
        if extension != ".xml":
            raise Exception("Please specify the XML path including the installer material")
        return True
    else:
        raise Exception("Please specify the XML path including the installer material")

def fetch_installer(installers, paths, pattern):
    '''
    Parse the folder and return the latest installer folder by the creation time
    '''
    def search_setup(setups, directory, name=["setup.exe","NI_STS_Auxiliary_RF_Tools.exe"]):
        for item in os.listdir(directory):
            item_path = os.path.join(directory,item)
            if os.path.isdir(item_path) and not re.search("Distributions|runtime", os.path.basename(item_path)):
                search_setup(setups,item_path)
            elif os.path.isfile(item_path):
                if item in name:
                    setups.append(item_path)
    if pattern.lower() == "special":
        for path in paths:
            search_setup(installers, path)
    else:
        for path in paths:             
            dirnames = os.listdir(path)
            dirnames.sort(key = lambda fn : os.path.getctime(path + os.sep + fn) if os.path.isdir(path + os.sep + fn) else 0)
            latest_folder = os.path.join(path,dirnames[-1])
            search_setup(installers,latest_folder)
    return installers

def write_path_to_file(installers, installer_file):
    '''
    write the parsed result to the file
    '''
    try:
        with open(installer_file, 'w') as result:
            for line in installers:
                result.write(line + '\n')
        return 0
    except IOError as error:
        raise error

def init_logger():
    '''
    Initialize the logger setting
    '''
    logger = logging.getLogger()
    logging.raiseExceptions = False
    logger.setLevel(logging.DEBUG)
    log_file_name = (r"c:" + os.sep + "parserExcute" + "_" + time.strftime("%Y%m%d", time.localtime()) + ".log")
    log_file_handler = logging.handlers.TimedRotatingFileHandler(log_file_name, when='D', interval=3, backupCount=10)
    log_file_handler.setLevel(logging.DEBUG)
    logger.addHandler(log_file_handler)
    return logger

def event_log(logger, event):
    '''
    Log the event
    '''
    logger.debug('[' + time.ctime() + ']:' + event)

def fetch_path(xml, hostname, modules):
    '''
    Read the root path of the software stack from the XML file user defined on running host
    return : a dictionary including product modules and installer root paths, searching pattern
    '''
    pattern = ""
    pathdict = OrderedDict()
    path_dict = OrderedDict()

    tree = xmlTree.parse(xml)
    root = tree.getroot()
    for swstacks in root.iterfind(hostname):
            for stack in swstacks.iterfind("*"): 
                if stack.get("required").lower() == "true":
                    pattern = stack.tag
                    for sw in stack:
                        pathdict[sw.tag] = sw.text
                    break
    if modules:
        for mod in modules:
            if mod in pathdict.keys():
                path_dict[mod] = pathdict[mod]
            else:
                raise "Invalid Module"
        pathdict.clear()
        pathdict = path_dict 
    return pathdict, pattern
        
def main(argv):
    settings = initialize_command_line(argv)
    event_log(logger,str(settings))
    try:
        validate_command_line_options(settings)
    except Exception as error:
        print("ERROR : %s" % error)
    (pathdict, pattern) = fetch_path(settings.file,tester,settings.module)
    fetch_installer(installers,pathdict.values(),pattern)
    write_path_to_file(installers,installer_file_name)
    return 0

if __name__ == '__main__':
    '''
    Execute the script with parameters and return the result
    '''
    status = 0
    trunk = ""
    installers = []
    tester = os.environ['computername']
    installer_file_name = (r"C:" + os.sep + "installer.log")
    logger = init_logger()
    event_log(logger,currenttime + ' Start python script to parse the latest installer path')
    status = main(sys.argv[1:])
    sys.exit(status)