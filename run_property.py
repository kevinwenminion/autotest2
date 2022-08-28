import time
from pathlib import Path
import glob
import os
import shutil

from dflow import Step, Workflow, download_artifact, upload_artifact
from dflow.python import (OP, OPIO, Artifact, OPIOSign, PythonOPTemplate,
                          upload_packages)
from dflow.plugins.dispatcher import DispatcherExecutor

if "__file__" in locals():
    upload_packages.append(__file__)


class PropertyRun(OP):
    def __init__(self):
        pass

    @classmethod
    def get_input_sign(cls):
        return OPIOSign({
            'target_tasks': Artifact(Path)
        })

    @classmethod
    def get_output_sign(cls):
        return OPIOSign({
            'out_tasks': Artifact(Path)
        })

    def run(self, path_to_work):
        tmp_task_list = glob.glob(os.path.join(path_to_work, 'task.[0-9]*[0-9]'))
        tmp_task_list.sort()
        all_task = tmp_task_list
        #run_tasks = util.collect_task(all_task, inter_type)
        if len(all_task) == 0:
            return
        else:
            for task in all_task:
                os.chdir(task)
                os.system("lmp -i in.lammps -v restart 0")

    @OP.exec_sign_check
    def execute(
            self,
            op_in: OPIO,
    ) -> OPIO:
        op_out = OPIO({
            "out_tasks": Path('tasks_finished')
        })
        path_to_work = op_in['target_tasks']
        cwd = os.getcwd()
        self.run(path_to_work)
        os.chdir(cwd)
        shutil.copytree(path_to_work, op_out["out_tasks"])
        return op_out

