import sys
import threading


__all__ = ['KThread']


class KThread(threading.Thread):
    """
    A subclass of threading.Thread, with a kill() method.
    The thread using this class, will slow down execution efficiency of
    the code, and only take effect when to execute next code.
    So when current code is block in system call, the thread will never
    be killed until the system call finished.

    As suggestion, when use this class, don't use any code which can block
    for long time in function, and improve them with nonblocking code.
    For example:
    1)  time.sleep(1000)
        ==>can be improved as follows:
        for i in range(1000):
            time.sleep(1)
    2)  socket.accept()
        ==>can be improved as follows:
        while not infds:
            infds, outfds, errfds = select.select([socket], [], [], 1)
        infds[0].accept()

    Reference:
    Kill a thread in Python:
    http://mail.python.org/pipermail/python-list/2004-May/260937.html
    """
    def __init__(self, *args, **kwargs):
        threading.Thread.__init__(self, *args, **kwargs)
        self.killed = False

    def start(self):
        """Start the thread."""
        self.__run_backup = self.run
        self.run = self.__run      # Force the Thread to install our trace.
        threading.Thread.start(self)

    def __run(self):
        """Hacked run function, which installs the trace."""
        sys.settrace(self.global_trace)
        self.__run_backup()
        self.run = self.__run_backup
        sys.settrace(None)

    def global_trace(self, frame, why, arg):
        if why == 'call':
            return self.local_trace
        else:
            return None

    def local_trace(self, frame, why, arg):
        if self.killed:
            if why == 'line':
                sys.settrace(None)
                raise SystemExit()
        return self.local_trace

    def kill(self):
        self.killed = True

    def terminate(self):
        self.kill()


