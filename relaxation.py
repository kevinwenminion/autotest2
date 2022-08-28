from pathlib import Path
from dflow.python import (OP, OPIO, Artifact, OPIOSign, upload_packages)

import os
import shutil

from monty.serialization import loadfn
from dpgen.auto_test.common_equi import (make_equi, post_equi)

if "__file__" in locals():
    upload_packages.append(__file__)


class RelaxMake(OP):
    def __init__(self):
        pass

    @classmethod
    def get_input_sign(cls):
        return OPIOSign({
            'parameters': Artifact(Path),
            'structure': Artifact(Path),
            'potential': Artifact(Path)
        })

    @classmethod
    def get_output_sign(cls):
        return OPIOSign({
            'inter': dict,
            'tasks': Artifact(Path)
        })

    @OP.exec_sign_check
    def execute(
            self,
            op_in: OPIO,
    ) -> OPIO:
        op_out = OPIO({
            "inter": loadfn(op_in['parameters'])["relaxation"],
            "tasks": Path("relaxation")
        })

        inter_parameter = loadfn(op_in['parameters'])["interaction"]
        relax_param = loadfn(op_in['parameters'])["relaxation"]
        confs = [str(op_in['structure'].parent)]

        cwd = os.getcwd()
        make_equi(confs, inter_parameter, relax_param)

        relaxtaion = os.path.join(confs[0], 'relaxation')
        relax_task = os.path.join(relaxtaion, 'relax_task')
        os.chdir(relaxtaion)
        if os.path.islink('frozen_model.pb'):
            os.remove('frozen_model.pb')
        shutil.copyfile(op_in['potential'], 'frozen_model.pb')
        os.chdir(relax_task)
        if os.path.islink('frozen_model.pb') and os.path.islink('POSCAR'):
            os.remove('frozen_model.pb')
            os.remove('POSCAR')
        shutil.copyfile(op_in['potential'], 'frozen_model.pb')
        shutil.copyfile(op_in['structure'], 'POSCAR')
        os.chdir(cwd)
        shutil.copytree(relaxtaion, 'relaxation')

        return op_out


class RelaxPost(OP):
    def __init__(self):
        pass

    @classmethod
    def get_input_sign(cls):
        return OPIOSign({
            'result_tasks': Artifact(Path),
            'parameters': Artifact(Path)
        })

    @classmethod
    def get_output_sign(cls):
        return OPIOSign({
            'result_json': Artifact(Path),
            'relaxation_finished': Artifact(Path),
        })

    @OP.exec_sign_check
    def execute(
            self,
            op_in: OPIO,
    ) -> OPIO:
        op_out = OPIO({
            "result_json": Path("result.json"),
            "relaxation_finished": Path("relaxation"),
        })
        confs = [str(op_in["result_tasks"].parent)]
        inter_param = loadfn(op_in['parameters'])["interaction"]

        cwd = os.getcwd()
        post_equi(confs, inter_param)
        os.chdir(cwd)
        shutil.copytree(op_in["result_tasks"], 'relaxation')

        return op_out


if __name__ == "__main__":
    pass
