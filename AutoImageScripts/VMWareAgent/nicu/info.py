'''This module contains methods for information of version, run path, status
'''
import os
import sys

__all__ = [
    "get_info"
]


def get_info():
    '''Get information: version, run path, status
    '''
    path = sys.path[0]
    status = ''
    version = ''
    retval = 0
    if os.path.isfile(path):
        run_path = os.path.dirname(path)
    else:
        run_path = path
    version_path = os.path.join(run_path, 'version.txt')
    if (not os.path.isfile(version_path)):
        status = 'cannot find version.txt'
        retval = 402
    else:
        try:
            with open(version_path) as fp:
                version = fp.read()
        except Exception, error:
            status = 'error in reading version.txt : %s' % error
            retval = 402

    data = version + ';' + run_path + ';' + status
    return [retval, data]
