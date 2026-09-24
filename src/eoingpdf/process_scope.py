"""Windows job ownership: closing a job terminates only its assigned descendants."""
import sys


class ProcessScope:
    def __init__(self):
        self.handle = None
        if sys.platform == 'win32':
            import win32job
            self.handle = win32job.CreateJobObject(None, '')
            limits = win32job.QueryInformationJobObject(self.handle, win32job.JobObjectExtendedLimitInformation)
            limits['BasicLimitInformation']['LimitFlags'] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(self.handle, win32job.JobObjectExtendedLimitInformation, limits)

    def assign(self, pid):
        if self.handle is None:
            return
        import win32api
        import win32con
        import win32job
        process = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, int(pid))
        try:
            win32job.AssignProcessToJobObject(self.handle, process)
        finally:
            process.Close()

    def close(self):
        if self.handle is not None:
            self.handle.Close()
            self.handle = None
