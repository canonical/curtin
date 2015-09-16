#! /usr/bin/env python
import threading
import subprocess
import traceback
import signal


class Command(object):
    """
    based on https://gist.github.com/kirpit/1306188
    """
    command = None
    process = None
    status = None
    exception = None
    returncode = -1

    def __init__(self, command, signal=signal.SIGTERM):
        self.command = command
        self.signal = signal

    def run(self, timeout=None, **kwargs):
        """ Run a command then return: (status, output, error). """
        def target(**kwargs):
            try:
                self.process = subprocess.Popen(self.command, **kwargs)
                self.process.communicate()
                self.status = self.process.returncode
            except subprocess.CalledProcessError as e:
                self.exception = e
                self.returncode = e.returncode
            except Exception as e:
                self.exception = e
        # thread
        thread = threading.Thread(target=target, kwargs=kwargs)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self.process.send_signal(self.signal)
            thread.join()
            self.exception = TimeoutExpired(
                cmd=self.command, timeout=timeout)

        if self.exception:
            raise self.exception

        if self.status != 0:
            raise subprocess.CalledProcessError(cmd=self.command,
                                                returncode=self.status)

        return 0

try:
    TimeoutExpired = subprocess.TimeoutExpired
except AttributeError:
    class TimeoutExpired(subprocess.CalledProcessError):
        def __init__(self, *args, **kwargs):
            if not kwargs:
                kwargs = {}
            if len(args):
                args = list(args)
                for arg in ('cmd', 'output', 'timeout'):
                    kwargs[arg] = args.pop(0)
                    if not len(args):
                        break

            returncode = -1
            if 'timeout' in kwargs:
                self.timeout = kwargs.pop('timeout')
            else:
                self.timeout = -1

            super(TimeoutExpired, self).__init__(returncode, **kwargs)
            

def check_call(cmd, signal=signal.SIGTERM, **kwargs):
    # provide a 'check_call' like interface, but kill with a nice signal
    return Command(cmd, signal).run(**kwargs)
