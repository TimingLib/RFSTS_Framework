"""
This modules contains methods and classes for processing NI style version
strings. The version and BaseVersion class are stolen from Shiny.
"""

import re
import logging

logger = logging.getLogger(__name__)

__all__ = ['split_version', 'cmp_version',
           'BaseVersion', 'Version', 'PackageVersion', 'VersionError']

# match 1.0.0d0
_major_minor_build_rev_pat = re.compile(r"^(\d+)\.(\d+)\.(\d+)([abdf])(\d+)$")
# match 1.0
_major_minor_pat = re.compile(r"^(\d+)\.(\d+)$")
# match 1.0.0
_major_minor_build_pat = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
# match 100
_major_minor_build_old_pat = re.compile(r"^(\d)(\d)(\d)$")
# match 1.0d0
_major_minor_rev_pat = re.compile(r"^(\d+)\.(\d+)([abdf])(\d+)$")
# development, alpha, beta, final
_phase_letters = "dabf"


def split_version(verstr):
    # match 1.0.0d0
    mmbr = _major_minor_build_rev_pat.match(verstr)
    if mmbr:
        return (int(mmbr.group(1)), int(mmbr.group(2)), int(mmbr.group(3)),
                _phase_letters.find(mmbr.group(4)), int(mmbr.group(5)))
    # match 1.0
    mmo = _major_minor_pat.match(verstr)
    if mmo:
        return (int(mmo.group(1)), int(mmo.group(2)), 0, 4, 0)
    # match 1.0.0
    mmb = _major_minor_build_pat.match(verstr)
    if mmb:
        return (int(mmb.group(1)), int(mmb.group(2)),
                int(mmb.group(3)), 4, 0)
    # match 100
    mmbo = _major_minor_build_old_pat.match(verstr)
    if mmbo:
        return (int(mmbo.group(1)), int(mmbo.group(2)),
                int(mmbo.group(3)), 0, 0)
    # match 1.0d0
    mmr = _major_minor_rev_pat.match(verstr)
    if mmr:
        return (int(mmr.group(1)), int(mmr.group(2)), 0,
                _phase_letters.find(mmr.group(3)), int(mmr.group(4)))

    return (0, 0, 0, 0, 0)


def cmp_version(version1, version2):
    """compare two version string."""
    p1 = split_version(version1)
    p2 = split_version(version2)
    for part in zip(p1, p2):
        if part[0] < part[1]:
            return -1
        if part[0] > part[1]:
            return 1
    return 0


class VersionError(Exception):
    pass


class Version(object):
    """ 1.0.0d0 alike version strings
    """

    #
    # The maximum valid values for each of the version parts
    #
    MAJOR_MAX = 0xff     # 8 bits
    MINOR_MAX = 0xf      # 4 bits
    UPDATE_MAX = 0xf     # 4 bits
    BUILD_MAX = 0x3fff   # 14 bits

    #
    # The phase letters that are valid
    #
    VALID_PHASES = ['d', 'a', 'b', 'f']
    VALID_PHASES_STR = "'d', 'a', 'b' or 'f'"

    def __init__(self, verstr='1.0.0d0'):
        """
        The constructor for the Version class.

        Accepts a version string to create the version object from.
        """
        self._major = 0
        self._minor = 0
        self._update = 0
        self._phase = self.VALID_PHASES[0]
        self._build = 0
        self._parse(str(verstr))

    def get_major(self):
        return self._major

    def set_major(self, major):
        errstr = 'Major version number %d cannot be greater than %d.'
        if major > self.MAJOR_MAX:
            raise VersionError(errstr % (major, self.MAJOR_MAX))
        self._major = major

    def inc_major(self):
        self.set_major(self._major + 1)

    def get_minor(self):
        return self._minor

    def set_minor(self, minor):
        errstr = 'Minor version number %d cannot be greater than %d.'
        if minor > self.MINOR_MAX:
            raise VersionError(errstr % (minor, self.MINOR_MAX))
        self._minor = minor

    def inc_minor(self):
        self.set_minor(self._minor + 1)

    def get_update(self):
        return self._update

    def set_update(self, update):
        errstr = 'Update version number %d cannot be greater than %d.'
        if update > self.UPDATE_MAX:
            raise VersionError(errstr % (update, self.UPDATE_MAX))
        self._update = update

    def inc_update(self):
        self.set_update(self._update + 1)

    def get_phase(self):
        return self._phase

    def set_phase(self, phase):
        phase = phase.lower()
        if phase not in self.VALID_PHASES:
            errstr = "The phase '%s' is not valid. Please use %s."
            raise VersionError(errstr % (phase, self.VALID_PHASES_STR))
        self._phase = phase

    def inc_phase(self):
        if self._phase == self.VALID_PHASES[-1]:
            raise VersionError('Cannot increment phase beyond \'%s\'.' %
                               self.VALID_PHASES[-1])
        self._phase = self.VALID_PHASES[self.VALID_PHASES.index(self._phase) + 1]

    def get_build(self):
        return self._build

    def set_build(self, build):
        errstr = 'Build version number %d cannot be greater than %d.'
        if build > self.BUILD_MAX:
            raise VersionError(errstr % (build, self.BUILD_MAX))
        self._build = build

    def inc_build(self):
        self.set_build(self._build + 1)

    def _parse(self, verstr):
        """
        Internal method to parse a version string.
        """
        old_ver_pat = re.compile(r'^(\d)(\d)(\d)([dabf])(\d+)$')
        new_ver_pat = re.compile(r'^(\d+)\.(\d+)\.(\d+)([dabf])(\d+)$')
        mat = old_ver_pat.match(verstr) or new_ver_pat.match(verstr)

        # Error if we were unable to parse the string
        if mat is None:
            errstr = "Error parsing version string '%s'. " + \
                     "Please use the format '1.2.3a4'."
            raise VersionError(errstr % (verstr,))

        # Grab the values from the version string
        major = int(mat.group(1))
        minor = int(mat.group(2))
        update = int(mat.group(3))
        phase = mat.group(4).lower()
        build = int(mat.group(5))

        # Check that the phase is valid
        if phase not in self.VALID_PHASES:
            errstr = "The phase '%s' is not valid. Please use %s."
            raise VersionError(errstr % (phase, self.VALID_PHASES_STR))

        # Check that the values fall within their ranges
        errstr = '%s version number %d cannot be greater than %d.'
        if major > self.MAJOR_MAX:
            raise VersionError(errstr % ('Major', major, self.MAJOR_MAX))
        if minor > self.MINOR_MAX:
            raise VersionError(errstr % ('Minor', minor, self.MINOR_MAX))
        if update > self.UPDATE_MAX:
            raise VersionError(errstr % ('Update', update, self.UPDATE_MAX))
        if build > self.BUILD_MAX:
            raise VersionError(errstr % ('Build', build, self.BUILD_MAX))

        # Set the values for the version object
        self._major = major
        self._minor = minor
        self._update = update
        self._phase = phase
        self._build = build

    def __str__(self):
        """
        Return the version string.
        """
        return '%d.%d.%d%s%d' % (self._major,
                                 self._minor,
                                 self._update,
                                 self._phase,
                                 self._build)

    def __repr__(self):
        """
        Return a string representation of the version object.
        """
        return 'Version(%s)' % repr(str(self))

    def __cmp__(self, other):
        """
        Compare one version to another.
        """
        #
        # If the other thing is not a version object try to make it into one
        #
        try:
            if not isinstance(other, Version):
                other = Version(other)
        except VersionError:
            raise VersionError('Unable to compare %s with %s.' % \
                               (repr(self), repr(other)))

        #
        # Compare the versions
        #
        vp = self.VALID_PHASES

        return cmp(self.get_major(), other.get_major()) or \
               cmp(self.get_minor(), other.get_minor()) or \
               cmp(self.get_update(), other.get_update()) or \
               cmp(vp.index(self.get_phase()), vp.index(other.get_phase())) or \
               cmp(self.get_build(), other.get_build())


class BaseVersion(object):
    """ major.minor alike version string
    """
    #
    # The maximum valid values for each of the base version parts
    #
    MAJOR_MAX = 0xff     # 8 bits
    MINOR_MAX = 0xf      # 4 bits

    def __init__(self, verstr='1.0'):
        """
        The constructor for the BaseVersion class.

        Accepts a base version string to create the base version object from.
        """
        self._major = 0
        self._minor = 0
        self._parse(str(verstr))

    def get_major(self):
        return self._major

    def set_major(self, major):
        errstr = 'Major version number %d cannot be greater than %d.'
        if major > self.MAJOR_MAX:
            raise VersionError(errstr % (major, self.MAJOR_MAX))
        self._major = major

    def inc_major(self):
        self.set_major(self._major + 1)

    def get_minor(self):
        return self._minor

    def set_minor(self, minor):
        errstr = 'Minor version number %d cannot be greater than %d.'
        if minor > self.MINOR_MAX:
            raise VersionError(errstr % (minor, self.MINOR_MAX))
        self._minor = minor

    def inc_minor(self):
        self.set_minor(self._minor + 1)

    def _parse(self, verstr):
        """
        Internal method to parse a base version string.
        """
        old_basever_pat = re.compile(r'^(\d)(\d)0$')
        new_basever_pat = re.compile(r'^(\d+)\.(\d+)$')
        mat = old_basever_pat.match(verstr) or new_basever_pat.match(verstr)

        if mat is not None:
            # Grab the values from the base version string
            major = int(mat.group(1))
            minor = int(mat.group(2))
        else:
            # Maybe this is a version string
            try:
                ver = Version(verstr)
                major = ver.get_major()
                minor = ver.get_minor()
            except:
                # Error if we were unable to parse the string
                errstr = "Error parsing base version string '%s'. " + \
                         "Please use the format '1.2'."
                raise VersionError(errstr % (verstr,))

        # Check that the values fall within their ranges
        errstr = '%s version number %d cannot be greater than %d.'
        if major > self.MAJOR_MAX:
            raise VersionError(errstr % ('Major',  major,  self.MAJOR_MAX))
        if minor > self.MINOR_MAX:
            raise VersionError(errstr % ('Minor',  minor,  self.MINOR_MAX))

        # Set the values for the version object
        self._major = major
        self._minor = minor

    def __str__(self):
        """
        Return the base version string.
        """
        return '%d.%d' % (self._major, self._minor)

    def __repr__(self):
        """
        Return a string representation of the base version object.
        """
        return 'BaseVersion(%s)' % repr(str(self))

    def __cmp__(self, other):
        """
        Compare one base version to another.
        """
        #
        # If the other thing is not a base version obj try to make it into one
        #
        try:
            if not isinstance(other, BaseVersion):
                other = BaseVersion(other)
        except VersionError:
            raise VersionError('Unable to compare %s with %s.' % \
                               (repr(self), repr(other)))

        #
        # Compare the base versions
        #
        return cmp(self.get_major(), other.get_major()) or \
               cmp(self.get_minor(), other.get_minor())


class PackageVersion(object):
    """ 1.0.0.0-0+d0 alike version strings
    """

    #
    # The maximum valid values for each of the version parts
    #
    MAJOR_MAX = 0xff             # 8 bits
    MINOR_MAX = 0xf              # 4 bits
    UPDATE_MAX = 0xf             # 4 bits
    LOWORDERWINVER_MAX = 0xffff  # 16 bits
    BUILD_MAX = 0x3fff           # 14 bits
    ALPHA_VERSION_NUM = 0x4000   # 16384

    #
    # The phase letters that are valid
    #
    VALID_PHASES = ['d', 'a', 'b', 'f']
    VALID_PHASES_STR = "'d', 'a', 'b' or 'f'"

    def __init__(self, verstr='1.0.0.0-0+d0'):
        """
        The constructor for the Version class.

        Accepts a version string to create the version object from.
        """
        self._major = 0
        self._minor = 0
        self._update = 0
        self._loworderwinver = 0
        self._phase = self.VALID_PHASES[0]
        self._build = 0
        self._parse(str(verstr))

    def get_major(self):
        return self._major

    def set_major(self, major):
        errstr = 'Major version number %d cannot be greater than %d.'
        if major > self.MAJOR_MAX:
            raise VersionError(errstr % (major, self.MAJOR_MAX))
        self._major = major

    def inc_major(self):
        self.set_major(self._major + 1)

    def get_minor(self):
        return self._minor

    def set_minor(self, minor):
        errstr = 'Minor version number %d cannot be greater than %d.'
        if minor > self.MINOR_MAX:
            raise VersionError(errstr % (minor, self.MINOR_MAX))
        self._minor = minor

    def inc_minor(self):
        self.set_minor(self._minor + 1)

    def get_update(self):
        return self._update

    def set_update(self, update):
        errstr = 'Update version number %d cannot be greater than %d.'
        if update > self.UPDATE_MAX:
            raise VersionError(errstr % (update, self.UPDATE_MAX))
        self._update = update

    def inc_update(self):
        self.set_update(self._update + 1)

    def get_loworderwinver(self):
        return self._loworderwinver

    def set_loworderwinver(self, loworderwinver):
        errstr = 'lowOrderWindowsVersion number %d cannot be greater than %d.'
        if loworderwinver > self.LOWORDERWINVER_MAX:
            raise VersionError(errstr % (loworderwinver, self.LOWORDERWINVER_MAX))
        self._loworderwinver = loworderwinver
        self._phase = self.VALID_PHASES[loworderwinver / ALPHA_VERSION_NUM]
        self._build = loworderwinver % ALPHA_VERSION_NUM

    def inc_loworderwinver(self):
        self.set_loworderwinver(self._loworderwinver + 1)

    def get_phase(self):
        return self._phase

    def set_phase(self, phase):
        phase = phase.lower()
        if phase not in self.VALID_PHASES:
            errstr = "The phase '%s' is not valid. Please use %s."
            raise VersionError(errstr % (phase, self.VALID_PHASES_STR))
        self._phase = phase
        self._loworderwinver = self.VALID_PHASES.index(phase) * ALPHA_VERSION_NUM + self._build

    def inc_phase(self):
        if self._phase == self.VALID_PHASES[-1]:
            raise VersionError('Cannot increment phase beyond \'%s\'.' %
                               self.VALID_PHASES[-1])
        self._phase = self.VALID_PHASES[self.VALID_PHASES.index(self._phase) + 1]

    def get_build(self):
        return self._build

    def set_build(self, build):
        errstr = 'Build version number %d cannot be greater than %d.'
        if build > self.BUILD_MAX:
            raise VersionError(errstr % (build, self.BUILD_MAX))
        self._build = build
        self._loworderwinver = self.VALID_PHASES.index(self._phase) * ALPHA_VERSION_NUM + build

    def inc_build(self):
        self.set_build(self._build + 1)

    def _parse(self, verstr):
        """
        Internal method to parse a version string.
        """
        ver_pat = re.compile(r'^(\d+)\.(\d+)\.(\d+).(\d+)-0\+([dabf])(\d+)$')
        mat = ver_pat.match(verstr)

        # Error if we were unable to parse the string
        if mat is None:
            errstr = "Error parsing version string '%s'. " + \
                     "Please use the format '1.2.3.4-0+d5'."
            raise VersionError(errstr % (verstr,))

        # Grab the values from the version string
        major = int(mat.group(1))
        minor = int(mat.group(2))
        update = int(mat.group(3))
        loworderwinver = int(mat.group(4))
        phase = mat.group(5).lower()
        build = int(mat.group(6))

        # Check that the phase is valid
        if phase not in self.VALID_PHASES:
            errstr = "The phase '%s' is not valid. Please use %s."
            raise VersionError(errstr % (phase, self.VALID_PHASES_STR))

        # Check that the values fall within their ranges
        errstr = '%s version number %d cannot be greater than %d.'
        if major > self.MAJOR_MAX:
            raise VersionError(errstr % ('Major', major, self.MAJOR_MAX))
        if minor > self.MINOR_MAX:
            raise VersionError(errstr % ('Minor', minor, self.MINOR_MAX))
        if loworderwinver > self.LOWORDERWINVER_MAX:
            raise VersionError(errstr % ('LowOrderWindowsVersion', loworderwinver, self.LOWORDERWINVER_MAX))
        if update > self.UPDATE_MAX:
            raise VersionError(errstr % ('Update', update, self.UPDATE_MAX))
        if build > self.BUILD_MAX:
            raise VersionError(errstr % ('Build', build, self.BUILD_MAX))

        # Set the values for the version object
        self._major = major
        self._minor = minor
        self._update = update
        self._loworderwinver = loworderwinver
        self._phase = phase
        self._build = build

    def __str__(self):
        """
        Return the version string.
        """
        return '%d.%d.%d.%d-0+%s%d' % (self._major,
                                       self._minor,
                                       self._update,
                                       self._loworderwinver,
                                       self._phase,
                                       self._build)

    def __repr__(self):
        """
        Return a string representation of the version object.
        """
        return 'PackageVersion(%s)' % repr(str(self))

    def __cmp__(self, other):
        """
        Compare one version to another.
        """
        #
        # If the other thing is not a version object try to make it into one
        #
        try:
            if not isinstance(other, PackageVersion):
                other = PackageVersion(other)
        except VersionError:
            raise VersionError('Unable to compare %s with %s.' % \
                               (repr(self), repr(other)))

        #
        # Compare the versions
        #
        vp = self.VALID_PHASES

        return cmp(self.get_major(), other.get_major()) or \
               cmp(self.get_minor(), other.get_minor()) or \
               cmp(self.get_update(), other.get_update()) or \
               cmp(self.get_loworderwinver(), other.get_loworderwinver()) or \
               cmp(vp.index(self.get_phase()), vp.index(other.get_phase())) or \
               cmp(self.get_build(), other.get_build())
