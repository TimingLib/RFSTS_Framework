#!/bin/bash

pid=`pidof -x ${HOME}/INCOMING/boot.sh`
if [ "$pid" != "$$" ]; then
    echo "A same process is already running. Exit!"
    exit 1
fi

echo "cd ${HOME}/INCOMING"
cd "${HOME}/INCOMING"
echo "Initiating installer script."


echo "Disable firewall"
if [ -x /sbin/SuSEfirewall2 ]; then
    sudo /sbin/SuSEfirewall2 off
else
    sudo /sbin/service iptables stop
fi

echo "Check ${HOME}/INCOMING/scriptOut.log for log file"
echo

echo "This window will close once the script has finished executing."
echo "Please wait..."

# We should only call "sudo python ./nicu/notify.py -t GhostAgent `hostname -s`" at last,
# but for virtual linux, no pymssql installed, so we use this for a workaround:
# 1) If it's a physical machine, we still use this method
# 2) If it's a virtual machine, we set Notify Server manually.

sudo perl ./BootScript.pl $1 1>>scriptOut.log 2>&1
if [ ! -f ./sendemail.flag ]; then
    sudo cp -f /mnt/cn-sha-rdfs01/RD/SAST/Installer_Services/Services/GhostAgentVDI/INCOMING/GhostNotifyEmail.py .
    sudo cp -rf /mnt/cn-sha-rdfs01/RD/SAST/Installer_Services/Services/GhostAgentVDI/nicu nicu
    sudo cp -rf /mnt/cn-sha-rdfs01/RD/SAST/Installer_Services/Services/GhostAgentVDI/util util
    sudo python ./GhostNotifyEmail.py >> GhostNotifyEmail.log 2>&1
    touch ./sendemail.flag
fi
GhostStatus=`cat ghostStatus.log`
