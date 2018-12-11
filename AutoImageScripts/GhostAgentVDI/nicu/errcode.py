'''
This module show all the error code in SAST software.
'''
import os

__all__ = [
    'strerror'
]

# dict providing a mapping from a numberic error code to an error string name
errcode = {}

# dict providing a mapping from a numberic error code to an error message
errstr = {}

def strerror(errno):
    """To translate a numeric error code to an error message"""
    s = errstr.get(errno, None)
    if s is None:
        s = os.strerror(errno)
    return s


def _err(errno, name, message):
    """add an error code.

    Args:
          errno (int): the numeric error code
          name (str): the string name for this error
          message (str): the detailed error message for this error

    """
    errcode[name] = errno
    globals()[name] = errno
    __all__.append(name)
    errstr[errno] = message

#
# for common error, I would suggest start the error name with ER_
# for module specific error, start it with ER_[MODULE_NAME]_
#
# 0-99 common error
_err(0, 'ER_SUCCESS', 'Function or command execute success')
_err(1, 'ER_TIMEOUT', 'Funciton or command execute timeout')
_err(2, 'ER_EXCEPTION', 'Exception happened during calling a command or \
function')
_err(3, 'ER_INVALID_PARAMETER_NUMBER', 'Invalid number of the parameters')
_err(4, 'ER_INVALID_PARAMETER', 'Invalid parameters')
_err(5, 'ER_MISCELLANEOUS_FAILURE', 'Miscellaneous failure')
_err(6, 'ER_TERMINATE_THREAD_TIMEOUT', 'Failed to terminate thread due to \
time out')
_err(7, 'ER_NO_SUCH_THREAD', 'Failed to execute because no such thread or \
the thread got terminated')
_err(8, 'ER_FILE_NONEXIST', 'File is nonexistent.')
_err(9, 'ER_FILE_READ_ERROR', 'Failed to read file.')
_err(10, 'ER_FILE_WRITE_ERROR', 'Failed to write file.')
_err(11, 'ER_FILE_DATA_WRONG', 'Invalid file content.')
_err(12, 'ER_ACCOUNT_ERROR', 'Invalid account or password.')
_err(13, 'ER_FAILED', 'Function or command execute failed.')

# 100-199 nicu error
_err(100, 'ER_DB_CONNECT_ERROR', 'The database operation or connection \
throws exception')
_err(101, 'ER_DB_WRONG_DATA', 'Can not get correct data from the database')
_err(102, 'ER_DB_CDE_ERROR', 'CommonDatabaseException thrown')
_err(103, 'ER_DB_COMMON_ERROR', 'Unexpected Exception thrown')
_err(104, 'ER_MISC_GET_VERSION', 'Can not get version information.')

# 200-299 VMWareAgent error
_err(200, 'ER_VM_VMTOOL_UNEXPECTED_EXCEPTION', 'The 3rd party virtual \
machine management tool throws unexpected exception.')
_err(201, 'ER_VM_VMTOOL_CRASH', 'The 3rd party virtual machine management \
tool is crashed or report unexpected error')
_err(202, 'ER_VM_IN_USED', 'The specific virtual machine had been checked \
out or in used')
_err(203, 'ER_VM_INVALID_IMAGE', 'Can not access the virtual machine image \
template or the template is not valid')
_err(204, 'ER_VM_INVALID_DESTINATION', 'The archive destination of the \
virtual machine image is not valid')
_err(205, 'ER_VM_INVALID_GHOST_SERVER', 'The current ghost server is not \
a virtual machine based server')
_err(206, 'ER_VM_CONF_EXCEPTION', 'Exception when parsing the configuration \
file (.ini)')
_err(207, 'ER_VM_CONF_GENERATE_FAILED', 'Failed to generate ghost \
configuration file (script.ini)')
_err(208, 'ER_VM_LOGIN_INFO_ERROR', 'Failed to get the login information of \
the virtual image')
_err(209, 'ER_VM_VER_INFO_ERROR', 'Exception happened during reading version \
information')
_err(210, 'ER_VM_INSTALL_ERROR', 'Fatal error during installing software')

# 300-399 GhostAgent error
_err(300, 'ER_GA_HANDLE_EXCEPTION',
     'Unexpected exception thrown during request handling.')
_err(301, 'ER_GA_PF_UNSUPPORT',
     'The operation does not apply to current platform.')
_err(302, 'ER_GA_GEN_CONF_EXCEPTION',
     'Failed to generate configuration.')
_err(303, 'ER_GA_VM_TYPE_UNSUPPORT', 'Current vmware tool is not support.')
_err(304, 'ER_GA_VM_CMD_FAILED',
     'Failed to execute command in vmware client machine.')
_err(305, 'ER_GA_LOCK_ACQUIRE_EXCEPTION', 'Failed to acquire lock.')
_err(306, 'ER_GA_LOCK_RELEASE_EXCEPTION', 'Failed to release lock.')




# 400-499