from pathlib import Path
import os
import shutil

from dflow.python import (OP, OPIO, Artifact, OPIOSign,
                          upload_packages)

if "__file__" in locals():
    upload_packages.append(__file__)


class RelaxRun(OP):
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
        os.chdir(path_to_work)
        os.system("lmp -i in.lammps -v restart 0")

    @OP.exec_sign_check
    def execute(
            self,
            op_in: OPIO,
    ) -> OPIO:
        op_out = OPIO({
            "out_tasks": Path('relaxation')
        })
        path_to_relaxation = op_in['target_tasks']
        path_to_work = path_to_relaxation/'relax_task'
        cwd = os.getcwd()
        self.run(path_to_work)
        os.chdir(cwd)
        shutil.copytree(path_to_relaxation, op_out["out_tasks"])
        return op_out
