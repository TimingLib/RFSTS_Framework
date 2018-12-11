from __future__ import with_statement
import os
import shutil
import stat
import logging
import traceback
import ConfigParser

import nicu.errcode as errcode
import nicu.sequence as sequence

import globalvar as gv
import util
import util.dbx as dbx
from util.render import Template

import socket

__all__ = [
    "gen_ghost_conf",
]

LOGGER = logging.getLogger(__name__)


def gen_ini_step(si_config, seq_id_template):
    """
    Generate ini steps based on sequence.

    :param si_config:
        The :class:`ConfigParser` for ini file.
    :param seq_id:
        The `SeqID` column in `GhostSequences` table.
    :returns:
        The join of all step name.
    """
    step_seq = ''
    if seq_id_template == -1:
        return step_seq
    seq_id = sequence.gen_new_seq(seq_id_template, throw_exception=True)

    # Generate an ini file by seq_id
    seq_info = dbx.queryx_sequence_info(seq_id)
    step_ids = seq_info[0].split(",")
    for i, step_id in enumerate(step_ids):
        step_info = dbx.queryx_step_info(step_id)
        step_name = "step%s" % (i)
        si_config.set("steps", step_name, 1)
        si_config.add_section(step_name)
        step_seq = step_seq + "&" + step_name
        # ----Basic Infomation----
        # always_run
        if step_info[10]:
            si_config.set(step_name, "always_run", 1)
        else:
            si_config.set(step_name, "always_run", 0)

        # ----Infomation----
        if step_info[0] == 0 or step_info[0] == 1:
            # Shared properties for Command Type and Installer Type
            if step_info[3] is not None:
                si_config.set(step_name, "path", step_info[3].strip())
            if step_info[1] is not None:
                si_config.set(step_name, "command", step_info[1].strip())
            if step_info[2] is not None:
                si_config.set(step_name, "flags", step_info[2].strip())
            if step_info[6]:
                si_config.set(step_name, "sleep_until_reboot", 1)
            else:
                si_config.set(step_name, "sleep_until_reboot", 0)

            if step_info[0] == 0:
                # ----Command Type Infomation----
                si_config.set(step_name, "type", "command")
            elif step_info[0] == 1:
                # ----Installer Type Infomation----
                si_config.set(step_name, "type", "latest_installer")
                if step_info[5]:
                    si_config.set(step_name, "find_latest", 1)
                else:
                    si_config.set(step_name, "find_latest", 0)
                if step_info[4] is not None:
                    si_config.set(step_name, "path_suffix",
                                  step_info[4].strip())
        elif step_info[0] == 2:
            # ----Reboot Type Infomation----
            si_config.set(step_name, "type", "reboot")
        elif step_info[0] == 3:
            # ----Notifier Type Infomation----
            si_config.set(step_name, "type", "notifier")
            if step_info[6]:
                si_config.set(step_name, "sleep_until_reboot", 1)
            else:
                si_config.set(step_name, "sleep_until_reboot", 0)
            if step_info[7]:
                si_config.set(step_name, "host", step_info[7])
            if step_info[8]:
                si_config.set(step_name, "port", step_info[8])
            if step_info[9]:
                si_config.set(step_name, "message", step_info[9])
    return step_seq


def get_run_key_value(is_vm_image, target_os_platform, target_os_bit):
    """
    Get value of key `run_key_value` in `script.ini`.

    :param is_vm_image:
        Whether target machine is vmware.
    :param target_os_platform:
        The os platform of target machine.
    :param target_os_bit:
        The os bit of target machine.
    :returns:
        The value of key `run_key_value`.
    """
    gvt, hdl = util.export_target_modules()
    run_key_value = ''
    if is_vm_image:
        if target_os_platform == 'windows':
            run_key_value = ('cmd /c "%s\\boot.bat %s"'
                             % (gvt.gt_vm_root,
                                gvt.gt_vm_root))
        elif target_os_platform == 'linux':
            run_key_value = '%s/boot.sh' % gvt.gt_vm_root
    else:
        if target_os_platform == 'windows':
            if target_os_bit == 32:
                run_key_value = ('cmd /c "%s\\boot.bat"' % gvt.gt_root_32)
            elif target_os_bit == 64:
                run_key_value = ('cmd /c "%s\\boot.bat"' % gvt.gt_root_64)
        elif target_os_platform == 'linux':
            # absolute path is not a good idea,
            # since we can not change user easily.
            # TODO: find a better method later
            run_key_value = "%s/boot.sh" % gvt.gt_root
        elif target_os_platform == 'mac':
            run_key_value = "%s/macboot.sh" % gvt.gt_root
    return run_key_value


def gen_ghost_conf(machine_id, os_id, seq_id, emails, req_addr=None,
                   is_grab_image=False, boot_dir_home=''):
    """
    Generate the ghost ini script file automatically for specific Machine and
    OS, and generate setupenv script for windows and vmware.

    :param machine_id:
        The `MachineID` column in `Machine_Info` table.
    :param os_id:
        The `OSID` column in `OS_Info` table.
    :param seq_id:
        The `SeqID` column in `GhostSequences` table.
    :param emails:
        The email adderss for receiving the notification email of Ghost
        status.
    :param req_addr:
        Where we receive this command from.
    :param is_grab_image:
        Whether grab new image or not.
    :param boot_dir_home:
        The directory of boot script in target machine.
    :returns:
        * successful - The path of `script.ini`
        * failed - raise exception with related error code.

    .. note::
        In the ghost ini script file, we will create some default steps:
            #. **updateosstatus** - Before Ghost Seq, we need update the
               current OS status in DB.
            #. **updateseqstatus** - After Ghost Seq, we need update the
               current Seq status in DB.
    """
    try:
        gvt, hdl = util.export_target_modules()

        (machine_name, group_name) = dbx.queryx_machine_info(machine_id)

        script_ini_full = os.path.join(
            gv.g_script_ini_dir_server, gv.g_script_ini)
        if gv.g_platform == 'windows':
            script_ini_full = os.path.join(
                gv.g_script_ini_dir_server, gv.g_apply_images_folder,
                group_name, machine_name, "OSID_%s" % os_id, gv.g_script_ini)

        # Get Server information for MachineID
        qs_res = dbx.queryx_target_server_info(machine_id, os_id)
        (server_name, server_port, is_vm_image) = qs_res

        (req_ip, req_port) = req_addr if req_addr else ('0.0.0.0', -1)

        # Common sections for ini file
        si_config = ConfigParser.ConfigParser()

        # optionxform, by default returns a lower-case version of option,
        # change optionxform to str, so the case are reserved as user input
        si_config.optionxform = str

        si_config.add_section("steps")

        # Email Settings
        si_config.add_section("emailconfiguration")
        si_config.set("emailconfiguration", "mailserver", gv.g_smtp_server)
        si_config.set("emailconfiguration", "mailto", emails)

        qs_res = dbx.queryx_target_os_info(os_id)
        (target_os_platform, target_os_bit) = qs_res[0:2]
        # Registry Settings
        si_config.add_section("settings")
        run_key_value = get_run_key_value(is_vm_image, target_os_platform,
                                          target_os_bit)
        if run_key_value:
            si_config.set("settings", "run_key_value", run_key_value)
        si_config.set("settings", "AutoAdminLoginOriginalState", "1")
        si_config.set("settings", "AutoAdminLoginOriginalUserName", "")
        si_config.set("settings", "AutoAdminLoginOriginalDomainName", "")

        # Before the custom ghost sequence,
        # we need create a default step to map file server
        step_name = "mappingsrv"
        step_seq = step_name
        si_config.add_section(step_name)
        si_config.set("steps", step_name, 1)
        si_config.set(step_name, "flags", "")
        si_config.set(step_name, "sleep_until_reboot", "0")
        si_config.set(step_name, "always_run", "1")
        si_config.set(step_name, "type", "command")
        si_config.set(step_name, "command", gvt.gt_mapping_script)
        si_config.set(step_name, "path", gvt.gt_cmd_prefix)

        # Before the custom ghost sequence,
        # we need update the current OS status
        step_name = "updateosstatus"
        step_seq = step_seq + "&" + step_name
        si_config.add_section(step_name)
        si_config.set("steps", step_name, 1)
        si_config.set(step_name, "type", "notifier")
        si_config.set(step_name, "host", server_name)
        si_config.set(step_name, "port", server_port)
        msg = "UpdateGhostStat %s %s" % (machine_id, os_id)
        si_config.set(step_name, "message", msg)

        # Before the custom ghost sequence,
        # we need reset the sequencese status as -1
        step_name = "resetseqstatus"
        step_seq = step_seq + "&" + step_name
        si_config.add_section(step_name)
        si_config.set("steps", step_name, 1)
        si_config.set(step_name, "type", "notifier")
        si_config.set(step_name, "host", server_name)
        si_config.set(step_name, "port", server_port)
        msg = "UpdateSeqStat %s %s" % (machine_id, "-1")
        si_config.set(step_name, "message", msg)

        # Get Sequences Information from GhostSequences Table
        seq_id = -1 if seq_id is None else seq_id
        step_seq = step_seq + gen_ini_step(si_config, seq_id)

        # After Ghost Seq, we need update the current Seq status
        seq_stat_section = "updateseqstatus"
        si_config.add_section(seq_stat_section)
        si_config.set(seq_stat_section, "srvhost", server_name)
        si_config.set(seq_stat_section, "srvport", server_port)

        msg = "UpdateSeqStat %s %s" % (machine_id, seq_id)

        si_config.set(seq_stat_section, "srvmessage", msg)
        si_config.set(seq_stat_section, "seqid", seq_id)
        si_config.set(seq_stat_section, "reqhost", req_ip)
        si_config.set(seq_stat_section, "reqport", req_port + 1)

        # if is_grab_image = True, we need add a new step to grab new image
        if is_grab_image:
            step_name = "grabnewimage"
            step_seq = step_seq + "&" + step_name
            si_config.add_section(step_name)
            si_config.set("steps", step_name, 1)
            si_config.set(step_name, "type", "notifier")
            si_config.set(step_name, "host", server_name)
            si_config.set(step_name, "port", server_port)
            msg = "GrabNewImage %s %s" % (machine_id, os_id)
            si_config.set(step_name, "message", msg)

        # Set the sequence of the ghost steps
        si_config.set("steps", "orderlist", step_seq)

        write_script_ini(si_config, script_ini_full,
                         group_name=group_name,
                         machine_name=machine_name,
                         os_id=os_id)
        gen_setupenv_script(target_os_platform,
                            group_name=group_name,
                            machine_name=machine_name,
                            machine_id=machine_id,
                            os_id=os_id,
                            boot_dir_home=boot_dir_home)
    except Exception, error:
        LOGGER.error(
            "Failed to generate ini file for Machine<%s> OSID<%s> seq_id<%s>: %s"
            % (machine_id, os_id, seq_id, error),
            extra={'error_level': 2})
        LOGGER.error(traceback.format_exc())
        raise Exception(errcode.ER_GA_GEN_CONF_EXCEPTION)
    LOGGER.info("generate %s for Machine<%s> OSID<%s> seq_id<%s>"
                % (script_ini_full, machine_id, os_id, seq_id))
    return script_ini_full


def write_script_ini(si_config, script_ini_full, **argv):
    """
    Write the `script.ini` file via :class:`ConfigParser`.

    :param si_config:
        The :class:`ConfigParser` for ini file.
    :param script_ini_full:
        The path of `script.ini`.
    :param argv:
        * group_name - The group name of target machine belonged to.
        * machine_name - The name of target machine.
        * os_id - The os id that target machine will be ghosted into.
    :returns:
        * successful - None
        * failed - raise exception with related error code.
    """
    # Write the ini file
    LOGGER.info("Generating %s" % (script_ini_full))

    group_name = argv['group_name']
    machine_name = argv['machine_name']
    os_id = argv['os_id']

    parent_dir = os.path.dirname(script_ini_full)
    if not os.path.exists(parent_dir):
        os.makedirs(parent_dir)
    if os.path.exists(script_ini_full):
        os.remove(script_ini_full)

    with open(script_ini_full, "w") as ini_fp:
        si_config.write(ini_fp)
    if not os.path.exists(script_ini_full):
        LOGGER.error("Generate %s fail!" % script_ini_full, extra={'error_level': 2})
        raise Exception(errcode.ER_GA_GEN_CONF_EXCEPTION)
    else:
        LOGGER.info("generate %s success" % script_ini_full)

    if gv.g_platform != 'windows':
        return

    # now platform is windows. "script.ini" is put locally in Linux/Mac,
    # but remotely in Windows. So, we need to copy it to local server.
    script_ini_dir_local = os.path.join(
        gv.g_ga_root, "GhostScripts", "SAAS", gv.g_apply_images_folder,
        group_name, machine_name, "OSID_%s" % os_id)
    script_ini_local = os.path.join(script_ini_dir_local, gv.g_script_ini)
    if not os.path.exists(script_ini_dir_local):
        os.makedirs(script_ini_dir_local)

    LOGGER.info("copy %s to %s" % (script_ini_full, script_ini_local))
    shutil.copyfile(script_ini_full, script_ini_local)
    return


def gen_setupenv_script(target_os_platform, **argv):
    """
    Generate setupenv script for windows and vmware.

    :param target_os_platform:
        The os platform that target machine will be ghosted into.
    :param argv:
        * group_name - The group name of target machine belonged to.
        * machine_name - The name of target machine.
        * os_id - The os id that target machine will be ghosted into.
        * boot_dir_home - The directory of boot script in target machine.
    :returns:
        * successful - None
        * failed - raise exception with related error code.

    .. note::
        For non-Windows OSes, ie, Linux/Mac, we don't generate the setupenv
        script, and we generate script.ini of linux only when target is
        vmware image.
    """
    if gv.g_platform != 'windows' \
            or target_os_platform not in ['windows', 'linux']:
        return

    gvt, hdl = util.export_target_modules()

    group_name = argv['group_name']
    machine_name = argv['machine_name']
    machine_id = argv['machine_id']
    os_id = argv['os_id']
    boot_dir_home = ''
    if 'boot_dir_home' in argv and argv['boot_dir_home']:
        boot_dir_home = '"%s"' % (argv['boot_dir_home'].strip('"'))

    setupenv_script_full = os.path.join(
        gv.g_ga_root, "INCOMING", gvt.gt_setupenv_script)

    if not os.path.exists(setupenv_script_full):
        LOGGER.error("%s NOT found!" % setupenv_script_full, extra={'error_level': 2})
        raise Exception(errcode.ER_GA_GEN_CONF_EXCEPTION)

    setupenv_script_dir_local = os.path.join(
        gv.g_ga_root, "GhostScripts", "SAAS", gv.g_apply_images_folder,
        group_name, machine_name, "OSID_%s" % os_id)
    setupenv_script_local = os.path.join(
        setupenv_script_dir_local, gvt.gt_setupenv_script)

    if not os.path.exists(setupenv_script_dir_local):
        os.makedirs(setupenv_script_dir_local)
    if os.path.exists(setupenv_script_local):
        os.chmod(setupenv_script_local, stat.S_IWRITE)

    shutil.copy(setupenv_script_full, setupenv_script_local)
    LOGGER.debug("copy %s success" % (gvt.gt_setupenv_script))

    os.chmod(setupenv_script_local, stat.S_IWRITE)
    if not os.access(setupenv_script_local, os.W_OK):
        LOGGER.error(
            "remove READONLY attribute on %s fail." % setupenv_script_local,
            extra={'error_level': 2})
        raise Exception(errcode.ER_GA_GEN_CONF_EXCEPTION)

    is_general = False
    if target_os_platform == 'windows':
        is_general = dbx.queryx_is_general(machine_id, os_id)

    odict = {'is_general': is_general,
             'boot_dir_home': boot_dir_home,
             'machine_name': machine_name}

    setupenv_script_full_server = os.path.join(
        gv.g_script_ini_dir_server, gv.g_apply_images_folder, group_name,
        machine_name, "OSID_%s" % os_id, gvt.gt_setupenv_script)
    if target_os_platform == 'windows':
        # copy setupenv.bat to cn-sha-rdfs01 server,
        # because setupenv.bat will be downloaded by ghosted machine
        # from this server, not transferred by Ghost Console.
        odict['script_ini_dir_server'] = os.path.dirname(
            setupenv_script_full_server)
    else:
        # if target is linux virtual machine
        server_name = socket.gethostname().split('.')[0]
        odict['notify_server'] = server_name
        odict['server_port'] = gv.g_ns_port
        odict['script_ini_dir_server'] = (gvt.gt_vm_script_root %
            (gv.g_apply_images_folder, group_name, machine_name, os_id))

    data_render = Template(filename=setupenv_script_local).render(**odict)
    with open(setupenv_script_local, 'wb') as fp:
        fp.write(data_render)

    shutil.copyfile(setupenv_script_local, setupenv_script_full_server)
    LOGGER.info('copy %s to server "%s" successfully'
                % (gvt.gt_setupenv_script, setupenv_script_full_server))

    LOGGER.info("generate %s successfully" % (setupenv_script_local))
    return
