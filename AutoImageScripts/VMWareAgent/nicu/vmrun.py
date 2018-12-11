import threading
from nicu.vm import Vmrun
from nicu.decor import *


__all__ = ['VmrunPool']

_mutex = threading.Lock()


class VmrunPool(Vmrun):
    @timeout(600)
    def kvmrun(self, cmd, *args):
        """
        VMRun command will be time out after 10 min.
        """
        # We should call the parent function with same name (such as start, stop),
        # not the base function (i.e. vmrun) in parent class.
        # Except for runProgramInGuest and runScriptInGuest, since that
        # we have modified these two functions, not only added some restrictions.
        if cmd in ['runProgramInGuest', 'runScriptInGuest']:
            return self.vmrun(cmd, *args)
        return getattr(Vmrun, cmd)(self, *args)

    #
    # POWER COMMANDS
    #
    @synchronized(_mutex)
    def start(self):
        '''
        COMMAND                  PARAMETERS           DESCRIPTION
        start                    Path to vmx file     Start a VM or Team
                                or vmtm file
        '''
        return self.kvmrun('start')

    @synchronized(_mutex)
    def stop(self, mode='soft'):
        '''
        stop                     Path to vmx file     Stop a VM or Team
                                or vmtm file
                                [hard|soft]
        '''
        return self.kvmrun('stop', mode)

    @synchronized(_mutex)
    def reset(self, mode='soft'):
        '''
        reset                    Path to vmx file     Reset a VM or Team
                                or vmtm file
                                [hard|soft]
        '''
        return self.kvmrun('reset', mode)

    @synchronized(_mutex)
    def suspend(self, mode='soft'):
        '''
        suspend                 Path to vmx file     Suspend a VM or Team
                                or vmtm file
                                [hard|soft]
        '''
        return self.kvmrun('suspend', mode)

    @synchronized(_mutex)
    def pause(self):
        '''
        pause                    Path to vmx file     Pause a VM
        '''
        return self.kvmrun('pause')

    @synchronized(_mutex)
    def unpause(self):
        '''
        unpause                  Path to vmx file     Unpause a VM
        '''
        return self.kvmrun('unpause')

    #
    # GUEST OS COMMANDS
    #
    # FIXME -noWait -activeWindow -interactive???
    def runProgramInGuest(self, program, nowait, *para):
        '''
        runProgramInGuest        Path to vmx file     Run a program in Guest OS
                                [-noWait]
                                [-activeWindow]
                                [-interactive]
                                Complete-Path-To-Program
                                [Program arguments]
        '''
        if nowait == True:
            return self.kvmrun('runProgramInGuest', '-nowait',"\"%s\"" % program, *para)
        return self.kvmrun('runProgramInGuest', "\"%s\"" % program, *para)

    def runScriptInGuest(self, interpreter_path, script, nowait):
        '''
        runScriptInGuest         Path to vmx file     Run a script in Guest OS
                                Interpreter path
                                script_text
        '''
        if nowait == True:
            return self.kvmrun('runScriptInGuest', '-nowait', interpreter_path, "\"%s\"" % script)
        return self.kvmrun('runScriptInGuest', interpreter_path, "\"%s\"" % script)


