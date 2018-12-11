"""This module contains methods for path related operations
"""

import os
import logging

logger = logging.getLogger(__name__)

__all__ = [
    "list_dir", "get_latest_installer", "get_folder_size"
]

def list_dir(directory, mode="mtime"):
    """Get all subdirectories under given directory, sorted by ctime or mtime
    If mode is mtime, it will be sorted by mtime (this is the default)
    Otherwise it will be sorted by ctime
    Return value will be in format[(ctime/mtime, full_path), ...]
    If the given directory doesn't exist, return an empty list.
    """
    directories = []

    #if the given directory doesn't exist, return an empty list.
    if not os.path.isdir(directory):
        return directories

    if mode == "mtime":
        directories = [(os.path.getmtime(
                os.path.join(directory, tmp)),
              os.path.join(directory, tmp))
                for tmp in os.listdir(directory)
                    if (not tmp.startswith(".") and
                        os.path.isdir(os.path.join(directory, tmp)))
            ]
    else:
        directories = [(os.path.getctime(
                os.path.join(directory, tmp)),
              os.path.join(directory, tmp))
                for tmp in os.listdir(directory)
                    if (not tmp.startswith(".") and
                        os.path.isdir(os.path.join(directory, tmp)))
            ]
    directories.sort()
    directories.reverse()
    return directories

def get_latest_installer(base_path):
    """Get the latest installer folder under the given base path
    If the given base_path could not be found, it will return None
    """
    latest_installer = ""
    if os.path.isdir(base_path):
        try:
            folder_list = list_dir(base_path)
            latest_installer = folder_list[0][1]
            path = os.path.join(base_path, latest_installer)
            return path
        except:
            logger.error(
                "Could not find out the latest installer from <%s>." %
                base_path)
            return None
    else:
        logger.error("%s is an invalid path." % base_path)
        return None

def get_folder_size(folder):
    """Returns the total size of a given folder,
    If the give folder doesn't exist, return as -1"""
    if not os.path.isdir(folder):
        return -1

    total_size = os.path.getsize(folder)
    for item in os.listdir(folder):
        itempath = os.path.join(folder, item)
        if os.path.isfile(itempath):
            total_size += os.path.getsize(itempath)
        elif os.path.isdir(itempath):
            total_size += get_folder_size(itempath)
    return total_size
