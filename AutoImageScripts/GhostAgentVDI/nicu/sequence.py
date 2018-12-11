import os
import time
import logging

import nicu.path as path
from nicu.db import SQLServerDB
from nicu.config import DB_LEN_SEQ_NAME, DB_LEN_SEQ_DESC, DB_LEN_STEP_DESC


__all__ = [
    "StackType",
    "split_str",
    "join_str",
    "get_stack_product_id",
    "get_stack_schema_id",
    "get_stack_id",
    "find_stack_info",
    "get_stack_step_ids",
    "insert_step",
    "insert_seq",
    "gen_new_seq",
    "get_steps_info",
    "is_equivalent_seq",
    "is_equivalent_step"
]

LOGGER = logging.getLogger(__name__)


class StackType:
    '''
    Stack Installer Type:
        #. Latest Stack Installer
        #. Latest Healthy Stack Installer
        #. Custom Stack Installer
    '''
    NONE_STACK_TYPE = 0         # Non Stack Installer
    LASTEST_TYPE = 1            # Latest Stack Installer
    LASTEST_HEALTHY_TYPE = 2    # Latest Healthy Stack Installer
    CUSTOM_TYPE = 3             # Custom Stack Installer

    @classmethod
    def is_stack(cls, stack_type):
        return stack_type != StackType.NONE_STACK_TYPE

    @classmethod
    def is_lastest_stack(cls, stack_type):
        return stack_type == StackType.LASTEST_TYPE

    @classmethod
    def is_lastest_healthy_stack(cls, stack_type):
        return stack_type == StackType.LASTEST_HEALTHY_TYPE

    @classmethod
    def is_custom_stack(cls, stack_type):
        return stack_type == StackType.CUSTOM_TYPE

    @classmethod
    def is_dynamic_stack(cls, stack_type):
        return StackType.is_lastest_stack(stack_type) \
            or StackType.is_lastest_healthy_stack(stack_type)

    @classmethod
    def desr2type(cls, desr):
        if desr.startswith('SWStack Template '):
            stack_type = StackType.LASTEST_TYPE
        elif desr.startswith('SWStack Healthy Template '):
            stack_type = StackType.LASTEST_HEALTHY_TYPE
        elif desr.startswith('SWStack '):
            stack_type = StackType.CUSTOM_TYPE
        else:
            stack_type = StackType.NONE_STACK_TYPE
        return stack_type


def _is_subset(sublist, totallist):
    return set(sublist).issubset(set(totallist))


def split_str(string):
    return [int(x.strip()) for x in string.split(',')]


def join_str(ints):
    return ','.join([str(x) for x in ints])


def get_stack_product_id(step_id=None, basepath=None):
    assert(step_id or basepath)
    if step_id:
        sql_str = "select BasePath from GhostSteps where StepID=%s" % (step_id)
        (basepath,) = SQLServerDB.query_one(sql_str)
        return get_stack_product_id(basepath=basepath)
    else:
        sql_str = "select ProductID, BasePath from StackValidation_ProductInfo"
    product_id = None
    rows = SQLServerDB.query(sql_str)
    for row in rows:
        if row[1] and row[1].strip() and basepath.startswith(row[1].strip()):
            product_id = row[0]
            break
    return product_id


def get_stack_schema_id(product_ids):
    schema_id = None
    schema_product_ids = None
    sql_str = "select SchemaID, SchemaList from StackSchema where Name not like '%obsolete%'"
    schema_infos = SQLServerDB.query(sql_str)
    for schema_info in schema_infos:
        cur_product_ids = split_str(schema_info[1])
        if _is_subset(product_ids, cur_product_ids):
            if not schema_id or len(cur_product_ids) < len(schema_product_ids):
                schema_id = schema_info[0]
                schema_product_ids = cur_product_ids
    return schema_id


def get_stack_id(schema_id, product_ids, stack_type):
    stack_id = None
    if not StackType.is_dynamic_stack(stack_type):  # if it's not a stack
        return stack_id
    if StackType.is_lastest_stack(stack_type):  # if it's a lastest stack
        sql_str = ("select StackID from StackValidation_StackInfo"
                   " where SchemaID=%s order by StackName desc" % (schema_id))
        (stack_id,) = SQLServerDB.query_one(sql_str)
        return stack_id

    # if it's a latest healthy stack
    while True:
        cur_max_stack_name = time.strftime('%Y%m%d_%H%M',
                                           time.localtime(time.time()))
        # in order to avoid querying too many time,
        # or query too much data one time.
        sql_str = ("select top 50 StackID, StackName, ComponentList from"
                   " StackValidation_StackInfo where SchemaID=%s"
                   " and StackName <= '%s' order by StackName desc"
                   % (schema_id, cur_max_stack_name))
        stack_infos = SQLServerDB.query(sql_str)
        if not stack_infos:
            # if no latest healthy stack installer,
            # instead, use the latest stack installer.
            return get_stack_id(schema_id, product_ids, StackType.LASTEST_TYPE)

        for stack_info in stack_infos:
            sql_str2 = ("select count(*) from StackValidation_ComponentInfo"
                        " where ComponentID in (%s) and ProductID in (%s)"
                        " and HealthyLevel >= 3"
                        % (stack_info[2], join_str(product_ids)))
            (count, ) = SQLServerDB.query_one(sql_str2)
            if len(product_ids) == count:
                stack_id = stack_info[0]
                break

        if stack_id:
            break
        cur_max_stack_name = stack_infos[-1][1]
    return stack_id


def find_stack_info(step_ids):
    '''
    Get stack type and products based on step id list.
    '''
    stack_type = StackType.NONE_STACK_TYPE
    product_ids = []
    sql_str_temp = ("select Description, Type, LatestInstaller from GhostSteps"
                    " where StepID=%s")
    for i, step_id in enumerate(step_ids):
        step_info = SQLServerDB.query_one(sql_str_temp % step_id)
        if step_info[1] != 1:
            continue
        cur_stack_type = StackType.desr2type(step_info[0])
        if StackType.is_stack(cur_stack_type):
            if StackType.is_stack(stack_type) \
                    and stack_type != cur_stack_type:
                raise Exception('Different types of stack are not allowed'
                                ' coexist in one sequence')
            elif (StackType.is_dynamic_stack(cur_stack_type)
                    and step_info[2] == 1) \
                or (StackType.is_custom_stack(cur_stack_type)
                    and step_info[2] == 0):
                stack_type = cur_stack_type
                product_id = get_stack_product_id(step_id=step_id)
                product_ids.append(product_id)
    return [stack_type, product_ids]


def get_stack_step_ids(stack_id, product_ids=None):
    '''
    Get step ids in this stack based on products needed.
    If `product_ids` is `None`, select all steps.
    Steps must be sorted according to products.
    '''
    step_ids = []
    sql_str = ("select ComponentList from StackValidation_StackInfo"
               " where StackID=%s" % (stack_id))
    (component_id_str, ) = SQLServerDB.query_one(sql_str)
    sql_str = ("select ComponentID, ProductID, StepID from"
               " StackValidation_ComponentInfo where ComponentID in (%s)"
               % (component_id_str))
    if product_ids is None:
        steps_info = SQLServerDB.query(sql_str)
        for step_info in steps_info:
            (component_id, product_id, step_id) = step_info
            if step_id == -1:
                # step id should not be -1
                raise Exception('Stack %s Product %s:%s has no corresponding'
                                ' step' % (stack_id, product_id, component_id))
            step_ids.append(step_id)
    else:
        sql_str += " and ProductID in (%s)" % (join_str(product_ids))
        steps_info = SQLServerDB.query(sql_str)
        for product_id in product_ids:
            step_id = None
            component_id = None
            for step_info in steps_info:
                if step_info[1] == product_id:
                    component_id = step_info[0]
                    step_id = step_info[2]
                    break
            if step_id is None:
                raise Exception('Stack %s Product %s has no corresponding'
                                ' component' % (stack_id, product_id))
            elif step_id == -1:
                # step id should not be -1
                raise Exception('Stack %s Product %s:%s has no corresponding'
                                ' step' % (stack_id, product_id, component_id))
            step_ids.append(step_id)
    return step_ids


def insert_step(step_info):
    new_step_id = None
    try:
        sql_str = "select max(StepID) from GhostSteps"
        (new_step_id, ) = SQLServerDB.query_one(sql_str)
        new_step_id += 1
        sql_str = ("insert into GhostSteps values(%s, '%s', %s, '%s', '%s',"
                   " '%s', '%s', %s, %s, %s, '%s', %s, '%s')"
                   % (new_step_id, step_info[1], step_info[2], step_info[3],
                      step_info[4], step_info[5], step_info[6],
                      int(step_info[7]), int(step_info[8]), int(step_info[9]),
                      step_info[10], step_info[11], step_info[12]))
        sql_str = sql_str.replace("'None'", "NULL").replace("None", "NULL")
        res = SQLServerDB.execute(sql_str)
        if res != 0:
            raise Exception('SQLServerDB execute return %s' % (res))
    except Exception, error:
        new_step_id = None
        LOGGER.error('Failed to insert a temporary step for step %s: %s'
                     % (step_info[0], error))
    return new_step_id


def insert_seq(seq_info):
    new_seq_id = None
    try:
        sql_str = "select max(SeqID) from GhostSequences"
        (new_seq_id, ) = SQLServerDB.query_one(sql_str)
        new_seq_id += 1
        sql_str = ("insert into GhostSequences values(%s, '%s', %s, '%s',"
                   " '%s', %s, %s, '%s', %s)"
                   % (new_seq_id, seq_info[1], seq_info[2], seq_info[3],
                      seq_info[4], int(seq_info[5]), seq_info[6],
                      seq_info[7], seq_info[8]))
        sql_str = sql_str.replace("'None'", "NULL").replace("None", "NULL")
        res = SQLServerDB.execute(sql_str)
        if res != 0:
            raise Exception('SQLServerDB execute return %s' % (res))
    except Exception, error:
        new_seq_id = None
        LOGGER.error('Failed to insert a temporary sequence for sequence'
                     ' %s: %s' % (seq_info[0], error))
    return new_seq_id


def gen_new_seq(seq_id, force=False, throw_exception=False):
    '''
    Base on the original sequence id, generate a new sequence.
    If any step in this sequence has dynamic path or force is True,
    return a new sequence id. Otherwise, return original sequence id.
    '''
    if seq_id is None or seq_id == -1:
        return seq_id

    new_step_ids = []
    new_seq_id = None

    try:
        sql_str = ("select Sequence from GhostSequences"
                   " where SeqID=%s" % (seq_id))
        seq_info = SQLServerDB.query_one(sql_str)
        step_ids = split_str(seq_info[0])

        # First, scan all steps, to get all steps related to stack if exists.
        stack_step_ids = []
        stack_step_index = 0
        (stack_type, product_ids) = find_stack_info(step_ids)
        if StackType.is_dynamic_stack(stack_type):
            schema_id = get_stack_schema_id(product_ids)
            stack_id = get_stack_id(schema_id, product_ids, stack_type)
            stack_step_ids = get_stack_step_ids(stack_id, product_ids)

        # Second, rescan all steps, replace all stack steps and daily
        # installers with fixed path.
        # If exists any daily installer, need to create new steps.
        # This new steps couldn't be deleted automatically, so we use special
        # description to mark them, for more convenient removing manually.
        sql_str_temp = ("select Description, Type, LatestInstaller from"
                        " GhostSteps where StepID=%s")
        for i, step_id in enumerate(step_ids):
            step_info = SQLServerDB.query_one(sql_str_temp % step_id)
            if step_info[1] != 1 or step_info[2] != 1:
                new_step_ids.append(step_id)
                continue
            # if this is a stack step
            if StackType.is_dynamic_stack(StackType.desr2type(step_info[0])):
                new_step_ids.append(stack_step_ids[stack_step_index])
                stack_step_index += 1
                continue
            # otherwise, this is a daily installer
            sql_str = ("select StepID, Description, Type, Command, Flags,"
                       " BasePath, PathSuffix, LatestInstaller,"
                       " SleepUntilReboot, AlwaysRun, NotifierHost,"
                       " NotifierPort, NotifierMsg from GhostSteps"
                       " where StepID=%s" % (step_id))
            daily_step_info = SQLServerDB.query_one(sql_str)
            # Maybe it's a linux/mac daily installer
            # We don't process any non-windows daily installer
            if daily_step_info[3] and daily_step_info[3].lower() != 'setup.exe':
                new_step_ids.append(step_id)
                continue
            new_step_info = list(daily_step_info)
            lastest_path = path.get_latest_installer(new_step_info[5])
            if not lastest_path:
                raise Exception('Failed to get latest path of "%s"'
                                % (new_step_info[5]))
            step_desc = 'NicuTempStep ' + new_step_info[1]
            new_step_info[1] = step_desc[:DB_LEN_STEP_DESC]
            new_step_info[5] = os.path.join(lastest_path, new_step_info[6].lstrip('\\'), '')
            new_step_info[6] = '\\'
            new_step_info[7] = False

            new_step_id = insert_step(new_step_info)
            if new_step_id is None:
                raise Exception('Failed to insert a temporary step')
            new_step_ids.append(new_step_id)

        if new_step_ids == step_ids and not force:
            return seq_id

        sql_str = ("select SeqID, SeqName, GroupID, Description, Sequence,"
                   " IsPublic, PrimaryStep, OSPlatform, Product from"
                   " GhostSequences where SeqID=%s" % (seq_id))
        seq_info = SQLServerDB.query_one(sql_str)
        new_seq_info = list(seq_info)
        new_seq_info[1] = ('NicuTempSeq ' + new_seq_info[1])[:DB_LEN_SEQ_NAME]
        new_seq_info[3] = ('NicuTempSeq ' + new_seq_info[3])[:DB_LEN_SEQ_DESC]
        new_seq_info[4] = join_str(new_step_ids)
        new_seq_info[5] = False
        new_seq_id = insert_seq(new_seq_info)
        if new_seq_id is None:
            raise Exception('Failed to insert a temporary sequence')
        LOGGER.info('Generate a new temporary sequence %s for sequence %s'
                    % (new_seq_id, seq_id))
    except Exception, error:
        if throw_exception:
            raise Exception(error)
        new_seq_id = None
        LOGGER.error('Failed to generate a temporary sequence for sequence'
                     ' %s: %s' % (seq_id, error))
    return new_seq_id


def is_equivalent_seq(seq_id1, seq_id2):
    '''
    Compare whether two sequences has the equivalent steps.
    '''
    try:
        if seq_id1 == seq_id2:
            return True
        if seq_id1 in (None, '', -1, '-1') and seq_id2 in (None, '', -1, '-1'):
            return True
        sql_str = ("select SeqID, Sequence from GhostSequences where SeqID in (%s,%s)"
                   % (seq_id1, seq_id2))
        rows = SQLServerDB.query(sql_str)
        if len(rows) != 2:
            return False
        step_ids_str1, step_ids_str2 = rows[0][1], rows[1][1]
        if str(seq_id1) != str(rows[0][0]):
            step_ids_str1, step_ids_str2 = step_ids_str2, step_ids_str1
        # None and empty string is equivalent here.
        if not step_ids_str1 or not step_ids_str2:
            return not step_ids_str1 and not step_ids_str2
        step_ids1 = [int(x.strip()) for x in step_ids_str1.split(',') if x.strip()]
        step_ids2 = [int(x.strip()) for x in step_ids_str2.split(',') if x.strip()]
        if len(step_ids1) != len(step_ids2):
            return False
        for step_id1, step_id2 in zip(step_ids1, step_ids2):
            if not is_equivalent_step(step_id1, step_id2):
                return False
    except Exception:
        return False
    return True


def get_steps_info(step_ids):
    '''
    Get information of steps.
    '''
    if isinstance(step_ids, int):
        step_ids = [step_ids]
    steps_info = {}
    try:
        step_ids_str = ','.join([str(x) for x in step_ids])
        step_cols = ['StepID', 'Description', 'Type', 'Command', 'Flags', 'BasePath',
            'PathSuffix', 'LatestInstaller', 'SleepUntilReboot', 'AlwaysRun']
        step_cols_str = ','.join(step_cols)
        sql_str = 'select %s from GhostSteps where StepID in (%s)' % (
            step_cols_str, step_ids_str)
        rows = SQLServerDB.query(sql_str)
        for row in rows:
            step_id = row[0]
            steps_info[step_id] = {}
            for index, col in enumerate(step_cols[1:]):
                steps_info[step_id][col] = row[index + 1]
    except Exception:
        steps_info = {}
    return steps_info


def _is_windows_path(path_arg):
    '''
    Judge whether the given path is a windows path.
    '''
    return path_arg and (path_arg.startswith(r'\\') or path_arg.find(':') == 1)


def _compare_string(str1, str2, is_case_sensitive):
    '''
    Compare two string. None and empty string is equivalent here.
    '''
    if not str1 or not str2:
        return not str1 and not str2
    if is_case_sensitive:
        return str1 == str2
    return str1.lower() == str2.lower()


def is_equivalent_step(step_id1, step_id2):
    '''
    Compare whether two steps has the equivalent commands.
    '''
    if step_id1 == step_id2:
        return True
    steps_info = get_steps_info([step_id1, step_id2])
    if len(steps_info) != 2:
        return False
    si1 = steps_info[step_id1]
    si2 = steps_info[step_id2]
    # Compare with case sensitivity, except when the basepath is a windows path.
    is_case_sensitive = _is_windows_path(si1['BasePath'])
    is_equal = (
        si1['Type'] == si2['Type'] \
        and _compare_string(si1['Command'], si2['Command'], is_case_sensitive) \
        and si1['Flags'] == si2['Flags'] \
        and _compare_string(si1['BasePath'], si2['BasePath'], is_case_sensitive) \
        and _compare_string(si1['PathSuffix'], si2['PathSuffix'], is_case_sensitive) \
        and si1['LatestInstaller'] == si2['LatestInstaller'] \
        and si1['SleepUntilReboot'] == si2['SleepUntilReboot'] \
        and si1['AlwaysRun'] == si2['AlwaysRun']
    )
    return is_equal

