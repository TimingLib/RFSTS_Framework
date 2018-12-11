import sys
import time
import socket
import platform
import ConfigParser

# Configuration for ini
_G_INI_FILE = './script.ini'
if platform.system() == "Linux":
    _G_INI_FILE = '/mnt/mainboot/script.ini'

srv_host = None
srv_port = 8123
sock = None

try:
    script_ini = ConfigParser.ConfigParser()
    script_ini.readfp(open(_G_INI_FILE))
    srv_host = script_ini.get("updateosstatus", "host")
    message = script_ini.get("updateosstatus", "message")
    (machine_id, os_id) = message.split(' ')[1:3]
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((srv_host, srv_port))
    cmd_line = r'TakeSnapshot "%s" %s %s' % (sys.argv[1], machine_id, os_id)
    print "Send cmd[%s] to [%s:%s]" % (cmd_line, srv_host, srv_port)
    sock.send(cmd_line)
    print "Take snapshot finished"
    time.sleep(30)
except Exception, e:
    print "Error when take snapshot: " % e
finally:
    sock.close()
