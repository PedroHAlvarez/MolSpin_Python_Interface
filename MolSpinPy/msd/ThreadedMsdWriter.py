import threading
import queue

from .FileTemplate import FileTemplate

class MSDWriter(threading.Thread):
    def __init__(self, template : FileTemplate , data_queue : queue, file_name : str, target : str):
        super().__init__()
        self.template = template
        self.queue = data_queue
        self.daemon = True
        self.file_name = file_name
        self.target = target

    def run(self):
        while True:
            item = self.queue.get()
            if item is None:
                self.queue.task_done()
                break
            step_idx, snapshot = item
            file = self.target + self.file_name + f"_{step_idx}" + ".msd"
            self.template.render_to_file(snapshot, file)
            self.queue.task_done()

