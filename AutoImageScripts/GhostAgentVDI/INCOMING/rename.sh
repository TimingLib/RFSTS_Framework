#!/bin/bash
# enable sudo
chmod +w /etc/sudoers
sed -i.BAK -e '/root.*ALL/a $1	ALL=(ALL)	ALL\' /etc/sudoers
sed -i -e '/\# %wheel.*NOPASSWD: ALL/c %wheel	ALL=(ALL)	NOPASSWD: ALL\' /etc/sudoers
sed -i -e '/Defaults.*requiretty/c \# Defaults    requiretty\' /etc/sudoers
chmod -w /etc/sudoers
usermod -G wheel $1

#change the hostname
if [ -e /etc/HOSTNAME -a $# -eq 2 ]; then
    sed -i.BAK -e "s/.*/$2/" /etc/HOSTNAME
    sed -i.BAK -e "s/127.0.0.1.*/127.0.0.1\t$2.localdomain\t$2/" /etc/hosts
elif [ -e /etc/hostname -a $# -eq 2 ]; then
    sed -i.BAK -e "s/.*/$2/" /etc/hostname
elif [ $# -eq 2 ]; then
    sed -i.BAK -e "s/HOSTNAME=.*/HOSTNAME=$2/" /etc/sysconfig/network
else
    echo "invalid parameter"
    exit 2
fi