#!/bin/bash
# This script should be shippled with the 'clone' step in 'ghost
# cnosole' It will first build network env, then download from file
# server all necessary files it need to build env

#mount \\cn-sha-rdfs01\RD to local folder
echo "mount //cn-sha-rdfs01.apac.corp.natinst.com/RD /mnt/cn-sha-rdfs01/RD"
sudo test -f '//cn-sha-rdfs01.apac.corp.natinst.com/RD' || sudo mkdir -p '/mnt/cn-sha-rdfs01/RD'
sudo mount -t cifs //cn-sha-rdfs01.apac.corp.natinst.com/RD /mnt/cn-sha-rdfs01/RD -o username=testfarm,password=welcome,domain=apac,ro

#change the current dir to /home/<loginusr>
cd /home/$1

#copy files from rdfs01
mkdir "./INCOMING"
cd ./INCOMING
arr=("boot.sh" "MAPDRIVES.sh" "linuxapp_installer.sh" "BootScript.pl" "StepClass.pm" "take_snapshot.sh" "TakeSnapshot.py")
for f in ${'${arr[@]}'}; do
    echo cp -f "/mnt/cn-sha-rdfs01/RD/SAST/Installer_Services/Services/GhostAgentVDI/INCOMING/${'${f}'}" "./"
    cp -f "/mnt/cn-sha-rdfs01/RD/SAST/Installer_Services/Services/GhostAgentVDI/INCOMING/${'${f}'}" "./"
done

# code for copying script.ini from rdfs01 will be appended by GhostAgent.py
# the new script.ini file will be placed under "Apply Images"/[GroupName]/[Machine Name]/"OS_ID"[OSID]/script.ini"
# when cloning a new system, this is the only one needs to be transfered to the ghosted.
sudo test -f '/mnt/mainboot' || sudo mkdir -p '/mnt/mainboot'
if [ ! -f /mnt/mainboot/script.ini ]; then
    echo cp -f "${script_ini_dir_server}/script.ini" "/mnt/mainboot/"
    sudo cp -f "${script_ini_dir_server}/script.ini" "/mnt/mainboot/"
fi

echo sudo python ./nicu/notify.py -s ${notify_server} -p ${server_port} -e GhostClient --status \"\$GhostStatus\" `hostname -s` >> boot.sh

echo Start to run boot.sh
exec ./boot.sh $1
