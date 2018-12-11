'''
This script is to help administrator to add new vmware machines for VDI.

Example:
    python AddNewVirtualMachines.py --machine 3101,3102,3103,3104,3105 --print --testdb

'''
import sys
import argparse
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
    parser.add_argument("--machine",
                        metavar="Machine",
                        type=str,
                        dest="machine_str",
                        help="Machine IDs need to add, seperated by \",\".",
                        required=True)
    parser.add_argument("--core",
                        metavar="CPUCore",
                        type=int,
                        default=4,
                        dest="cpu_core",
                        help="Number of CPU cores.")
    parser.add_argument("--freq",
                        metavar="CPUFrequency",
                        type=float,
                        default=2.53,
                        dest="cpu_freq",
                        help="Frequency of CPU (GHz).")
    parser.add_argument("--mem",
                        metavar="MemorySize",
                        type=float,
                        default=2.0,
                        dest="mem_size",
                        help="Memory Size (GB).")
    parser.add_argument("--hd",
                        metavar="HardDiskSize",
                        type=float,
                        default=300.0,
                        dest="hd_size",
                        help="Hard Disk Size (GB).")
    parser.add_argument("--print",
                        action="store_true",
                        dest="just_print",
                        help="Just print which records will be added.")
    parser.add_argument("--testdb",
                        action="store_true",
                        help="Test database will be used.")

    args = parser.parse_args()
    args.machine_ids = set(map(int, args.machine_str.split(',')))
    if filter(lambda x: x >3999 or x < 3000, args.machine_ids):
        print('Error: Machine ID must be among 3000~3999.')
        sys.exit(1)
    return args


def insert_machine_info_record(machine_id, machine_name, cpu_core, cpu_freq, mem_size, hd_size):
    '''
    Insert a new record to Machine_Info table.
    Default OS is Win 7 64-bit.
    '''
    if args.just_print:
        return
    sql_str = ("insert into Machine_Info (MachineID,MachineName,GroupID,"
               "MachineModel,CPUModel,CPUCore,CPUFrequency,MemorySize,"
               "HardDiskSize,HardwareIDList,StartTime,ExpireTime,ServiceID,"
               "Owner,CurrentOSID,CurrentSeqID,Comment,MachineIP,MacAddress)"
               "  values (%d, '%s', 1, 'VMware Virtual Platform', 'Intel',"
               " %d, %f, %f, %f, NULL, NULL, GETDATE(), NULL, NULL, 6, NULL,"
               " NULL, NULL, NULL)"
               % (machine_id, machine_name, cpu_core, cpu_freq, mem_size, hd_size))
    SQLServerDB.execute(sql_str)
    return


def add_machines():
    '''
    Add machines to Machine_Info table, as required.
    If machine already exist in Machine_Info, it will display an error to administrators.
    '''
    for machine_id in args.machine_ids:
        machine_name = 'sh-rd-vmtest%02d' % (machine_id-3000)
        machine_info = "%s:%s" % (machine_id, machine_name)
        try:
            rows = dbx.queryx_table('Machine_Info', 'MachineID',
                "MachineID=%d or MachineName='%s'" % (machine_id, machine_name))
            if rows:
                print('Error: Already exist record for machine "%s"' % (machine_info))
                continue
            print('Info: Ready to add machine "%s"' % (machine_info))
            insert_machine_info_record(machine_id, machine_name, args.cpu_core,
                args.cpu_freq, args.mem_size, args.hd_size)
        except Exception, error:
            print('Error: Failed to add machine "%s": %s' % (machine_info, error))
    return


if __name__ == '__main__':
    args = parse_args()
    if args.testdb:
        init_db(config.DB_TEST_HOST, config.DB_TEST_USER,
                config.DB_TEST_PASSWORD, config.DB_TEST_DATABASE)
    else:
        init_db(config.DB_DEFAULT_HOST, config.DB_DEFAULT_USER,
                config.DB_DEFAULT_PASSWORD, config.DB_DEFAULT_DATABASE)
    add_machines()
    print('Finish!')
