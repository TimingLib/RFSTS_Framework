"""This module contains miscellaneous methods
"""
from __future__ import with_statement
import os
import sys
import socket
import select
import logging
import subprocess
import itertools
import time

try: set
except NameError:
    from sets import Set as set

import errcode


logger = logging.getLogger(__name__)

__all__ = [
    "gethostipbyname",
    "execute", "remote_execute",
    "remote_execute_diff_port",
    "ping_port",
    "xjoin",
    "is_string", "is_sequence", "as_list",
    "safeunicode", "safestr", "utf8",
    "uniq",
    "dictreverse", "dictfind", "dictfindall",
    "Odict",
    "is_old_python",
    "xsleep",
    "get_info",
    "get_last_modified_time"
]


def gethostipbyname(name=None, ref_name=None):
    """
    Get the IP of machine "name".

    If name is None, returns local IP, else returns IP of name.

    If ref_name is None, it will return the nearest IP to 10.144.0.0 LAN.
    If ref_name is not None, it will return the nearest IP to LAN which
    ref_name belongs to.

    If call this function with the name of local server(not other servers),
    socket.gethostbyname() returns any one of IPs this server has.
    For example:
        1. In sh-linux-lvtest02, socket.gethostbyname(None, 'sh-linux-lvtest02')
           return '127.0.0.1'.
        2. In sast-vm-2, socket.gethostbyname(None, 'sast-vm-2')
           return '169.254.154.221'.

    So, strongly recommend to use this function without ref_name argument.
    """
    retip = None
    try:
        if not ref_name:
            ref_ip = '10.144.0.0'.split('.')
        else:
            ref_ip = socket.gethostbyname(ref_name).strip().split('.')
        # gethostbyname_ex returns (hostname, aliaslist, ipaddrlist)
        name = name or socket.gethostname()
        ipaddrlist = socket.gethostbyname_ex(name)[2]

        if len(ipaddrlist) == 1:
            return ipaddrlist[0]
        elif len(ipaddrlist) > 1:
            retweight = 0
            for ipaddr in ipaddrlist:
                ipaddrlst = ipaddr.strip().split('.')
                curweight = 0
                for i in range(4):
                   if ref_ip[i] == ipaddrlst[i]:
                      curweight += 1
                   else:
                      break
                if curweight > retweight:
                    retweight = curweight
                    retip = ipaddr
            return retip
        else:
            return None
    except socket.error, err:
        logger.error("gethostipbyname socket error : %s" % err)
        return None
    except socket.herror, err:
        logger.error("gethostipbyname socket address-related error : %s" % err)
        return None


def execute(cmd, workdir=None):
    """Execute a command with current working directory by a sub process
    """
    if workdir != None:
        os.chdir(workdir)
    p = subprocess.Popen(cmd, shell=True,
                         stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT)
    streamdata = p.communicate()[0]
    return p.returncode


def remote_execute(hostname, port, cmd, ipaddr=None,
                   isrecv=False, resbool=True, timeout=-1):
    """
    Execute a command on remote host.
    Improve this function with socket of nonblock mode,
    to make sure this function can be used in killable thread.
    """
    res = None
    recv_data = ""
    client_socket = None
    logger.info("Remote_execute: %s, %s, %s, %s" %
                (cmd, isrecv, resbool, timeout))
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if not ipaddr:
            ipaddr = gethostipbyname(hostname)
        logger.info("Execute command %s on host with IP %s" % (cmd, ipaddr))
        client_socket.connect((ipaddr, port))
        client_socket.send(cmd)
        import time
        time.sleep(1)
        client_socket.setblocking(0)
        if isrecv:
            loop_count = 0
            infds, outfds, errfds = ([], [], [])
            while not infds:
                if timeout > 0 and loop_count >= timeout:
                    raise socket.timeout()
                infds, outfds, errfds = select.select([client_socket],
                                                      [], [], 1)
                loop_count += 1
            recv_data = client_socket.recv(1024)
        res = [recv_data, True][resbool]
        logger.debug("Remote_execute Result: %s" % (res))
    except socket.timeout:
        logger.error("Timeout in remote_execute, "
                     "server<%s>, port<%s>, cmd<%s>" %
                     (hostname, port, cmd))
        res = [socket.timeout, False][resbool]
    except Exception, error:
        logger.error("%s: %s" % (error.__class__.__name__, error))
        res = [Exception(error), False][resbool]
    finally:
        if client_socket:
            client_socket.close()
    return res


def remote_execute_diff_port(hostname, port, cmd, recv_port=None,
                             ipaddr=None, timeout=-1):
    """
    Execute a command on remote host,
    and receive reply with another port(recv_port),
    If recv_port is None the port will be (client_port + 1).
    The mode of socket is also nonblock.
    """
    recv_data = ""
    client_socket = None
    server_socket = None
    connection = None
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if not ipaddr:
            ipaddr = gethostipbyname(hostname)
        logger.info("Execute command %s on host with IP %s" % (cmd, ipaddr))
        client_socket.connect((ipaddr, port))
        client_addr, client_port = client_socket.getsockname()

        #wait for response
        rep_port = recv_port or (client_port+1)
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((client_addr, rep_port))
        server_socket.listen(1)
        server_socket.setblocking(0)

        client_socket.send(cmd)

        logger.info("waiting for accept from %s:%s" %
                    (client_addr, rep_port))
        loop_count = 0
        infds, outfds, errfds = ([], [], [])
        while not infds:
            if timeout > 0 and loop_count >= timeout:
                raise socket.timeout()
            infds, outfds, errfds = select.select([server_socket],
                                                  [], [], 1)
            loop_count += 1
        (connection, address) = server_socket.accept()

        infds, outfds, errfds = ([], [], [])
        while not infds:
            if timeout > 0 and loop_count >= timeout:
                raise socket.timeout()
            infds, outfds, errfds = select.select([connection],
                                                  [], [], 1)
            loop_count += 1
        recv_data = connection.recv(1024)
        logger.debug('receive data "%s"' % (recv_data))
    except socket.timeout:
        logger.error("Timeout in remote_execute_diff_port, "
                     "server<%s>, port<%s>, cmd<%s>" %
                     (hostname, port, cmd))
        recv_data = socket.timeout
    except Exception, error:
        logger.error("%s: %s" % (error.__class__.__name__, error))
        recv_data = Exception(error)
    finally:
        if client_socket:
            client_socket.close()
        if connection:
            connection.close()
        if server_socket:
            server_socket.close()
    return recv_data


def ping_port(server, port):
    """Returns whether the server and port could be ping through"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((server, port))
        return True
    except:
        return False
    finally:
        try:
            sock.close()
        except:
            pass


def xjoin(*c):
    """Equivalent to os.path.normpath(os.path.abspath(os.path.join(*c)))"""
    return os.path.normpath(os.path.abspath(os.path.join(*c)))


def is_string(s):
    """Return True if s is a str. """
    return isinstance(s, str)


def is_sequence(seq):
    """Return True if seq is a sequence. False otherwise."""
    if is_string(seq):
        return False
    try:
        len(seq)
    except:
        return False
    return True


def as_list(seq):
    """Convert seq to a list."""
    if is_sequence(seq):
        return list(seq)
    else:
        return [seq]


# the following code are stolen from the web.py modules

def safeunicode(obj, encoding='utf-8'):
    r"""
    Converts any given object to unicode string.

        >>> safeunicode('hello')
        u'hello'
        >>> safeunicode(2)
        u'2'
        >>> safeunicode('\xe1\x88\xb4')
        u'\u1234'
    """
    t = type(obj)
    if t is unicode:
        return obj
    elif t is str:
        return obj.decode(encoding)
    elif t in [int, float, bool]:
        return unicode(obj)
    elif hasattr(obj, '__unicode__') or isinstance(obj, unicode):
        return unicode(obj)
    else:
        return str(obj).decode(encoding)


def safestr(obj, encoding='utf-8'):
    r"""
    Converts any given object to utf-8 encoded string.

        >>> safestr('hello')
        'hello'
        >>> safestr(u'\u1234')
        '\xe1\x88\xb4'
        >>> safestr(2)
        '2'
    """
    if isinstance(obj, unicode):
        return obj.encode(encoding)
    elif isinstance(obj, str):
        return obj
    elif hasattr(obj, 'next'):  # iterator
        return itertools.imap(safestr, obj)
    else:
        return str(obj)

# for backward-compatibility
utf8 = safestr


def uniq(seq, key=None):
    """
    Removes duplicate elements from a list while preserving the order of the
    rest.

        >>> uniq([9,0,2,1,0])
        [9, 0, 2, 1]

    The value of the optional `key` parameter should be a function that
    takes a single argument and returns a key to test the uniqueness.

        >>> uniq(["Foo", "foo", "bar"], key=lambda s: s.lower())
        ['Foo', 'bar']
    """
    key = key or (lambda x: x)
    seen = set()
    result = []
    for v in seq:
        k = key(v)
        if k in seen:
            continue
        seen.add(k)
        result.append(v)
    return result


def dictreverse(mapping):
    """
    Returns a new dictionary with keys and values swapped.

        >>> dictreverse({1: 2, 3: 4})
        {2: 1, 4: 3}
    """
    return dict([(value, key) for (key, value) in mapping.iteritems()])


def dictfind(dictionary, element):
    """
    Returns a key whose value in `dictionary` is `element`
    or, if none exists, None.

        >>> d = {1:2, 3:4}
        >>> dictfind(d, 4)
        3
        >>> dictfind(d, 5)
    """
    for (key, value) in dictionary.iteritems():
        if element is value:
            return key


def dictfindall(dictionary, element):
    """
    Returns the keys whose values in `dictionary` are `element`
    or, if none exists, [].

        >>> d = {1:4, 3:4}
        >>> dictfindall(d, 4)
        [1, 3]
        >>> dictfindall(d, 5)
        []
    """
    res = []
    for (key, value) in dictionary.iteritems():
        if element is value:
            res.append(key)
    return res


class Odict(dict):
    """Dictionary in which the insertion order of items is preserved"""

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self._order = self.keys()

    def __setitem__(self, key, value):
        dict.__setitem__(self, key, value)
        if key in self._order:
            self._order.remove(key)
        self._order.append(key)

    def __delitem__(self, key):
        dict.__delitem__(self, key)
        self._order.remove(key)

    def order(self):
        """Return keys in the ordered dictionary"""
        return self._order[:]

    def ordered_items(self):
        """Return keys and values in the ordered dictionary"""
        return [(key, self[key]) for key in self._order]


def is_old_python():
    """
    Judge whether the version of python interpreter is older than 2.6.
    """
    return sys.version_info < (2, 6)


def xsleep(second):
    """
    This function is used in nonblock mode instead of time.sleep,
    which can be killed.
    """
    if isinstance(second, int):
        for i in xrange(second):
            time.sleep(1)
    elif isinstance(second, float):
        interger = int(second)
        xsleep(interger)
        time.sleep(second - interger)
    else:
        raise TypeError('a float is required')
    return


def get_info(path):
    '''Get information: version, run path, status
    '''
    status = ''
    version = ''
    retval = errcode.ER_SUCCESS
    if os.path.isfile(path):
        run_path = os.path.dirname(path)
    else:
        run_path = path
    version_path = os.path.join(run_path, 'version.txt')
    if (not os.path.isfile(version_path)):
        status = 'cannot find version.txt'
        retval = errcode.ER_MISC_GET_VERSION
    else:
        try:
            with open(version_path) as fp:
                version = fp.read()
        except Exception, error:
            status = 'error in reading version.txt : %s' % error
            retval = errcode.ER_MISC_GET_VERSION

    data = version + ';' + run_path + ';' + status
    return [retval, data]


def get_last_modified_time(folder_name):
    newest = os.stat(folder_name).st_mtime
    if os.path.isdir(folder_name):
        for r, d, f in os.walk(folder_name):
            if f:
                mtimes = (os.stat(os.path.join(r, _f)).st_mtime for _f in f)
                newest = max(newest, max(mtimes))
    return newest