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
            'parameters': Artifact(Path),
            'structure': Artifact(Path),
            'potential': Artifact(Path)
        })

    @classmethod
    def get_output_sign(cls):
        return OPIOSign({
            'eospath': Artifact(Path),
            'log': Artifact(Path),
        })

    @OP.exec_sign_check
    def execute(
            self,
            op_in: OPIO,
    ) -> OPIO:
        op_out = OPIO({
            "eospath": Path("eos_calc"),
            "log": Path("eos_make_log.txt"),
        })
        pass

        return op_out


def test_python():
    wf = Workflow(name="eos-post")

    artifact0 = upload_artifact("param.json")
    artifact1 = upload_artifact("POSCAR")
    artifact2 = upload_artifact("frozen_model.pb")
    print(artifact0)
    print(artifact1)
    print(artifact2)
    # print(artifact3)
    step = Step(
        name="step",
        template=PythonOPTemplate(Eosmake, image="zhuoyli/dflow_test:eos"),
        artifacts={"parameters": artifact0,
                   "structure": artifact1,
                   "potential": artifact2},
    )
    wf.add(step)
    wf.submit()

    while wf.query_status() in ["Pending", "Running"]:
        time.sleep(1)

    assert (wf.query_status() == "Succeeded")
    step = wf.query_step(name="step")[0]
    assert (step.phase == "Succeeded")

    print(download_artifact(step.outputs.artifacts["eospath"]))
    print(download_artifact(step.outputs.artifacts["log"]))


if __name__ == "__main__":
    test_python()

