import os
import sys
import stat
import shutil
import re
import hashlib
import optparse
import datetime
import traceback
import ConfigParser
import msilib
import codecs
import p4lib
import logging
import tempfile
import subprocess
from misc import execute
# win32api needs installed
from win32api import GetFileVersionInfo, LOWORD, HIWORD

from _winreg import OpenKey, HKEY_LOCAL_MACHINE, QueryValueEx, KEY_ALL_ACCESS, KEY_WOW64_64KEY

__all__ = ["Product", "MSI", "InstallerReview", "ICE"]

LOGGER = logging.getLogger(__name__)

pathjoin = os.path.join


class Product:
    '''
    This class is used to analyze product.
    '''
    def __init__(self, path):
        LOGGER.info("Start construct product %s.", path)
        # The path of this product.
        self.path = path
        # The path of distribution the product belongs to.
        self.dist_path = self.find_dist_path()
        self.product_name = os.path.basename(path)
        # NIUpdateProductCode.
        self.product_code = None
        # NIUpdateProductVersion.
        self.product_version = None
        # The part list of this product.
        self.msi_list = self.find_all_msifiles()
        # The core part of this product.
        self.core_part = self.find_core_part()
        # The function get_product_info is used to get
        # NIUpdateProductCode and NIUpdateProductVersion property.
        self.get_product_info()
        '''
        The following variables are used when there is a released product
        The released product that has same NIUpdateProductCode
        with this product.
        '''
        self.released_product = None
        # Indicate whether the product name in registry not change.
        self.registry_name_ok = None
        # The version value in registry.
        self.registry_version = None
        self.registry_version_ok = None
        # The key that core part populates product information to.
        self.registry_key = None
        # Indicate whether the key is satisfied the checklist.
        self.registry_key_ok = None

    def find_all_msifiles(self):
        '''
        Find all part in this product.
        '''
        # Return r which is a list of class MSI.
        r = []
        for root, dirs, files in os.walk(self.path):
            for f in files:
                if f.endswith(".msi"):
                    r.append(MSI(pathjoin(root, f), self.dist_path))
        msi_names = [msi.name for msi in r]
        len_msi = len(msi_names)
        if len_msi == 1:
            LOGGER.debug("There is one part in this product,"
                         "and it is %s.", msi_names[0])
        elif len_msi == 0:
            LOGGER.error("We can not find any part"
                         "in product %s!", self.product_name)
        else:
            LOGGER.debug("There are %d parts in this product"
                         "and they are: %s.", len(msi_names),
                         ' '.join(msi_names))

        return r

    def find_core_part(self):
        '''
        Find the core part of this product.

        If return False: There is an error that "a product should
                            not have more than one core part".
                  None: Can't find the core part of this product.
                  MSI class: This msi class is the core part.
        '''
        i = 0
        for msi in self.msi_list:
            if (msi.is_core):
                i = i+1
                msi_core = msi
        if (i == 0):
            LOGGER.error("Can not find core part in product"
                         "%s!", self.product_name)
            return None
        elif(i > 1):
            LOGGER.error("There are more than one core part"
                         "in product %s!", self.product_name)
            return False
        else:
            LOGGER.debug("The core part of this product is "
                         "%s.",  msi_core.name)
            return msi_core

    def find_dist_path(self):
        '''
        Get the distribution path that the product belongs to.
        '''
        try:
            dist_path = os.path.dirname(os.path.dirname(self.path))
            LOGGER.debug("The distribution path is: %s.", dist_path)
            return dist_path
        except Exception, e:
            LOGGER.error("Can not find the distribution path of"
                         "product %s!", self.product_name)
        return None

    def get_product_info(self):
        '''
        Used to find the NIUpdateProductCode and NIUpdateProductVersion
        property.
        '''
        if not (self.core_part):
            LOGGER.error("Can not find the core part of product"
                         "%s.", self.product_name)
        else:
            self.product_code = self.core_part. \
                read_msitable_property("NIUpdateProductCode")
            LOGGER.debug("The NIUpdateProductCode is %s.", self.product_code)
            self.product_version = self.core_part. \
                read_msitable_property("NIUpdateProductVersion")
            LOGGER.debug("The NIUpdateProductVersion %s.",
                         self.product_version)

    def judge_registry_key(self, registry_key):
        '''
        Judge whether a registry key satisfies the following rules:
        1. If the product allows side-by-side installs, the values
        should be populated at key HKLM\Software\National Instruments
        \<Product Name>\<version major.minor>
        2. If the product does not allow side-by-side installs,
        the values should be populated at key HKLM\Software\
        National Instruments\<Product Name>\CurrentVersion
        '''
        try:
            if (not self.core_part) or self.core_part.side_by_side is None:
                LOGGER.error("Please find the core part and judge whether"
                             "the core part is side by side firstly.")
                return None

            elif(self.core_part.side_by_side is True):
                version = registry_key.split('\\')[-1]
                pattern = re.compile("^(\d+)\.(\d+)\.(\d+)(\.\d+)?$")
                m = pattern.match(version)
                if m:
                    LOGGER.info("The core part of this product is side by"
                                " side, and registry key %s is in correct"
                                " format.", registry_key)
                    return True
                else:
                    LOGGER.info("The core part of this product is side by side"
                                ",and registry key %s is not in correct format"
                                ".", registry_key)
                    return False

            else:
                version = registry_key.split('\\')[-1]
                if (version == 'CurrentVersion'):
                    LOGGER.info("The core part of this product is upgrade, and "
                                "the registry key %s is in correct format.",
                                registry_key)
                    return True
                else:
                    LOGGER.info("The core part of this product is upgrade, and "
                                "the registry key %s is not in correct format"
                                ".", registry_key)
                    return False
        except Exception, e:
            LOGGER.info("The registry key is not in correct format.")
            return False

    def read_core_part_registry(self, propertyname):
        '''
        Read the registry information from msi registry table.
        A part may have several registry for one property.
        For Example nilm.msi has three path key:
            SOFTWARE\FLEXlm License Manager\NILM License Manager
            SOFTWARE\National Instruments\License Manager\CurrentVersion
            SOFTWARE\National Instruments\License Manager

        So We should judge whether the keys are in correct format
            firstly and return the correct one.
        '''
        try:
            sql = "select * from Registry"
            db = msilib.OpenDatabase(self.core_part.path,
                                     msilib.MSIDBOPEN_READONLY)
            v = db.OpenView(sql)
            v.Execute(None)
            r = v.Fetch()
            while r:
                if (r.GetString(4).lower() == propertyname.lower()):
                    LOGGER.debug("Get the %s value of this product in registry"
                                 " tabel is %s.", propertyname, r.GetString(5))
                    LOGGER.debug("Get the registry key is %s.", r.GetString(3))
                    self.registry_key_ok = \
                        self.judge_registry_key(r.GetString(3))
                    if self.registry_key_ok:
                        return (r.GetString(3), r.GetString(5))
                r = v.Fetch()
        except Exception, e:
            if self.registry_key_ok is False:
                LOGGER.error("%s gets %s registry, but the key is not in"
                            " correct format.", self.product_name,
                            propertyname)
            else:
                LOGGER.debug("%s does not have %s registry",
                             self.product_name, propertyname)
        finally:
            v.Close()
        return (None, None)

    def get_core_part_registry(self):
        '''
        This function is used to find the registry information
        of core part in this product.
        '''
        if not (self.core_part):
            LOGGER.error("Can not find the core part of product %s.",
                         self.product_name)
        else:
            # Get the version property in registry tabel.
            self.registry_key, self.registry_version = \
                self.read_core_part_registry("Version")
            if self.registry_key:
                return

            # Get the path property in registry tabel.
            self.registry_key, registry_path = \
                self.read_core_part_registry("path")
            if (self.registry_key):
                return

            # Get the VersionString property in registry tabel.
            self.registry_key, registry_version_string = \
                self.read_core_part_registry("VersionString")
            if (self.registry_key):
                return

            # Get the ProductName property in registry tabel.
            self.registry_key, registry_product_name = \
                self.read_core_part_registry("ProductName")
            if (self.registry_key):
                return

            LOGGER.warn("The product %s doesn't have registry information!",
                        self.product_name)

    def get_registry_product_name(self):
        '''
        If the product allows side-by-side installs, the values should be
        populated at key HKLM\Software\National Instruments\<Product Name>
        \<version major.minor> If the product does not allow side-by-side
        installs, the values should be populated at key HKLM\Software\
        National Instruments\<Product Name>\CurrentVersion
        This function is used to get the value of <Product Name>
        '''
        if (self.registry_key):
            try:
                registry_product_name = self.registry_key.split('\\')[-2]
                LOGGER.debug("The product name in registry is %s.",
                             registry_product_name)
                return registry_product_name
            except Exception, e:
                correct_key = r'''If the product allows side-by-side installs
                              , the values should be populated at key HKLM\
                              Software\National Instruments \<Product Name>\
                              <version major.minor> If the product does not
                              allow side-by-side installs, the values should
                              be populated at key HKLM\Software\National
                              Instruments\<Product Name>\CurrentVersion'''
                LOGGER.error("The product %s's registry key is %s. This is "
                             "not a correct registry key. The correct format"
                             " should be: %s", self.product_name,
                             self.registry_key, correct_key)
                return False
        else:
            return None

    def check_registry_product_name(self):
        '''
        To check whether the <Product Name> key has not changed since the
        previous release, even if the customer-visible name for your
        product has changed.
        '''
        LOGGER.info("Check whether the <Product Name> key has not changed"
                    " since the previous release.")
        if not self.released_product:
            LOGGER.error("The product does not have a released product!")
            return
        n1 = self.get_registry_product_name()
        n2 = self.released_product.get_registry_product_name()
        LOGGER.debug("The product names in currect product and released"
                     " product registry are %s, %s respectively.", n1, n2)
        if (not n1) or (not n2):
            LOGGER.warn("Can't get the correct product name from current"
                        " product or released product registries, because"
                        " registry key is not in correct format!")
            self.registry_name_ok = None
        elif(n1 == n2):
            LOGGER.info("The product names in registry are same, and they"
                        " are %s!", n1)
            self.registry_name_ok = True
        else:
            LOGGER.error("The product names in registry have changed, and they"
                         " are %s, %s respectively!", n1, n2)
            self.registry_name_ok = False

    def judge_version(self, version):
        '''
        Both the minor and update fields of the Version are less than or
        equal to 9, and the major field is less than 65535
        '''
        pattern = re.compile("^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<update>\d+)(?:\.\d+)?$")
        m = pattern.match(version)

        if m is None:
            LOGGER.error("The version is not in correct format!")
            return False
        major = int(m.group('major'))
        minor = int(m.group('minor'))
        update = int(m.group('update'))
        if not (major < 65535):
            LOGGER.error("The major field should be less than 65535!")
            return False
        elif (minor > 9) or (update > 9):
            LOGGER.error("Both the minor and update fields of the Version "
                         "value (Table 2.2) should be less than or equal to 9")
            return False
        else:
            LOGGER.info("The registry version is in correct format!")
            return True

    def check_the_version(self):
        '''
        Both the minor and update fields of the Version value (Table 2.2)
        are less than or equal to 9, and the major field is less than 65535
        '''
        LOGGER.info("Check whether the version in registry key is in"
                    " correct format.")
        if not self.registry_version:
            LOGGER.warn("Can't get the registry version information!")
        else:
            LOGGER.debug("The version in registry key is %s.",
                         self.registry_version)
            self.registry_version_ok = \
                self.judge_version(self.registry_version)

    def check_versions_increased(self, v1, v2):
        '''
        Version rules and has been
        properly incremented with respect to prior versions of the part

        v1 is current version
        v2 is released version
        '''
        LOGGER.debug("compare version:version = %s, version = %s", v1, v2)
        if v1 is None or v2 is None:
            LOGGER.error("v1 or v2 is None!")
            return None
        pattern = re.compile("^(\d+)\.(\d+)\.(\d+)(\.\d+)?$")
        m1 = pattern.match(v1)
        m2 = pattern.match(v2)

        if m1 is None or m2 is None:
            LOGGER.error("ProductVersion in inconsistent format! %s"
                         " %s", v1, v2)
            return False

        for x, y in zip(m1.groups(), m2.groups()):
            if x is None or y is None:
                continue

            x, y = int(x), int(y)

            if x == y:
                continue
            elif x < y:
                LOGGER.error("ProductVersion not increased! newer = %s "
                             "older = %s", v1, v2)
                return False
            else:
                return True

        LOGGER.info("Versions stay the same! newer = %s older ="
                     " %s", v1, v2)
        return False

    def check_product_property_core_part(self):
        '''
        - 3.7 NIUpdateProductCode and NIUpdateProductVersion properties are
        set in all core parts, and are not set in any child parts.
        '''
        if (not self.product_code) or (not self.product_version):
            return False
        if len(self.msi_list) == 1:
            return True
        for msi in self.msi_list:
            if not msi.is_core:
                product_code = \
                    msi.read_msitable_property("NIUpdateProductCode")
                product_version = \
                    msi.read_msitable_property("NIUpdateProductVersion")
                if (product_code or product_version):
                    return False
        else:
            return True


class MSI:
    '''
    This class is used to analyze msi.
    '''
    def __init__(self, path, dist_path=None):
        LOGGER.debug("Start construct msi %s.", path)
        # The msi path
        self.path = path
        # The msi name
        self.name = os.path.basename(path)
        # The distribution path of this msi
        self.dist_path = dist_path
        # Whether this msi is core part
        self.is_core = self.is_core_part()
        self.upgrade_code = self.get_upgrade_code()
        self.product_version = self.get_product_version()
        # Whether this part is side by side
        self.side_by_side = None
        # The corresponding part in released distribution.
        self.released_msi = None

    def is_core_part(self):
        '''
        Check whether this msi is core part
        '''
        if not self.dist_path:
            LOGGER.warn("You should assign distribution path!")
            return None
        f = pathjoin(self.dist_path, 'setup.ini')
        if not os.path.exists(f):
            LOGGER.error("%s not found!", f)
            return None

        conf = ConfigParser.ConfigParser()
        conf.readfp(open(f))
        if conf.has_option(self.name, "ProductId"):
            return True
        else:
            return False

    def get_upgrade_code(self):
        '''
        Get the UpgradeCode of this part.
        '''
        upgrade_code = self.read_msitable_property("UpgradeCode")
        LOGGER.debug("UpgradeCode is %s.", upgrade_code)
        return upgrade_code

    def get_product_version(self):
        '''
        Check whether this msi is core part
        '''
        product_version = self.read_msitable_property("ProductVersion")
        LOGGER.debug("ProductVersion is %s.", product_version)
        return product_version

    def read_msitable_property(self, propertyname):
        '''
        Read the property from msi.

        Param
        propertyname :
            maybe type of string, or type of re.Pattern returned by re.compile
        '''
        if not os.path.exists(self.path):
            LOGGER.error("%s not found!", self.path)
            return None

        def compare(propname=propertyname):
            if isinstance(propname, str):
                return lambda x: str.__eq__(propname, x)
            elif type(propname) == type(re.compile("")):
                return lambda x: propname.match(x) is not None

        try:
            sql = "select * from Property"
            db = msilib.OpenDatabase(self.path, msilib.MSIDBOPEN_READONLY)
            v = db.OpenView(sql)
            v.Execute(None)
            r = v.Fetch()
            while r:
                if compare()(r.GetString(1)):
                    return r.GetString(2)
                r = v.Fetch()
        except Exception, e:
            if type(propertyname) == str:
                LOGGER.error("Open %s fail, or this msi doesn't have the"
                             " property %s!", self.path, propertyname)
            elif type(propertyname) == type(re.compile("")):
                LOGGER.error("Open %s fail, or this msi doesn't have the"
                             "re.Pattern property!", self.path)
        finally:
            v.Close()
        return None

    def check_product_version_number(self, version):
        '''
        3.7 The major and minor fields should not exceed 255;
        the build field and any additional fields should not exceed 65535.
        '''
        pattern = re.compile("^(\d+)\.(\d+)\.(\d+)(\.\d+)?$")
        m = pattern.match(version)

        if m is None:
            LOGGER.error("The version is not in correct format!")
            return False
        major = int(m.groups()[0])
        minor = int(m.groups()[1])
        build = int(m.groups()[2])
        if (build > 65535):
            LOGGER.error("The build field and any additional fields should "
                         "not exceed 65535!")
            return False
        elif (major > 255) or (minor > 255):
            LOGGER.error("The major and minor fields should not exceed 255!")
            return False
        else:
            LOGGER.debug("The ProductVersion is in correct format!")
            return True


class InstallerReview:

    def __init__(self, root, products, released=None, output=None):
        self.root = root
        self.product_names = products
        self.released = released
        self.output = output
        self.products = self.construct_product()
        self.minitree = None
        self.setupini = self.load_setup_ini()

    def construct_product(self):
        p = []
        for pn in self.product_names:
            p.append(Product(pathjoin(self.root, 'Products', pn)))
        return p

    def load_setup_ini(self):
        f = os.path.join(self.root, 'setup.ini')
        if not os.path.exists(f):
            LOGGER.error("The file %s doesn't exist! Can't check Logging!", f)
            return None
        conf = ConfigParser.ConfigParser()
        conf.readfp(open(f))
        return conf

    def check_ICEs(self, MIF=None, iBuild=None):
        '''
        - 1.1 and - 3.1:  Internal Consistency Evaluators(ICEs)
        It's duplicate with 3.1 ICE check done by runice.py
        '''
        ice = ICE(self.root, self.product_names, self.output,
                  MIF, iBuild, True)
        status = ice.run_ICE_check()
        LOGGER.debug("The minitree is %s!", ice.minitree)
        self.minitree = ice.minitree
        return status

    def check_autorun(self):
        '''
        Check whether there is autorun.exe in root path
        '''
        f = os.path.join(self.root, 'autorun.exe')
        return os.path.exists(f)

    def check_isbeta(self):
        '''
        Check whether the distribution is a release version.
        '''
        if not self.setupini:
            return None
        if self.setupini.has_option("Settings", "IsBeta"):
            v = self.setupini.getint("Settings", "IsBeta")
            return v == 0
        else:
            return True

    def read_guid_from_nidist(self, f):
        '''
        Read distributionGUID in nidist.id file.
        '''
        if not os.path.exists(f):
            LOGGER.error("file not found, %s", f)
            return None
        conf = ConfigParser.ConfigParser()
        conf.readfp(open(f))
        v = None
        if conf.has_option("Volume Id", "DistributionGUID"):
            v = conf.get("Volume Id", "DistributionGUID")
        return v

    def check_dist_guid(self):
        '''
        Check distribution GUID in nidist.id matches that of previously
        released versions of this distribution.
        '''
        if not self.released:
            LOGGER.warn("you do not provide release distribution, "
                        "this makes sense if you're on an initial version")
            return True

        old = self.read_guid_from_nidist(pathjoin(self.released, 'nidist.id'))
        new = self.read_guid_from_nidist(pathjoin(self.root, 'nidist.id'))
        LOGGER.info("Distribution GUID(released): %s", old)
        LOGGER.info("Distribution GUID(     dev): %s", new)
        return old == new

    def check_EULA(self):
        '''
        -1.10 NI End-User License Agreements(EULAs)
        The latest versions of the NI license agreements are included
        in the distribution.
        '''
        p4path = "//NIInstallers/export/Legal/license/NIReleased"
        try:
            perforce = os.getenv('nibuild_perforce_clientspec').rstrip("\\")
            perforce = p4lib.P4(user=os.getenv("P4USER"), client=perforce,
                                port="perforce:1666")
            perforce.sync(p4path + "/...", force=True)
            f1 = perforce.files(files=p4path + "/NI Released License"
                                " Agreement...rtf")
            fset1 = []
            for f in f1:
                depotf = f["depotFile"]
                localf = perforce.where(depotf)[0]["localFile"]
                fset1.append(localf)

            f2 = os.listdir(pathjoin(self.root, 'Licenses'))
            fset2 = []
            pat = re.compile("\ANI Released License Agreement.*\.rtf\Z", re.I)
            fset2 = [pathjoin(self.root, "Licenses", f) for f in f2
                     if pat.match(f)]
            fset1.sort()
            fset2.sort()

            if len(fset1) != len(fset2):
                LOGGER.error("EULA file sets diff in file numbers. perforce"
                             " side(%d), installer side(%d)", len(fset1),
                             len(fset2))
                for f in fset1:
                    LOGGER.debug("perforce side file: %s", f)
                for f in fset2:
                    LOGGER.debug("installer sider file: %s", f)
                return None

            tag = True
            logbuffer = ["\n"]
            for xy in zip(fset1, fset2):
                x, y = xy
                m1 = hashlib.md5()
                m1.update(open(x).read())
                m1 = m1.hexdigest()
                m2 = hashlib.md5()
                m2.update(open(y).read())
                m2 = m2.hexdigest()
                logbuffer.append("md5: %s file %s" % (m1, x))
                logbuffer.append("md5: %s file %s" % (m2, y))
                if m1 != m2:
                    logbuffer.append("EULA not identical in md5 cmp:\n%s"
                                     "vs.\n %s" % (x, y))
                    tag = False
                else:
                    logbuffer.append("EULA identical")
            LOGGER.info("\n".join(logbuffer))
            return tag

        except Exception:
            LOGGER.error("fail to check EULA")
            traceback.print_exc()
            return None

    def detect(self, filename):
        ''' buffer -> encoding_name
        The buffer should be at least 4 bytes long.
            Returns None if encoding cannot be detected.
            Note that encoding_name might not have an installed
            decoder (e.g. EBCDIC)
        '''
        # a more efficient implementation would not decode the whole
        # buffer at once but otherwise we'd have to decode a character at
        # a time looking for the quote character...that's a pain

        # according to the XML spec, this is the default
        # this code successively tries to refine the default
        # whenever it fails to refine, it falls back to
        encoding = "utf-8"

        # the last place encoding was set.
        autodetect_dict = {(0x00, 0x00, 0xFE, 0xFF): ("ucs4-be"),
                           (0xFF, 0xFE, 0x00, 0x00): ("ucs4-le"),
                           (0xFE, 0xFF, None, None): ("utf-16-be"),
                           (0xFF, 0xFE, None, None): ("utf-16-le"),
                           (0x00, 0x3C, 0x00, 0x3F): ("utf-16-be"),
                           (0x3C, 0x00, 0x3F, 0x00): ("utf-16-le"),
                           (0x3C, 0x3F, 0x78, 0x6D): ("utf-8"),
                           (0x4C, 0x6F, 0xA7, 0x94): ("EBCDIC")}
        buffer = open(filename, "r").read(4)
        bytes = (byte1, byte2, byte3, byte4) = tuple(map(ord, buffer[0:4]))
        enc_info = autodetect_dict.get(bytes, None)
        # try autodetection again removing potentially
        if not enc_info:
            # variable bytes
            bytes = (byte1, byte2, None, None)
            enc_info = autodetect_dict.get(bytes)
        if enc_info:
            # we've got a guess... these are
            encoding = enc_info
        return encoding

    def read_file_in_lines(self, f):
        encoding = self.detect(f)
        if encoding is None:
            LOGGER.error("Could not detect %s file encoding", f)
            return None
        file_lines = []
        if encoding == "utf-16-le" or encoding == "utf-16-be":
            LOGGER.debug("%s's encoding is utf-16", f)
            file_lines = codecs.open(f, 'r', "utf-16").readlines()
        elif encoding == 'utf-8':
            LOGGER.debug("%s's encoding is utf-8", f)
            file_lines = codecs.open(f, 'r', "utf-8").readlines()
        else:
            LOGGER.warn("file encoding %s not supported! only support"
                        " utf-8, utf-16", encoding)
        return file_lines

    def check_end_execute(self, ilog, permitted_return_code):
        '''
        -1.12 check End Execute items, All executables specified to run
        after installation have been tested to run correctly (or not run
        as appropriate)

        Param:
            ilog   The path of install log.
            permitted_return_code  The permitted return code list.
        '''
        if not os.path.exists(ilog):
            LOGGER.error("install log %s not exist, end execution check"
                         " defaults to be dissatisfied.", ilog)
            return None
        pat = re.compile("^MetaInstaller: MetaInstaller exiting.+Returning"
                         " (\d+)\s*.*$")

        lines = self.read_file_in_lines(ilog)
        if not lines:
            LOGGER.error("can not read lines from %s", ilog)
            return False

        for line in lines:
            m = pat.match(line)
            if m:
                LOGGER.debug("math line: %s", line)
                code = int(m.groups()[0])
                LOGGER.debug("returning code is: %s", code)
                return code in permitted_return_code
        LOGGER.error("Can not find matched line in %s to match '%s'",
                     ilog, pat.pattern)
        return False

    def check_dialogs(self):
        '''
        1.18 The Phone Home dialog is visible and the option to check
        for notifications is on by default.
        '''
        if not self.setupini:
            return None
        v1 = self.setupini.getint("PhoneHome", "DefaultState")
        v2 = self.setupini.getint("PhoneHome", "visible")
        return (v1 == 1) and (v2 == 1)

    def check_product_activation(self):
        '''
        1.21 Product Activation
        If your application is licensed, at least one CoreLicenses element
        is declared as a child of your Distribution element.
        '''
        if not self.setupini:
            return None
        for sec in self.setupini.sections():
            if self.setupini.has_option(sec, "CoreLicenses"):
                v = self.setupini.getint(sec, "CoreLicenses")
                return v != 0
        else:
            return False

    def check_dist_scanner(self):
        '''
        - 1.22 Distribution Scanner: DistScanner.exe confirms that
        all parts schedule RemoveExistingProducts properly.
        '''
        f = pathjoin(self.output, ICE.ScanLogFile)
        if not os.path.exists(f):
            LOGGER.error("%s NOT found! Run ice check first", f)
            return None
        for line in self.read_file_in_lines(f):
            r = line.find("RemoveExistingProducts")
            if r != -1:             # found
                return False
        else:
            return True

    def check_OS_restrictions(self, version_nt_min, version_nt_max):
        '''
        - 1.23 OS Restrictions
        The default value of OSRestriction is overridden only if your
        distribution has higher OS requirements than the department
        default (XPsp2)
        '''
        if not self.setupini:
            return None
        v1 = self.setupini.get("OS", "VersionNTMin")
        v2 = self.setupini.get("OS", "VersionNTMax")
        return v1 == version_nt_min and v2 == version_nt_max

    def find_all_released_products(self):
        '''
        Find all products from the released product path.
        '''
        r = []
        released_product_path = pathjoin(self.released, r'Products')
        dirs = os.walk(released_product_path).next()[1]
        for d in dirs:
            r.append(Product(pathjoin(released_product_path, d)))
        return r

    def get_part_pairs(self, product, rproduct):
        '''
        Get the corresponding part in released product.
        '''
        for msi in product.msi_list:
            for rmsi in rproduct.msi_list:
                if (msi.upgrade_code == rmsi.upgrade_code):
                    msi.side_by_side = False
                    rmsi.side_by_side = False
                    msi.released_msi = rmsi
                    LOGGER.info("The part %s is a upgrade part!", msi.name)
                    LOGGER.info("The corresponding part is %s in in released"
                                " distribution: %s!", rmsi.name, self.released)
                    break
            else:
                for rmsi in rproduct.msi_list:
                    if ((msi.name == rmsi.name) and
                       (rmsi.side_by_side is not False)):
                        msi.side_by_side = True
                        rmsi.side_by_side = True
                        msi.released_msi = rmsi
                        LOGGER.info("The part %s is a side by side part!",
                                    msi.name)
                        LOGGER.info("The corresponding part is %s in"
                                    " released distribution: %s!",
                                    rmsi.name, self.released)
                        break
                else:
                    len_product = len(product.msi_list)
                    len_rproduct = len(rproduct.msi_list)
                    if(len_product == 1 and len_rproduct == 1):
                        msi.side_by_side = True
                        rmsi.side_by_side = True
                        msi.released_msi = rmsi
                        LOGGER.info("The part %s is a side by side part!",
                                    msi.name)
                    else:
                        LOGGER.info("The part %s is a side by side part "
                                    "or new part!", msi.name)

    def get_product_pairs(self):
        '''
        Get the corresponding product in released distribution.
        '''
        if not self.released:
            LOGGER.info("\n#################################Start analyze"
                        " the product side by side property.#############"
                        "#########")
            LOGGER.debug("You should provide the released distribution path!")
            return
        else:
            released_products = self.find_all_released_products()
            LOGGER.info("\n#################################Start analyze "
                        "the product side by side property.###############"
                        "#######")
            for product in self.products:
                LOGGER.info("Start analyze the product %s.",
                            product.product_name)
                LOGGER.info("The NIUpdateProductCode is %s.",
                            product.product_code)
                LOGGER.info("The NIUpdateProductVersion is %s.",
                            product.product_version)
                for rproduct in released_products:
                    if (product.product_code == rproduct.product_code):
                        product.released_product = rproduct
                        LOGGER.info("The corresponding product is %s in "
                                    "released distribution: %s!",
                                    rproduct.product_name, self.released)
                        LOGGER.info("The NIUpdateProductCode is %s.",
                                    rproduct.product_code)
                        LOGGER.info("The NIUpdateProductVersion is %s.",
                                    rproduct.product_version)
                        self.get_part_pairs(product, rproduct)
                        break
                else:
                    LOGGER.info("The product %s is a new product!",
                                product.product_name)

    def check_registry(self):
        '''
        This function is used to analyze the registry of products.
        '''
        LOGGER.info("\n#######################Start analyze the registry."
                    "#####################")
        for product in self.products:
            if product.released_product:
                LOGGER.info("Start analyze the registry of product %s.",
                            product.product_name)
                LOGGER.info("Get the core part registry information of "
                            "this product!")
                product.get_core_part_registry()
                LOGGER.info("Get the core part registry information of "
                            "the released product!")
                product.released_product.get_core_part_registry()
                product.check_registry_product_name()
                product.check_the_version()
            else:
                LOGGER.info("The product doesn't have a released product, so"
                            "can't analyze the registry of product %s.",
                            product.product_name)

    def check_metautils(self):
        '''
        - 3.8 DistScanner.exe confirms that parts do not include
        unreleased versions of NIMetaUtils. Ensure the string
        "VersionCheck" does not appear in the log.
        '''
        f = pathjoin(self.output, ICE.ScanLogFile)
        if not os.path.exists(f):
            LOGGER.error("%s not found, you should run runice.py first", f)
            return None
        for line in self.read_file_in_lines(f):
        #for line in open(f).readlines():
            r = line.find("VersionCheck")
            if r != -1:             # found
                return False
        else:
            return True

    def get_windows_file_version_in_attribute_page(self, filename):
        def get_version_number(filename):
            try:
                info = GetFileVersionInfo(filename, os.path.sep)
                ms = info['FileVersionMS']
                ls = info['FileVersionLS']
                return HIWORD(ms), LOWORD(ms), HIWORD(ls), LOWORD(ls)
            except:
                return (0, 0, 0, 0)

        tup = get_version_number(filename)
        ls = [str(i) for i in tup]
        return (".".join(ls), filename)

    def attached_document_version_numbers(self):
        '''
        Version numbers of distributed installer binaries.
        '''
        display_info = []
        filelist = ["setup.exe", r"Bin\niPie.exe", ]
        for f in filelist:
            ff = pathjoin(self.root, f)
            v = self.get_windows_file_version_in_attribute_page(ff)
            display_info.append(v)

        check_items = [
            ["Products\\MetaUninstaller\\MU\\MetaUninstaller.msi",
             "Property", "ProductVersion"],
            ["Products\\MDF\\MDF\\MDFSupport.msi",
             "Property", "ProductVersion"],
            # pattern
            ["Bin\\merged.bin.msi", "Property", "NIBuildDate.NIMetaUtils"],
            # pattern
            ["Bin\\merged.bin.msi", "Property", "NIVersion.uninstall.exe"]]
        for item in check_items[:2]:
            f = pathjoin(self.root, item[0])
            v = MSI(f).read_msitable_property("ProductVersion")
            display_info.append((v, "%s/@%s, FROM %s" %
                                 (item[1], item[2], item[0])))

        for item in check_items[2:]:
            # merged.bin is in minitree, not self.root, since we may have
            # no write permisstion to self.root
            if self.minitree:
                f = pathjoin(self.minitree, item[0])
                v = MSI(f).read_msitable_property(re.compile("^%s.*$" % item[2]))
                display_info.append((v, "%s/@%s, FROM %s" %
                                     (item[1], item[2], item[0])))
        if self.minitree:
            shutil.rmtree(self.minitree, True)
        return display_info


class ICE:
    # The ice log name
    ICELogFile = "ice.log"
    # The scan result name
    ScanLogFile = "scan.xml"

    def __init__(self, root, products, output="", MIF=None,
                 iBuild=None, debug=False):
        self.root = root
        self.products = products
        self.pacific = None
        self.perforce = None
        self.penguin = None
        self.unzipper = ""
        self.output = output
        self.prepare_env_ice(output)
        self.MIF = self.get_MIF(MIF)
        self.iBuild = self.get_iBuild(iBuild)
        self.debug = debug
        self.minitree = None
        self.ForceSync = False

    def prepare_env_ice(self, output):
        '''
        Prepare the environment for class ICE.

        :param output:
            The output directory for ICE log and Scan result.
        '''

        # Initialize the pacific, perforce and penguin
        self.pacific = p4lib.P4(user=os.getenv("P4USER"), client=os.getenv
                                ("nibuild_pacific_clientspec"),
                                port="pacific:1666")
        self.perforce = p4lib.P4(user=os.getenv("P4USER"), client=os.getenv
                                 ('nibuild_perforce_clientspec'),
                                 port="perforce:1666")
        self.penguin = p4lib.P4(user=os.getenv("P4USER"), client=os.getenv
                                ('nibuild_penguin_clientspec'),
                                port="penguin:1666")

        # Find the 7-Zip path
        try:
            try:
                key = OpenKey(HKEY_LOCAL_MACHINE, 'SOFTWARE\\7-Zip')
            except:
                key = OpenKey(HKEY_LOCAL_MACHINE, 'SOFTWARE\\7-Zip', 0, (KEY_WOW64_64KEY | KEY_ALL_ACCESS))
            self.unzipper = QueryValueEx(key, "Path")[0]
            self.unzipper = self.unzipper + r'\7z.exe'
        except Exception, e:
            LOGGER.error("Your machine doesn't install 7-Zip? "
                         "Install it firstly.")

        # Make sure ICELogFile and ScanLogFile is cleaned
        try:
            for f in [ICE.ICELogFile, ICE.ScanLogFile]:
                f2 = os.path.join(output, f)
                os.path.exists(f2) and os.remove(f2)
        except Exception, e:
            LOGGER.error("cleaning %s, %s at %s faild: %s",
                         "ice.log", "scan.xml", output, e)

    def get_MIF(self, MIF):
        '''
        Get the path of MIF.

        :param MIF:
            The path of MIF that user specified.
        '''
        # perforce
        MIF_export = "//NIInstallers/export"
        # user specifies MIF version
        if not MIF:
            MIF = self.newest_version_path(MIF_export, self.perforce)
            if MIF is None:
                raise Exception("get newest MIF version fail:"
                                "perforce:%s", MIF_export)
            MIF = "/".join([MIF_export, MIF[0], MIF[1], "MIF"])
        else:
            MIF = MIF.rstrip("/\\")
        LOGGER.debug("use MIF %s", MIF)
        return MIF

    def get_iBuild(self, iBuild):
        '''
        Get the path of iBuild.

        :param iBuild:
            The path of iBuild that user specified.
        '''
        # penguin
        iBuild_export = "//NIComponents/iBuild/export"
        # use specifies iBuild version
        if not iBuild:
            iBuild = self.newest_version_path(iBuild_export, self.penguin)
            if iBuild is None:
                raise Exception("get newest iBuild fail:"
                                "penguin:%s", iBuild_export)
            iBuild = "/".join([iBuild_export] + iBuild)
        else:
            iBuild = iBuild.rstrip("/\\")
        LOGGER.debug("use iBuild %s", iBuild)
        return iBuild

    def run_ICE_check(self):
        '''
        The main funtion that runs ICE check.
        '''
        # perforce
        nicubs_file = self.MIF + "/NICommon/NIICE/niice.cub"
        scanner = self.MIF + "/MetaBuilder/Release/DistScanner.exe"
        # perforce
        rubydir = "//sa/ss/toolchain/Ruby/export/180/187f75/tools/win32/i386"
        rubyexe = rubydir + "/bin/ruby.exe"
        # On pacific
        ruby_script = "//SAST/Internal_Service/Installer/ICECheckTool" \
            "/cubs_withWarning.rb"
        # Step 1, sync necessary files
        self.do_syncing([(self.iBuild, 'penguin', 'dir'),
                        (scanner, 'perforce', 'file'),
                        (ruby_script, 'pacific', 'file'),
                        (rubydir, 'perforce', 'dir'),
                        (nicubs_file, 'perforce', 'file')])

        smokedirNew = self.iBuild + "/tools/win32/i386/ibuild/WiX2"
        smokedir = self.iBuild + "/tools/win32/i386/ibuild/Smoke"
        smoke = self.penguin.where(smokedir)[0]["localFile"]
        if not os.path.exists(smoke):
            smoke = self.penguin.where(smokedirNew)[0]["localFile"]

        LOGGER.debug("niice.cub: %s", nicubs_file)
        LOGGER.debug("DistScanner.exe: %s", scanner)
        LOGGER.debug("ruby script: %s", ruby_script)
        LOGGER.debug("ruby interpreter: %s", rubyexe)
        LOGGER.debug("unzipper: %s", self.unzipper)
        LOGGER.debug("Smoke folder: %s", smoke)

        # Step 2: copy
        # Copy niice.cub
        src = None
        dst = None
        w = self.perforce.where(nicubs_file)
        src = w[0]["localFile"]
        dst = os.path.join(smoke, os.path.basename(src))
        LOGGER.debug("remove %s", dst)
        self.remove_readonly_file(dst)
        LOGGER.info("copy %s to %s", src, dst)
        shutil.copy(src, dst)

        # Step 3: make mini produt set
        if not os.path.exists(self.unzipper):
            LOGGER.error("%s NOT found! install it first.", self.unzipper)

        rt = tempfile.mkdtemp()
        self.minitree = rt
        LOGGER.info("create mini tree: %s", rt)
        try:
            self.create_mini_product(rt)
            # Step 4 Run ICE check
            ts = datetime.datetime.now().strftime("%Y-%m-%d-%H%M%S")
            ruby = self.perforce.where(rubyexe)[0]["localFile"]
            cub_withWarning = self.pacific.where(ruby_script)[0]["localFile"]
            cmd = '"%s" "%s" "%s" "%s"' % (ruby, cub_withWarning, rt, smoke)
            LOGGER.info("exec %s", cmd)
            pipe = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) \
                .communicate()
            icelog = os.path.join(self.output, ICE.ICELogFile)
            if pipe[1]:
                LOGGER.error(pipe[1])
            else:
                LOGGER.info("creating %s", icelog)
                with open(icelog, "w") as f:
                    f.write(pipe[0])
                LOGGER.info("%s ok", cmd)
            LOGGER.debug('cwd is %s', os.getcwd())
            LOGGER.info("Generate ICE log: %s", icelog)

            # Step 5 Run scanner
            scanner = self.perforce.where(scanner)[0]["localFile"]
            scanlog = os.path.join(self.output, ICE.ScanLogFile)
            cmd = '"%s" "%s" -noupd -scan "%s"' % (scanner, self.root, scanlog)
            LOGGER.info("exec %s", cmd)

            pipe = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) \
                .communicate()
            if os.path.exists(scanlog):
                LOGGER.info("scanlog %s generated", scanlog)
            else:
                raise Exception("fail to run DistScanner: %s" % scanner)

            pipe[1] and LOGGER.error(pipe[1])
            LOGGER.info("Generate SCANNER log: %s", scanlog)
            return True
        except:
            LOGGER.error("\n" + traceback.format_exc())
            return False
        finally:
            # If this function is called by InstallerReview class,
            # the rt should not be deleted, because InstallerReview
            # will use this folder.
            if not self.debug:
                shutil.rmtree(rt, True)                     # ignore error
                self.minitree = None

    def create_mini_product(self, rt):
        '''
        Create a mini product set to the temp path. The mini product
        set only contains products that we want to check.
        '''
        for p in self.products:
            src = os.path.join(self.root, 'Products', p)
            dst = os.path.join(rt, "Products", p)
            LOGGER.info("copy %s to %s", src, dst)
            shutil.copytree(src, dst)
        # Copy merged.bin file to the temp folder.
        bin_path = os.path.join(self.root, "Bin", "merged.bin")
        Bin = os.path.join(rt, "Bin")
        os.makedirs(Bin)
        f = os.path.join(Bin, "merged.bin")
        if os.path.exists(bin_path):
            shutil.copy(bin_path, f)
        else:
            src = os.path.join(self.root, "Bin", "merged.cab")
            # no space after -o
            cmd = '"%s" e -y -o"%s" "%s" merged.bin' \
                % (self.unzipper, Bin, src)
            LOGGER.info("exec %s", cmd)
            pipe = subprocess.Popen(cmd, stderr=subprocess.PIPE).communicate()
            pipe[1] and LOGGER.error(pipe[1])  # stderr
            if not os.path.exists(f):
                LOGGER.error("unzip %s cause error!", src)
                raise Exception("unzip error")
        try:
            msiformat = f + ".msi"
            # this is for ICE test, it requires file surffix to be .msi
            shutil.copy(f, msiformat)
            if not msiformat:
                LOGGER.error("create file fail: %s", msiformat)
        except:
            LOGGER.error("create %s fail! This will result ice"
                         "check missing on merged.bin.", msiformat)
        # remove READONLY attribute from mini product set
        # if the depot is readonly, smoke.exe will fail,
        # reporting temp.xml access rejected.
        for r, d, files in os.walk(rt):
            for file_name in files:
                full_path = os.path.join(r, file_name)
                os.chmod(full_path, stat.S_IWRITE)

    def remove_readonly_file(self, f):
        '''
        Remove readonly file from disk.
        '''
        try:
            LOGGER.info("remove file: %s.", f)
            os.chmod(f, stat.S_IWRITE)
            os.remove(f)
        except Exception:
            LOGGER.error("remove file: %s error.", f)

    def sort_versions(self, versions):
        '''
        Sort versions under p4 in DESC order, and versions
        in format: "n.n" or "n.n.n"
        '''

        def convert(x):
            '''
            Convert string version into tuple format,
            e.g:
                    "1.2" -> (1, 2, 0);
                    "1.2.3" -> (1,2,3);
            '''
            pat1 = re.compile("^\d+\.\d+$")
            pat2 = re.compile("^\d+\.\d+\.\d+$")
            m = pat1.match(x)
            g = None
            if m is not None:
                # take 1.1 as 1.1.0
                g = m.group(0)
                g = g + ".0"
            else:
                m = pat2.match(x)
                if m is not None:
                    g = m.group(0)
                else:
                    # x is bad format
                    return (0, 0, 0)
            # g is still a string
            return map(int, g.split("."))

        def sorter(a, b):
            a = convert(a)
            b = convert(b)

            for xy in zip(a, b):
                x, y = xy
                if x > y:
                    return -1
                if x < y:
                    return 1
            else:
                return 0

        versions.sort(sorter)
        return versions

    def sort_dabf_version(self, versions):
        '''
        Sort 1.2.3C4 format versions where 'C' is a character in [d, a, b, f]
        '''
        def filter_version(versions):
            new_versions = []
            pat = re.compile("^\d+\.\d+\.\d+[abdf]{1}\d+$")
            for v in versions:
                if pat.match(v) is not None:
                    new_versions.append(v)
            else:                   # belongs to 'for'
                return new_versions

        def convert(v):
            '''
                Convert version string into a int list.
                The para v in the format of n.n.nCn, where n is a number and C
                is a character in (dabf). We convert the character into a
                number based on the index in (dabf).

                eg:
                    convert(1.2.3d5)
                    (1,2,3,0,5)
            '''
            k = "dabf"
            for c in k:
                v = v.replace(c, ".%s." % k.index(c))

            v = map(int, v.split("."))
            return v

        def sorter(v1, v2):
            '''
                v1 and v2 are in "1.2.3d5" format
            '''
            v1 = convert(v1)        # v1 in (1, 2, 3, 4, 5) after convert
            v2 = convert(v2)
            for xy in zip(v1, v2):
                x, y = xy
                if x > y:
                    return -1
                if x < y:
                    return 1
            return 0

        versions = filter_version(versions)
        versions = filter(None, versions)
        versions.sort(sorter)
        return versions

    def newest_version_path(self, rootpath, p4):
        '''
        Get the newest export directory from p4.

        param rootpath:
            p4 path, root the the version, like '//NIComponents/iBuild/export/'
        param p4:
            p4lib.P4 class object, the rootpath resides.

        return :
            the version pair of the newest version, like (12.0, 12.0.0f0)

        e.g.
            To get the newest ibuild version, call this function in this:
            newest = newest_version_path('//NIComponents/iBuild/
            export/', penguin)
        '''
        try:
            ret = range(2)
            rootpath = rootpath.rstrip("/")
            # list [ rootpath/xxx, rootpath/yyy, ...]
            versions = p4.dirs(rootpath + "/*")
            # list [ xxx, yyy]
            versions = [x.strip("/").rsplit("/", 1)[-1] for x in versions]
            versions = self.sort_versions(versions)
            if len(versions) <= 0:
                LOGGER.error("no suitable version available! %s", versions)
                return None
            ret[0] = versions[0]
            # path like rootpath/xxx/*
            path = rootpath + "/" + ret[0] + "/*"
            # list [rootpath/xxx/nnna0, rootpath/xxx/nnna1, ...]
            versions = p4.dirs(path)
            # list [ xxx, yyy]
            versions = [x.strip("/").rsplit("/", 1)[1] for x in versions]
            versions = self.sort_dabf_version(versions)
            if len(versions) <= 0:
                LOGGER.error("no version found!")
                return None
            ret[1] = versions[0]
            LOGGER.debug("get newest version: %s", repr(ret))
            return ret
        except Exception, e:
            LOGGER.error(traceback.format_exc())
            return None

    def sync_export(self, path, server):
        '''
        using p4sync (from Build Services) to sync export
        files, which knows about export on file server
        to get p4sync tool, we need to call setupEnv.bat
        and I choose the 1.8.1f2 ibuild for setupEnv.bat
        '''
        toolchain = r"//sa/ss/build/export/1.8/1.8.1f2"  # perforce
        self.perforce.sync(toolchain + "/...", force=self.ForceSync)
        local_toolchain_dir = self.perforce.where(toolchain)[0]["localFile"]
        # sync para, whether this is a force sync or not
        sync_para = ''
        if self.ForceSync:
            sync_para += ' --force'
        if (server=='perforce'):
            local_path = self.perforce.where(path)[0]["localFile"]
        elif (server=='penguin'):
            local_path = self.penguin.where(path)[0]["localFile"]
        else:
            local_path = self.pacific.where(path)[0]["localFile"]

        if os.path.exists(local_path):
            for file_name in os.listdir(local_path):
                if file_name.startswith(r'cookie.sync'):
                    LOGGER.info("%s has existed in this machine.", path)
                    return

        export_path = server + ':' + path.rstrip("/") + "/..."
        sync_export = ('cd /d "%s" && setupEnv.bat && p4sync %s "%s"' %
                       (local_toolchain_dir, sync_para, export_path))
        LOGGER.info("Run script to sync export (know about export on"
                    "file server):\n%s", sync_export)
        execute(sync_export)
        with open(local_path+r'\cookie.sync.p4', "w"):
            pass

    def do_syncing(self, items):
        '''
        Sync items from p4 server. Throw exception if sync fail.

        Param items
            Is a list of the structure (path, server, type)
            where path is the path of item that we want to sync.
            server is penguin, perforce or pacific.
            type is dir or file to indicate whether the path is
            a file or directory.

        eg:
            do_syncing([(r"//NIComponents/iBuild/export", 'penguin', 'dir'),
                    (r"//NIInstallers/export/14.5/14.5.0d4/MIF/MetaBuilder/
                    Release/DistScanner.exe", perforce, 'file')
                    ])
        '''
        for path_server_type in items:
            path, server_name, item_type = path_server_type
            server = getattr(self, server_name)
            if item_type == 'dir':
                LOGGER.info("syncing %s%s ... ", server_name, path)
                server.sync(path + "/...", force=self.ForceSync)
                self.sync_export(path, server_name)
            elif item_type == 'file':
                LOGGER.info("syncing %s%s ... ", server_name, path)
                server.sync(path, force=self.ForceSync)
            else:
                LOGGER.error("p4: %s, file: %s, type: %s",
                             server_name, path, item_type)
                raise Exception('bad parameter, only "dir/file" are allowed')
