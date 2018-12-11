"""
Description :   The script is a decorator of the build project. It intends to pass some helpfull information for the user as variables.
Autor   :   Yang
Date    :   6/7
"""

import  re
import  os
import  sys
import  platform
import  argparse


def initialize_command_line(argv):
    '''
    Parse the arguments that user provided
    '''
    parser = argparse.ArgumentParser(usage='Decpratpr.py    -f [Destination]',
                                    description='''The Script is used to pass the variables through the different build projects.
                                    Optional:
                                    f   THE PATH OF FILE STORED THE ENVRIOMENT VARIABLES''',
                                    formatter_class=argparse.RawDescriptionHelpFormatter)
    optional_opts = parser.add_argument_group(title='OPTIONAL', description='These parameters are optional')
    optional_opts.add_argument('-f','--file', action='store', default=r"C:\jenkins\workspace\var.properties", help='''The file used to store the envrioment variables''')
    settings = parser.parse_args(argv)
    return settings

'''
def get_system_encoding():
    """
    The encoding of the default system locale but falls back to the given
    fallback encoding if the encoding is unsupported by python or could
    not be determined.
    """

    try:
        encoding = locale.getdefaultlocale()[1] or 'ascii'
        codecs.lookup(encoding)
    except Exception:
        encoding = 'ascii'
        return encoding
'''

def win_info():
    """
    Fetch the system information 
    """
    prog  = re.compile(r'\w+\-\d+')
    system = prog.match(platform.platform()).group().upper()
    version = platform.version().upper()
    return system,version


def get_installer_info(insfile):
    """
    Fetch the installers information on the Tester
    """
    try:
        with open(insfile,'r') as sn:
            content = sn.read().splitlines()
        return content
    except IOError as error:
        raise error


def set_variables_jenkins(vars,profile):
    """
    Write the variables to the properties file in jenkins workspace
    """
    installer_info = get_installer_info(insfile)
    i = 0
    for installer in installer_info:
        module = "INSTALLER" + str(i)
        vars[module] = installer.replace(os.sep,r"\\")
        i += 1
    (vars['SYSTEMINFO'],vars['VERSIONINFO']) = win_info()
    try:
        (os.path.splitext(profile) == ".properties")
    except Exception:
        print("ERROR    :   Please declare the variables with the strict file format (**.properties)")
        return 110
    with open(profile,'a+') as fn:
        for var in vars.keys():
            con = var + r'=' + vars[var]
            fn.write(con + "\n")
    return 0


if __name__ == '__main__':
    variables = {}
    insfile = r"C:\installer.log"
    settings = initialize_command_line(sys.argv[1:])
    status = set_variables_jenkins(variables,settings.file)
    exit(status)