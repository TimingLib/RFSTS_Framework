"""
This script is mainly intended to install package from
the given repo path or package path
"""

import os
import re
import sys
import time
import urllib
import urllib2
import _winreg
import urlparse
import optparse
import xml.etree.cElementTree
import nicu.version as version
from nicu.path import get_latest_installer

WINERRORS = {
    'ERROR_FILE_NOT_FOUND': 2L,
    'ERROR_PATH_NOT_FOUND': 3L,
    'ERROR_INVALID_PARAMETER': 87L,
    'INET_E_INVALID_URL': 0x80072EE4L
}
NIPackageManagerProcessName = "NIPackageManager.exe"
NIPackageManagerInstallerDir = r"\\cn-sha-argo\RnD\perforceExports\AST\PackageManagement\components\nipkgui\export"
NIPackageManagerDefaultInstallerPath = \
    r"\\nirvana\perforceExports\AST\PackageManagement\components\nipkgui\export\17.0\17.0.0a8\targets\win64U\x64\msvc-14.0\release\Install.exe"

ignoredErrCode = [-125071]
'''''
Refer to nipkg return code for more details:
    Perforce://AST/PackageManagement/components/shared/trunk/16.6/templates/errors.yml
+-------------------------------------------------+
|         Code        |          Mnemonic         |
+=================================================+
|       -125071       |       reboot_needed       |
+-------------------------------------------------+
'''''


def execSysCmd(command, delay=0):
    ret = os.system(command)
    time.sleep(delay)
    return ret if ret not in ignoredErrCode else 0


def get_latest_nipkg(base_path):
    """Get the latest nipkg folder under the given base path
    If the given base_path could not be found, it will return None
    """
    latest_nipkg = "1.0.0.0-0+d0"
    if 'http://' in base_path or 'https://' in base_path:
        try:
            base_path = base_path if base_path.endswith('/') else (base_path + '/')
            matchedURL = [latest_nipkg]
            dir_pat = re.compile(r'<A HREF="(.+?)">')
            ver_pat = re.compile(r'(\d+)\.(\d+)\.(\d+).(\d+)-0\+([dabf])(\d+)')
            req = urllib2.Request(base_path)
            content = urllib2.urlopen(req).read()
            for line in content.split('\r\n'):
                for item in dir_pat.finditer(line):
                    if ver_pat.search(item.group(1)) is not None and \
                        version.PackageVersion(os.path.basename(item.group(1)[:-1])) > version.PackageVersion(matchedURL[0]):
                        matchedURL[0] = os.path.basename(item.group(1)[:-1])
            latest_nipkg = urlparse.urljoin(base_path, matchedURL[0] + '/')
        except:
            return None
    else:
        if os.path.isdir(base_path):
            try:
                base_path = base_path[:-1] if base_path.endswith('\\') else base_path
                for dir in os.listdir(base_path):
                    if os.path.isdir(os.path.join(base_path, dir)) \
                        and version.PackageVersion(dir) > version.PackageVersion(latest_nipkg):
                        latest_nipkg = dir
                latest_nipkg = os.path.join(base_path, latest_nipkg)
            except:
                return None
        else:
            return None
    return latest_nipkg


def storeURLContent(urlPath, localPath):
    request = urllib2.Request(urlPath)
    urllib2.urlopen(request)
    if not os.path.exists(os.path.dirname(localPath)):
        os.makedirs(os.path.dirname(localPath))
    urllib.urlretrieve(urlPath, localPath)


def parseInputCmdParams(argv):
    parser = optparse.OptionParser(usage='installNextGenProduct.py [options]',
                                    formatter=optparse.TitledHelpFormatter(width=75))
    parser.add_option("-l", "--latest", action="store_true", dest="findlatest", default=False)
    parser.add_option("-p", "--path", action="store", type='string')
    parser.add_option("-a", "--addRepoOnly", action="store_true", dest="addRepoOnly", default=False)
    settings, args = parser.parse_args(argv)
    return settings


def getTopLevelPackages(repoPath):
    """
    Retrieve the top level package names from the given repo path
    """
    isUrlPath = False
    topPkgs = []

    if 'http://' in repoPath or 'https://' in repoPath:
        isUrlPath = True
        repoPath = repoPath if repoPath.endswith('/') else (repoPath + '/')
        workingDir = os.path.join(os.getcwd(), 'URLTemp')
        if not os.path.exists(workingDir):
            os.mkdir(workingDir)
        try:
            ### Check if the URL is valid
            storeURLContent(urlparse.urljoin(repoPath, 'meta-data/Feed_Tree.xml'),
                                             os.path.join(workingDir, 'meta-data', 'Feed_Tree.xml'))
            repoPath = workingDir
        except (IOError, urllib.ContentTooShortError, urllib2.URLError):
            raise Exception('INET_E_INVALID_URL')

    if os.path.exists(os.path.join(repoPath, 'meta-data', 'Feed_Tree.xml')):
        coreFilePath = os.path.join(repoPath, 'meta-data', 'Feed_Tree.xml')
    else:
        raise Exception('ERROR_FILE_NOT_FOUND')

    tree = xml.etree.ElementTree.parse(coreFilePath)
    for child in tree.getroot().findall('package'):
        topPkgs.append(child.attrib['name'])
    if isUrlPath is True:
        os.remove(coreFilePath)
    return topPkgs


def getSetupPath(directory):
    for r, dir, fileLst in os.walk(directory):
        for f in fileLst:
            if f.lower() == "setup.exe" or f.lower() == "install.exe":
                relativePath = os.path.relpath(r, directory)
                if "win64U" in relativePath and "msvc" in relativePath:
                    return os.path.join(relativePath, f)
    else:
        raise Exception()


def installPackageManager(installerDir):
    ### define ERROR_FILE_NOT_FOUND 2L in WinError.h
    ### The system cannot find the file specified.

    ret_val = 0
    latestMajorVer = get_latest_installer(installerDir)
    if not latestMajorVer:
        return WINERRORS['ERROR_FILE_NOT_FOUND']
    else:
        latestMinorVer = get_latest_installer(latestMajorVer)
        if not latestMinorVer:
            return WINERRORS['ERROR_FILE_NOT_FOUND']

        try:
            latestPath = os.path.join(latestMinorVer, getSetupPath(latestMinorVer))
            ret_val = execSysCmd("%s /Q" % latestPath, 60)
        except Exception:
            ret_val = execSysCmd("%s /Q" % NIPackageManagerDefaultInstallerPath, 60)
        finally:
            execSysCmd("TASKKILL /F /IM %s /T" % NIPackageManagerProcessName)
            return ret_val


def installProduct(productPath, addRepoOnly=False):
    """
    Install the specified product
    If the way of 'Custom Package' is specified, it will install with the given package directly
    if the way of 'Custom Repo' or 'NI Hub', it will parse the top level package at first
    """
    if productPath is None:
        return WINERRORS['ERROR_PATH_NOT_FOUND']

    cmd_list = []
    ret_val = 0
    productPath = productPath.strip()
    try:
        nipkg_regkey = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,
                                       r'SOFTWARE\National Instruments\NI Package Manager\CurrentVersion')
    except:
        ret_val = installPackageManager(NIPackageManagerInstallerDir)
        if ret_val:
            return ret_val
        else:
            nipkg_regkey = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE,
                                           r'SOFTWARE\National Instruments\NI Package Manager\CurrentVersion')

    nipkg_path = '"' + os.path.join(_winreg.QueryValueEx(nipkg_regkey, 'Path')[0], 'nipkg.exe') + '"'
    install_flag = r'install --accept-eulas -y -v'

    try:
        if productPath.endswith('.nipkg'):
            # Install package directly
            cmd_line = ' '.join([nipkg_path, install_flag, productPath])
            cmd_list.append(cmd_line)
        else:
            # Add repo
            cmd_line = ' '.join([nipkg_path, 'repo-add', productPath])
            cmd_list.append(cmd_line)
            # Update package
            cmd_line = ' '.join([nipkg_path, 'update'])
            cmd_list.append(cmd_line)
            if not addRepoOnly:
                # # Install package
                for topPkg in getTopLevelPackages(productPath):
                    cmd_line = ' '.join([nipkg_path, install_flag, topPkg])
                    cmd_list.append(cmd_line)

        for cmd in cmd_list:
            ret_val = execSysCmd(cmd)
            if ret_val:
                break
    except Exception, errinfo:
        ret_val = WINERRORS[errinfo.message]
    return ret_val


if __name__ == '__main__':
    """Install the NextGen product based on the given path (repo/package installed)"""
    if len(sys.argv) > 5 or len(sys.argv) < 3:
        ### define ERROR_INVALID_PARAMETER 87L in WinError.h
        sys.exit(WINERRORS['ERROR_INVALID_PARAMETER'])

    settings = parseInputCmdParams(sys.argv)
    if settings.findlatest is False:
        productPath = settings.path.strip()
    else:
        productPath = get_latest_nipkg(settings.path.strip())

    sys.exit(installProduct(productPath, settings.addRepoOnly))
