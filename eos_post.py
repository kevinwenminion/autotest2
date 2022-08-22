import time
from pathlib import Path

from dflow import Step, Workflow, download_artifact, upload_artifact
from dflow.python import (OP, OPIO, Artifact, OPIOSign, PythonOPTemplate,
                          upload_packages)

import glob
import json
import os
import re
import shutil

import numpy as np
import dpgen.auto_test.lib.vasp as vasp
from monty.serialization import loadfn, dumpfn

from dpgen.auto_test.calculator import make_calculator
from dpgen.auto_test.reproduce import post_repro
from dpgen import dlog

if "__file__" in locals():
    upload_packages.append(__file__)


class Eospost(OP):
    def __init__(self):
        pass

    @classmethod
    def get_input_sign(cls):
        return OPIOSign({
            'workfile': Artifact(Path)
        })

    @classmethod
    def get_output_sign(cls):
        return OPIOSign({
            'result_json': Artifact(Path),
            'result_out': Artifact(Path),
        })

    def compute(self,
                output_file,
                print_file,
                path_to_work):
        path_to_work = os.path.abspath(path_to_work)
        task_dirs = glob.glob(os.path.join(path_to_work, 'task.[0-9]*[0-9]'))
        task_dirs.sort()
        all_res = []
        for ii in task_dirs:
            with open(os.path.join(ii, 'inter.json')) as fp:
                idata = json.load(fp)
            poscar = os.path.join(ii, 'POSCAR')
            task = make_calculator(idata, poscar)
            res = task.compute(ii)
            dumpfn(res, os.path.join(ii, 'result_task.json'), indent=4)
            # all_res.append(res)
            all_res.append(os.path.join(ii, 'result_task.json'))

        # cwd = os.getcwd()
        # os.chdir(path_to_work)
        res, ptr = self._compute_lower(output_file, task_dirs, all_res)
        #        with open(output_file, 'w') as fp:
        #            json.dump(fp, res, indent=4)
        with open(print_file, 'w') as fp:
            fp.write(ptr)
        # os.chdir(cwd)

    def _compute_lower(self,
                       output_file,
                       all_tasks,
                       all_res):
        output_file = os.path.abspath(output_file)
        res_data = {}
        ptr_data = "conf_dir: " + os.path.dirname(output_file) + "\n"
        reprod = False
        #if not self.reprod:
        if not reprod:
            ptr_data += ' VpA(A^3)  EpA(eV)\n'
            for ii in range(len(all_tasks)):
                # vol = self.vol_start + ii * self.vol_step
                vol = loadfn(os.path.join(all_tasks[ii], 'eos.json'))['volume']
                task_result = loadfn(all_res[ii])
                res_data[vol] = task_result['energies'][-1] / sum(task_result['atom_numbs'])
                ptr_data += '%7.3f  %8.4f \n' % (vol, task_result['energies'][-1] / sum(task_result['atom_numbs']))
                # res_data[vol] = all_res[ii]['energy'] / len(all_res[ii]['force'])
                # ptr_data += '%7.3f  %8.4f \n' % (vol, all_res[ii]['energy'] / len(all_res[ii]['force']))

        else:
            if 'init_data_path' not in self.parameter:
                raise RuntimeError("please provide the initial data path to reproduce")
            init_data_path = os.path.abspath(self.parameter['init_data_path'])
            res_data, ptr_data = post_repro(init_data_path, self.parameter['init_from_suffix'],
                                            all_tasks, ptr_data, self.parameter.get('reprod_last_frame', True))

        with open(output_file, 'w') as fp:
            json.dump(res_data, fp, indent=4)

        return res_data, ptr_data

    @OP.exec_sign_check
    def execute(
            self,
            op_in: OPIO,
    ) -> OPIO:
        op_out = OPIO({
            "result_json": Path("result.json"),
            "result_out": Path("result.out"),
        })

        self.compute(op_out['result_json'],
                     op_out['result_out'],
                     op_in['workfile'])

        return op_out


def test_python():
    wf = Workflow(name="eos-post")

    artifact0 = upload_artifact("eos_00")
    print(artifact0)
    # print(artifact3)

    step = Step(
        name="step",
        template=PythonOPTemplate(Eospost, image="zhuoyli/dflow_test:eos"),
        artifacts={"workfile": artifact0}
    )
    wf.add(step)
    wf.submit()

    while wf.query_status() in ["Pending", "Running"]:
        time.sleep(1)

    assert (wf.query_status() == "Succeeded")
    step = wf.query_step(name="step")[0]
    assert (step.phase == "Succeeded")

    print(download_artifact(step.outputs.artifacts["result_json"]))
    print(download_artifact(step.outputs.artifacts["result_out"]))


if __name__ == "__main__":
    test_python()

