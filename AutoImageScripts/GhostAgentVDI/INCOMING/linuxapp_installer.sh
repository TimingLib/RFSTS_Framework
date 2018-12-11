#!/bin/bash

function install_p4 {
    dst=./p4
    if [ $# -ne 0 ]; then
        dst=$1
    fi
    curl -L -o $dst  -s http://www.perforce.com/downloads/perforce/r10.1/bin.macosx104u/p4 &&
    chmod +x $dst
}

function uninstall_p4 {
    dst=./p4
    if [ $# -ne 0 ]; then
        dst=$1
    fi
    rm $dst
}

function get_latest_path {
    local _path="`ls -t "${1}" | grep -v "^\." | head -1`"
    echo "${_path}"
}

function get_latest_file_path {
    local _basepath="$1"
    local _suffixpath="$2"
    local _latestpath=$(get_latest_path "$1")
    local _latestfilepath="$_basepath/$_latestpath"
    if [ -n "$_suffixpath" ]; then
        _latestfilepath=$(echo "$_latestfilepath"/$_suffixpath)
    fi
    echo "${_latestfilepath}"
}

function install_pkg {
    if [ $# -ne 3 ]; then
        echo "parameters error"
        echo "usage: install_pkg pkg_path installcmd flags"
        exit
    fi
    local _folder_path="$1"
    local _installcmd="$2"
    local _flags="$3"

    echo "try to execute ${_installcmd} under ${_folder_path}"
    cd "${_folder_path}" &&
    echo ${_installcmd} ${_flags} &&
    ${_installcmd} ${_flags}
}

function install_tar_gz {
    if [ $# -ne 3 ]; then
        echo "parameters error"
        echo "usage: install_tar_gz targz_path installcmd flags"
        exit
    fi
    local _targz_path="$1"
    local _installcmd="$2"
    local _flags="$3"

    local _tmpdir=`mktemp -d`
    echo "try to extract the installer ${_targz_path} to ${_tmpdir}"
    cd "${_tmpdir}" &&
    tar zxf "${_targz_path}" &&
    echo ${_installcmd} ${_flags} &&
    ${_installcmd} ${_flags}
}

function install_iso {
    if [ $# -ne 4 ]; then
        echo "parameters error"
        echo "usage: install_iso iso_path mount_point installcmd flags"
        exit
    fi
    local _iso_path="$1"
    local _mount_point="$2"
    local _installcmd="$3"
    local _flags="$4"

    echo "try to mount ${_iso_path}"
	test -f "${_mount_point}" || mkdir -p "${_mount_point}"
    echo mount -o loop "${_iso_path}" "${_mount_point}"
    mount -o loop "${_iso_path}" "${_mount_point}" &&
    cd "${_mount_point}" &&
    echo ${_installcmd} ${_flags} &&
    ${_installcmd} ${_flags}
}

function install_latest {
    if [ $# -ne 4 ]; then
        echo "parameters error"
        echo "usage: install_latest base_path suffixpath installcmd flags"
        exit
    fi
    local _latest_full_path=$(get_latest_file_path "$1" "$2")
    install_pkg "${_latest_full_path}" "$3" "$4"
}

function install_latest_tar_gz {
    if [ $# -ne 5 ]; then
        echo "parameters error"
        echo "usage: install_latest_tar_gz base_path suffixpath targzfile installcmd flags"
        exit
    fi
    local _suffixpath="$2/$3"
    [ -z "$2" ] && _suffixpath="$3"
    local _latest_full_path=$(get_latest_file_path "$1" "${_suffixpath}")
    install_tar_gz "${_latest_full_path}" "$4" "$5"
}


echo "$@"
"$@"

