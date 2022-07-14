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
from dpgen import dlog

if "__file__" in locals():
    upload_packages.append(__file__)

class Eosmake(OP):
    def __init__(self):
        pass

    @classmethod
    def get_input_sign(cls):
        return OPIOSign({
            'eos' : Artifact(Path),
            'interaction': Artifact(Path),
            'structure': Artifact(Path),
            'potential': Artifact(Path)
        })

    @classmethod
    def get_output_sign(cls):
        return OPIOSign({
            'eospath' : Artifact(Path),
            'log' : Artifact(Path),
        })

    @OP.exec_sign_check
    def execute(
            self,
            op_in : OPIO,
    ) -> OPIO:
        op_out = OPIO({
            "eospath": Path("eos_calc"),
            "log": Path("eos_make_log.txt"),
        })

        potential = op_in['potential']
        inter_param_prop = loadfn(op_in['interaction'])
        parameters = loadfn(op_in['eos'])
        parameters['cal_type'] = parameters.get('cal_type', 'relaxation')
        parameters['cal_setting'] = {"relax_pos": True,
                                   "relax_shape": True,
                                   "relax_vol": False}
        equi_contcar = loadfn(op_in['eos'])["relaxed_poscar"]
        vol_ratio = loadfn(op_in['eos'])["vol_ratio"]
        vol_start = loadfn(op_in['eos'])["vol_start"]
        vol_end = loadfn(op_in['eos'])["vol_end"]
        vol_step = loadfn(op_in['eos'])["vol_step"]
        #equi_contcar = os.path.relpath('./POSCAR')
        equi_contcar = op_in['structure']
        vol_start = 0.8
        vol_end = 1.2
        vol_step = 0.01

        task_num = 0
        cwd = os.getcwd()
        task_list = []
        while vol_start + vol_step * task_num < vol_end:
            vol = vol_start + task_num * vol_step
            output_task = os.path.join(op_out['eospath'], 'task.%06d' % task_num)
            os.makedirs(output_task, exist_ok=True)
            os.chdir(output_task)
            task_list.append(output_task)
            os.symlink(equi_contcar, 'POSCAR.orig')
            #poscar_orig = os.path.join(output_task, 'POSCAR.orig')
            #shutil.copy('../POSCAR', poscar_orig)
            scale = vol ** (1. / 3.)
            #eos_params = {'volume': vol * vol_to_poscar, 'scale': scale}
            #dumpfn(eos_params, 'eos.json', indent=4)
            #self.parameter['scale2equi'].append(scale)  # 06/22
            vasp.poscar_scale('POSCAR.orig', 'POSCAR', scale)
            task_num += 1
            os.chdir(cwd)
        #os.chdir(op_out['eospath'])
        #shutil.copy(potential, 'frozen_model.pb')
        shutil.copy(potential, 'frozen_model.pb')

        for kk in task_list:
            poscar = os.path.join(kk, 'POSCAR')
            inter = make_calculator(inter_param_prop, poscar)
            inter.make_potential_files(os.path.abspath(kk))
            #dlog.debug(prop.task_type())  ### debug
            inter.make_input_file(kk, 'eos', parameters)

        with open('eos_make_log.txt','w+') as fout:
           print('eos make end', file=fout)
        
        return op_out

def test_python():
    wf = Workflow(name="eos-make")

    artifact0 = upload_artifact("eos.json")
    artifact1 = upload_artifact("inter.json")
    artifact2 = upload_artifact("POSCAR")
    artifact3 = upload_artifact("frozen_model.pb")
    print(artifact0)
    print(artifact1)
    print(artifact2)
    print(artifact3)
    step = Step(
        name="step", 
        template=PythonOPTemplate(Eosmake, image="zhuoyli/dflow_test:eos"),
        artifacts={"eos": artifact0, "interaction": artifact1,
                   "structure": artifact2, "potential": artifact3},
    )
    wf.add(step)
    wf.submit()

    while wf.query_status() in ["Pending", "Running"]:
        time.sleep(1)

    assert(wf.query_status() == "Succeeded")
    step = wf.query_step(name="step")[0]
    assert(step.phase == "Succeeded")

    print(download_artifact(step.outputs.artifacts["eospath"]))
    print(download_artifact(step.outputs.artifacts["log"]))

if __name__ == "__main__":
    test_python()
