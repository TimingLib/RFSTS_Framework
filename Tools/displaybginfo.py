import os
import sys
import subprocess

def _get_install_log():
    vm_log = r'C:\Incoming\scriptOut.log'
    if os.path.exists(vm_log):
        return vm_log
    progfiles = os.getenv('PROGRAMFILES(X86)')
    if not progfiles:
        progfiles = os.getenv('PROGRAMFILES')
    return os.path.join(progfiles, r'Symantec\Ghost\INCOMING\scriptOut.log')

def gen_installer_list(install_log=None):
    if not install_log:
        install_log = _get_install_log()
    succ_installers = ['']
    failed_installers = ['']
    with open(install_log) as f:
        for line in f:
            if r'Executing:"\\' in line:
                tmp = line.split('"')[1]
                if tmp.lower().endswith('autolicense.exe'):
                    continue
                # Go on read 2 lines, and see whether this software is failed to install.
                more_two_lines = ''
                try:
                    more_two_lines += f.next()
                    more_two_lines += f.next()
                except Exception:
                    break
                finally:
                    # If this installer is a "setup.exe", it's unnecessary to display it.
                    # Otherwise, it's better to display the name, to make people easily
                    # know which installer it is.
                    installer_path = tmp
                    if os.path.basename(installer_path).lower() == 'setup.exe':
                        installer_path = os.path.dirname(installer_path)
                    if '[ERROR]: Return value:' in more_two_lines:
                        failed_installers.append(installer_path)
                    else:
                        succ_installers.append(installer_path)
    with open(r'c:\installer.txt', 'w') as fp:
        fp.write('\n'.join(succ_installers))
    with open(r'c:\failed_installer.txt', 'w') as fp:
        fp.write('\n'.join(failed_installers))

def run_bginfo():
    g_selfpath = os.path.realpath( __file__ )
    g_bginfo = os.path.join(os.path.dirname(g_selfpath), 'bginfo.exe')
    g_bginfoconfig = os.path.join(os.path.dirname(g_selfpath), 'bginfoconfig.bgi')
	print succ_installers
    #subprocess.call([g_bginfo, g_bginfoconfig, '/nolicprompt', '/timer:0', '/silent'])

def main():
    install_log = ''
    if len(sys.argv) > 1:
        install_log = sys.argv[1]
    gen_installer_list(install_log)
    run_bginfo()
    return 0

if __name__ == "__main__":
    sys.exit(main())