'''
This script is to help administrator to update a bulk of records of Machine_Reimage table.

Example:
    python UpdateReimageTable.py --server 28 --machine 3101,3102,3103,3104,3105 --os 5,6,80,81,94,107 --print --testdb
'''
import os
import sys
import glob
import argparse
import ConfigParser
sys.path.append('..')
from nicu.db import init_db, SQLServerDB
import nicu.config as config
import util.dbx as dbx


args = None


def parse_args():
    '''
    process the parameters in the command line.
    '''
    parser = argparse.ArgumentParser()
    parser.add_argument("--server",
                        metavar="ServerID",
                        type=int,
                        dest="server_id",
                        help="ID of Server.",
                        required=True)
    parser.add_argument("--machine",
                        metavar="MachineID",
                        type=str,
                        dest="machine_str",
                        help="Machine IDs to update, seperated by \",\".",
                        required=True)
    parser.add_argument("--os",
                        metavar="OSID",
                        type=str,
                        dest="os_str",
                        help="OS IDs to update, seperated by \",\".",
                        required=True)
    parser.add_argument("--print",
                        action="store_true",
                        dest="just_print",
                        help="Just print which records will be updated.")
    parser.add_argument("--testdb",
                        action="store_true",
                        help="Test database will be used.")


    args = parser.parse_args()
    args.machine_ids = set(map(int, args.machine_str.split(',')))
    args.os_ids = set(map(int, args.os_str.split(',')))
    return args


def insert_reimage_record(machine_id, os_id, image_source, login_usr, login_pwd):
    '''
    Add a new reimage record to Machine_Reimage table.
    '''
    if args.just_print:
        return
    sql_str = ("insert into Machine_Reimage (MachineID,OSID,ServerID,IsVM,"
               "ImageSource,ImageSnapshot,LoginUsr,LoginPwd) values "
               "(%d, %d, %d, 1, '%s', 'CleanSnap', '%s', '%s')"
               % (machine_id, os_id, args.server_id, image_source, login_usr, login_pwd))
    SQLServerDB.execute(sql_str)
    return


def update_reimage_record(machine_id, os_id, image_source, login_usr, login_pwd):
    '''
    Update a reimage record in Machine_Reimage table.
    '''
    if args.just_print:
        return
    sql_str = ("update Machine_Reimage set ImageSource='%s',LoginUsr='%s',"
               "LoginPwd='%s' where MachineID=%d and OSID=%d"
               % (image_source, login_usr, login_pwd, machine_id, os_id))
    SQLServerDB.execute(sql_str)
    return


def get_image_info(machine_id, os_id):
    '''
    Get the image base information from the template source.
    '''
    (server_image_source,) = dbx.queryx_table('OS_Info', 'VMwareImage', 'OSID=%d' % (os_id), only_one=True)
    if not server_image_source:
        raise Exception('VMwareImage is empty for OS %d' % (os_id))
    if not os.path.exists(server_image_source):
        raise Exception('VMwareImage is inexistent for OS %d' % (os_id))

    config_path = os.path.join(server_image_source, 'config.ini')
    cf = ConfigParser.ConfigParser()
    cf.read(config_path)
    login_usr = cf.get('BasicInfo', 'Account')
    login_pwd = cf.get('BasicInfo', 'Password')

    (machine_name,) = dbx.queryx_machine_name(machine_id)
    parent_folder = os.path.basename(server_image_source)
    vmx_list = glob.glob('%s\\*.vmx' % (server_image_source))
    if len(vmx_list) == 0:
        raise Exception('Couldn\'t find .vmx file under "%s"' % (parent_folder))
    elif len(vmx_list) > 1:
        raise Exception('Multiple .vmx files exist under "%s"' % (parent_folder))
    vmx_file = os.path.basename(vmx_list[0])
    image_source = '%s\\%s\\%s\\%s' % (args.vmroot, machine_name, parent_folder, vmx_file)

    return (image_source, login_usr, login_pwd)


def update_reimage_for_machine_os(machine_id, os_id):
    '''
    Update reimage information for specified machine and os.
    '''
    msg_extra_info = "<MachineID:%d, OSID:%d>" % (machine_id, os_id)
    try:
        rows = dbx.queryx_table(
            'Machine_Reimage',
            ['ServerID', 'IsVM', 'ImageSource', 'ImageSnapshot', 'LoginUsr', 'LoginPwd'],
            'MachineID=%d and OSID=%d' % (machine_id, os_id))
        if len(rows) > 1:
            raise Exception('Multiple records')

        image_source, login_usr, login_pwd = get_image_info(machine_id, os_id)
        if len(rows) == 0:
            print('Info: Ready to insert %s' % (msg_extra_info))
            insert_reimage_record(machine_id, os_id, image_source, login_usr, login_pwd)
        else:
            (db_server_id, db_is_vm, db_image_source, db_image_snapshot, db_login_usr, db_login_pwd) =  rows[0]
            if db_server_id != args.server_id:
                raise Exception('Server ID is inconsistent <DataBase Value:%s, Input Value:%s>'
                                % (db_server_id, args.server_id))
            if not db_is_vm:
                raise Exception('IsVM is %s (Should be True)' % (str(db_is_vm)))
            if db_image_snapshot != 'CleanSnap':
                raise Exception('ImageSnapshot is %s (Should be CleanSnap)' % (str(db_image_snapshot)))

            if (image_source, login_usr, login_pwd) == (db_image_source, db_login_usr, db_login_pwd):
                print('Info: The record of %s is latest. No need to update.' % (msg_extra_info))
            else:
                print('Info: Ready to update %s' % (msg_extra_info))
                update_reimage_record(machine_id, os_id, image_source, login_usr, login_pwd)
    except Exception, error:
        print("Error: %s of %s. So ignore it." % (error, msg_extra_info))
    return


def update_reimages():
    '''
    Update reimage records as required.
    '''
    row = dbx.queryx_server_info(args.server_id)
    server_name, args.vmroot = row[0], row[-1]
    if not args.vmroot:
        print('Error: VMRoot is empty for server "%s:%s"' % (server_name, args.server_id))
        sys.exit(1)
    for machine_id in args.machine_ids:
        for os_id in args.os_ids:
            update_reimage_for_machine_os(machine_id, os_id)
    return


if __name__ == '__main__':
    args = parse_args()
    if args.testdb:
        init_db(config.DB_TEST_HOST, config.DB_TEST_USER,
                config.DB_TEST_PASSWORD, config.DB_TEST_DATABASE)
    else:
        init_db(config.DB_DEFAULT_HOST, config.DB_DEFAULT_USER,
                config.DB_DEFAULT_PASSWORD, config.DB_DEFAULT_DATABASE)
    update_reimages()
    print('Finish!')
