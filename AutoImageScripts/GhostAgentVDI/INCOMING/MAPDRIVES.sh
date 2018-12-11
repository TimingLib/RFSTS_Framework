#!/bin/bash

mount_user='testfarm'
mount_pass='welcome'
mount_domain='apac'

MAPLIST="//cn-sha-rdfs04.apac.corp.natinst.com/ExportMirror;/mnt/cn-sha-rdfs04/ExportMirror
//cn-sha-rdfs04.apac.corp.natinst.com/NIInstallers;/mnt/cn-sha-rdfs04/NIInstallers
//cn-sha-rdfs01.apac.corp.natinst.com/RD;/mnt/cn-sha-rdfs01/RD
//cn-sha-rdfs01.apac.corp.natinst.com/AutoTestData;/mnt/cn-sha-rdfs01/AutoTestData
//cn-sha-rdfs01.apac.corp.natinst.com/NIInstallers-Released;/mnt/cn-sha-rdfs01/NIInstallers-Released
//cn-sha-nas1.ni.corp.natinst.com/NISoftwarePrerelease;/mnt/cn-sha-argo/NISoftwarePrerelease
//cn-sha-nas1.ni.corp.natinst.com/NISoftwareReleased;/mnt/cn-sha-argo/NISoftwareReleased
"

echo 'Delay 20s to ensure network started'
sleep 20s

echo 'Mapping Network Drives'
for line in ${MAPLIST}
do
	smb_path=`echo ${line} | awk -F";" '{print $1}'`
	mnt_point=`echo ${line}| awk -F";" '{print $2}'`
	echo 'Try deleting previously mapped drive (if it exists)' "${mnt_point}"
	test -f "${mnt_point}" && umount "${mnt_point}"
	echo "Mapping ${smb_path} to ${mnt_point}"
	test -f "${mnt_point}" || mkdir -p "${mnt_point}"
	mount -t cifs -o domain="${mount_domain}",user="${mount_user}",password="${mount_pass}" "${smb_path}" "${mnt_point}"
	ret=$?
	[ $ret -eq 0 ] || echo "Maping ${smb_path} error = " "${ret}"
done

#mainboot='/mnt/mainboot'
#echo "Mount main os /boot to ${mainboot}"
#test -f "${mainboot}" || mkdir -p "${mainboot}"
#mount -t ext2 '/dev/sda1'  "${mainboot}"
#ret=$?
#[ $ret -eq 0 ] || echo "Mounting main os error = " "${ret}"

echo ''


