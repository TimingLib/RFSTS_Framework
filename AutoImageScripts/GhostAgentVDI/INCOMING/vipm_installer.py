import sys
import os
import tempfile
import shutil
import re
import nicu.path as nicupath
import nicu.errcode as errcode
import stat
from optparse import OptionParser


def get_pkg_path(is_daily, src, suffix):
    """
    Get source package path.
    When is_daily is true, get the latest package folder under 'src' path.
    When is_daily it false, 'src' is the customed package path and return 'src' directly.
    """
    try:
        pkg_src = src
        if is_daily:
            # install type is installing latest package.
            pkg_src = nicupath.get_latest_installer(src)
            if pkg_src is None:
                print "[get_pkg_path]get latest package error: %s" % src
                raise
            if suffix != "":
                pkg_src = os.path.join(src, suffix)

        return pkg_src
    except Exception, e:
        print "[get_pkg_path]error: %s." % e
        raise


def install_package(src, dest, pk_key_name):
    temp_path = ""
    try:
        # Copy the vipm package
        temp_path = tempfile.mkdtemp(".temp", "vimpinstaller")
        print "try to copy the installer %s to %s" % (src, temp_path)
        # As the dest dir in shutil.copytree(src, dest) should not exist,
        # remove temp_path.
        os.rmdir(temp_path)
        shutil.copytree(src, temp_path)
        src = temp_path

        # Get vipm package name
        vip_name = get_vipm_name(src, pk_key_name)
        if vip_name is None:
            return errcode.ER_FAILED

        vip_path = os.path.join(src, vip_name)

        # User VIPackageHandler.exe to install package
        command = (r'\\cn-sha-rdfs01\AutoTestData\Software\VIPM_InstallTool\VIPackageHandler.exe -f "%s" "%s"'
                   % (vip_path, dest))
        if os.system(command) != 0:
            print "Execute command: '%s' fail." % command
            return errcode.ER_FAILED
        else:
            print "Execute command: '%s' successfully." % command
            return errcode.ER_SUCCESS
    except Exception, e:
        print "[install_package]error: %s." % e
        return errcode.ER_FAILED
    finally:
        if os.path.exists(temp_path):
            shutil.rmtree(temp_path, onerror=rm_readonly)


def rm_readonly(func, path, _):
    "Remove the readonly bit and retry the remove."
    os.chmod(path, stat.S_IWRITE)
    func(path)


def resolve_path(path):
    """
    Get the absolute path.
    path has two types:
    1. absolute path
    2. identifier. The supported identifier is labviewxxxxdir[64].
       xxxx refers to LabVIEW release version.
       It will return the LabVIEW installation path.
    """
    absolute_path = None
    if path.find("\\") != -1:
        # Absolute path
        return path

    result = re.match("^labview(\d{4})dir(\d*)$", path, re.I)
    if result is None:
        print "[resolve_path]error: invalid identifier %s" % path
        raise
    else:
        lv_version = result.group(1)
        if result.group(2) == "" or result.group(2) == "32":
            lv_bit = "32"
        elif result.group(2) == "64":
            lv_bit = "64"
        else:
            print ('[resolve_path] identifier %s error: If there is a number after "dir" ,'
                   'it should be 32 or 64.' % path)
            raise
        # If both of machine's OS and LabVIEW version are 32 bit or 64bit,
        # the default installation path of LabVIEW is:
        # C:\Program Files\National Instruments\LabVIEW xxxx
        # if machine's OS is 64 bit and LabVIEW version is 32 bit,
        # the default installation path of LabVIEW is:
        # C:\Program Files (x86)\National Instruments\LabVIEW xxxx
        os_bit = get_os_bit()
        if os_bit == 32:
            if lv_bit == "32":
                absolute_path = r"C:\Program Files\National Instruments\LabVIEW " + lv_version
        else:
            # OS is 64 bit
            if lv_bit == "32":
                absolute_path = r"C:\Program Files (x86)\National Instruments\LabVIEW " + lv_version
            elif lv_bit == "64":
                absolute_path = r"C:\Program Files\National Instruments\LabVIEW " + lv_version

        if absolute_path is None:
            print ("[resolve_path]error: OS version:%d, identifier:%s"
                   % (os_bit, path))
            raise
        if not os.path.exists(absolute_path):
            print "[resolve_path]error: %s path does not exist." % absolute_path
            raise

        return absolute_path


def get_os_bit():
    """Get the operation system's bit number."""
    if "PROGRAMFILES(x86)" in os.environ:
        bits = 64
    else:
        bits = 32
    return bits


def get_vipm_name(src_dir, pk_name):
    """Get the package file name under src_dir.
    If pk_name is not empty, the package file name should match pk_name string.
    If pk_name is empty, find the package which suffix is ".vip"
    """
    for fname in os.listdir(src_dir):
        if os.path.splitext(fname)[1] == ".vip":
        # find .vip file
            if pk_name == "":
                return fname
            elif re.match(pk_name, fname, re.I) is not None:
                return fname

    print ('[get_vipm_name]error: Can not find the package which matches "%s" string under %s'
           % (pk_name, src_dir))
    return None


def main():
    """
    Install vipm package according to the input parameters.
    parameters:
        -i/--isdaily  It supports "install_latest" and "install_custom" vipm package.
                      When setting this parameter, install the latest package.
                      Otherwise install the customed package.
        -s/--src      the base path of the vipm package.
        -x/--suffix   the suffix path of the vipm package.
        -d/--dest     the uncompressed path of the vipm package.
                      User can use absolute path or identifier.
                      The supported identifier is LabVIEWxxxxDIR[32/64],
                      xxxx refers to LabVIEW release version.
        -n/--name     the key word of the package file
    """
    try:
        # Parse arguments
        usage = ("usage: %prog -s/--src src_package_path -d/--dest dest_uncompress_path " +
                 "[-i/--isdaily] [-x/--suffix src package_suffix_path] [-n/--name package_name]")
        parser = OptionParser(usage)
        parser.add_option("-i", "--isdaily", action="store_true", dest="is_daily", default=False,
                          help='''When setting this parameter, the install type is installing latest package,
                                  otherwise is installing custom package.''')
        parser.add_option("-s", "--src", dest="src",
                          help=("When installing latest package, it's source package base path." +
                                "when installing custom package, it's customed source package path."))
        parser.add_option("-d", "--dest", dest="dest",
                          help='''The uncompressed path of the vipm package.
                                  It supports absolute path or identifier.
                                  The supported identifier is LabVIEWxxxxDIR[32/64],
                                  xxxx refers to LabVIEW release version.''')
        parser.add_option("-x", "--suffix", dest="suffix", default="",
                          help="""The suffix path of the vipm package, it's used by "install_latest" type.""")
        parser.add_option("-n", "--name", dest="name", default="",
                          help="The key word of the package file.")

        (options, args) = parser.parse_args()

        if options.src is None or options.dest is None:
            parser.error('Parameter "-s/--src" and "-d/--dest" is needed.')

        if options.is_daily is False and options.suffix != "":
            parser.error('When installing customed package, "suffix" can not be set.')

        # get package path
        pkg_src = get_pkg_path(options.is_daily, options.src, options.suffix)
        # get the uncompress package path
        pkg_dest = resolve_path(options.dest)

        # install package
        result = install_package(pkg_src, pkg_dest, options.name)

        if result == errcode.ER_FAILED:
            sys.exit(-1)
        else:
            sys.exit(0)
    except Exception, e:
        print e
        sys.exit(-1)


if __name__ == "__main__":
    main()