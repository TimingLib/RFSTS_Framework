import subprocess
import time
import os
import string

while True:
    param = os.environ['SLAVE']
    command = "ping -n 1" + " " + param
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    out, err = process.communicate()
    ret = process.returncode
    print("ret=%s" % ret)
    print("out=%s" % out)
    print("err=%s" % err)
    if ('unreachable' in out) or ret != 0:
        print(os.environ['SLAVE']+ " is down")
        break
    else:
        time.sleep(10)
exitcode = "exit 0"
process = subprocess.Popen(exitcode, shell = True)