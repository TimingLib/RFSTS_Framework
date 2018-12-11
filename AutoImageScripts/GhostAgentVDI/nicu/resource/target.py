import logging
from datetime import datetime
from datetime import timedelta
import nicu.db as db
import nicu.errcode as errcode

__all__ = [
    'Target'
]

LOGGER = logging.getLogger(__name__)

_TARGET_INFO_COLS = [
    'Target_ID',
    'Target_Name',
    'Target_UserName',
    'Target_Password',
    'Target_Status',
    'Target_LocalAdmin',
    'Target_Note',
    'Target_Manufacturer',
    'Target_CurrentUser',
    'Target_StartDate',
    'Target_ExpectUnlockDate',
    'Target_Pic',
    'Module_Board',
    'Target_Family',
    'Target_Type',
    'Target_Controller'
]

_TARGET_ADDR_COLS = [
    'Target_ID',
    'Target_Mac',
    'Target_IP'
]


class Target:
    '''
    This class can be used to manage all the target resouces.
        1. get_target_info()
        2. set_target_info()
        3. checkout_target()
        4. release_target()
    '''

    def __init__(self, target_id):
        self.target_id = target_id
        ret_val = 0
        try:
            sql_query = ("select count(*) from Target_Farm where "
                         "Target_ID='%s';" % target_id)
            [(ret_val,)] = db.run_query_sql(sql_query)
        except Exception, e:
            LOGGER.error('Target Init failed: %s' % e)
        if ret_val == 0:
            raise Exception('No such target')

    def get_target_info(self):
        '''
        Get the target information
        '''
        target_info = None
        info_cols = ','.join(_TARGET_INFO_COLS)
        info_query = ("select %s from Target_Farm where Target_ID='%s'" %
                      (info_cols, self.target_id))
        try:
            results = db.run_query_sql(info_query)
            if results:
                target_info = dict(zip(_TARGET_INFO_COLS, results[0]))
        except Exception, e:
            LOGGER.error('[get_target_info] Get Target Info '
                         'failed: %s' % e)
        return target_info

    def set_target_info(self, info={}, **args):
        '''
        This function can update the target information in database

        parameter:
            info:
                the dict of the target info to update
            example: {
                'Target_ID': '1',
                'Target_Name': 'ni-crio9082-serviceteam',
                'Target_UserName': 'admin',
                'Target_Password': None,
                'Target_Status': 0,
                'Target_LocalAdmin': '475c4e8b-002f-44ec-aab5-2d9bd0186a83',
                'Target_Note': None,
                'Target_Manufacturer': None,
                'Target_CurrentUser': None,
                'Target_StartDate': '2014-08-05 11:35:00',
                'Target_ExpectUnlockDate': datetime(2014, 8, 6, 11, 35, 10),
                'Target_Pic': '~/Images/NI cRIO-9082.png',
                'Module_Board': 'NI cRIO-9082 "RIO0" : rio://NI-cRIO9082-2F15
                                2939/RIO0',
                'Target_Family': 1,
                'Target_Type': 0,
                'Target_Controller': 9082
            }
            args:
                set the target info
                If you set the parameter in args like Target_ID=0, the
                Target_ID in info will be replaced by 0.
        '''
        ret_code = errcode.ER_FAILED
        try:
            info_update = "update Target_Farm set %s where Target_ID='%d'"
            info = dict(info)
            for item in args:
                if item in _TARGET_INFO_COLS:
                    info[item] = args[item]
            if not info:
                raise Exception('No target info is set')
            info_datas = []
            for (key, val) in info.items():
                if val and isinstance(val, datetime):
                    val = val.strftime('%Y-%m-%d %H:%M:%S')
                info_datas.append("%s='%s'" % (key, val))
            info_update = info_update % (','.join(info_datas), self.target_id)
            info_update = info_update.replace("='None'", '=NULL')
            ret_code = db.run_action_sql(info_update)
        except Exception, e:
            LOGGER.error('[set_target_info] Set target information '
                         'failed: %s' % e)
        return ret_code

    def get_target_addr(self):
        '''
        Get target Mac&IP address from database
        '''
        target_addr = []
        addr_cols = ','.join(_TARGET_ADDR_COLS)
        addr_query = ("select %s from TargetAddressInfo where "
                      "Target_ID='%s'" % (addr_cols,
                                          self.target_id))
        try:
            results = db.run_query_sql(addr_query)
            for result in results:
                target_addr.append(dict(zip(_TARGET_ADDR_COLS, result)))
        except Exception, e:
            LOGGER.error('[get_target_addr] Get target information '
                         'failed: %s' % e)
        return target_addr

    def set_target_addr(self, target_mac, **args):
        '''
        This function can update the target address in database
            args: Target_ID=1
                  Target_Mac='00:80:2F:15:29:39'
                  Target_IP='10.144.20.119'
            Target_Mac can't be set to NULL, because it's PK
            of the table.
        '''
        ret_code = errcode.ER_FAILED
        try:
            sql_query = ("select COUNT(*) from TargetAddressInfo where "
                         "Target_ID='%d' and Target_Mac='%s';" %
                         (self.target_id, target_mac))
            results = db.run_query_sql(sql_query)
            addr_update = ("update TargetAddressInfo set %s where "
                           "Target_Mac='%s'")
            addr_datas = []
            if results:
                for (key, val) in args.items():
                    if key in _TARGET_ADDR_COLS:
                        addr_datas.append("%s='%s'" % (key, val))
                    else:
                        raise Exception('Invalid parameter: (%s, %s)' % (key,
                                                                         val))
                if not addr_datas:
                    return ret_code
                addr_update = addr_update % (','.join(addr_datas), target_mac)
            else:
                raise Exception('Unknown Target Address')
            addr_update = addr_update.replace("='None'", '=NULL')
            ret_code = db.run_action_sql(addr_update)
        except Exception, e:
            LOGGER.error('[set_target_addr] Set target address '
                         'failed: %s' % e)
        return ret_code

    def checkout_target(self, user=None, reserve_time=1):
        '''
        Checkout the target.
        '''
        ret_code = errcode.ER_FAILED
        try:
            sql_query = ("select Target_Status from Target_Farm where "
                         "Target_ID='%s'" % self.target_id)
            ret_val = db.run_query_sql(sql_query)
            if ret_val[0][0] == 0:
                sql_update = ("update Target_Farm set Target_Status=1, "
                              "Target_StartDate=GETDATE(), "
                              "Target_ExpectUnlockDate=DATEADD(HH, %s, "
                              "GETDATE()), Target_CurrentUser='%s' where "
                              "Target_ID='%s' and Target_Status=0;" %
                              (reserve_time, user, self.target_id))
                ret_code = db.run_action_sql(sql_update.replace("='None'", '=NULL'))
        except Exception, e:
            LOGGER.error('[checkout_target] Checkout target failed: %s' % e)
        return ret_code

    def release_target(self):
        '''
        Release a target with the given ID
        '''
        ret_code = errcode.ER_FAILED
        try:
            reserve_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sql_update = ("update Target_Farm set Target_Status=0, "
                          "Target_CurrentUser=NULL, "
                          "Target_ExpectUnlockDate='%s' where "
                          "Target_ID='%s'" % (reserve_time, self.target_id))
            ret_code = db.run_action_sql(sql_update)
        except Exception, e:
            LOGGER.error('[release_target] Release target failed: %s' % e)
        return ret_code
