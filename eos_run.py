import time
from pathlib import Path
import glob
import os
import shutil

from dflow import Step, Workflow, download_artifact, upload_artifact
from dflow.python import (OP, OPIO, Artifact, OPIOSign, PythonOPTemplate,
                          upload_packages)
from dflow.plugins.dispatcher import DispatcherExecutor

lbg_resource_dict = {
    "number_node": 1,
    "cpu_per_node": 8,
    "gpu_per_node": 1,
    "queue_name": "eosflow_run",
    "group_size": 1,
    "source_list": ["/opt/deepmd-kit-2.0.1"]
    #"source_list": ["/opt/intel/oneapi/setvars.sh"]
}
lbg_machine_dict = {
    "batch_type": "Lebesgue",
    "context_type": "LebesgueContext",
    "local_root" : "./",
    "remote_profile":{
        "email": "xxxxxxxx@xxxx",
        "password": "xxxxxx!",
        "program_id": xxxx,
        "input_data":{
            "api_version":2,
            "job_type": "indicate",
            "log_file": "log",
            "grouped":True,
            "job_name": "eosflow_run",
            "disk_size": 100,
            "scass_type":"c12_m92_1 * NVIDIA V100",
            "platform": "ali",
            #"image_name":"zhuoyli/dflow_test:eos",
            "image_name":"LBG_DeePMD-kit_2.0.1_v1.1",
            "on_demand":0
    }
}
}

if "__file__" in locals():
    upload_packages.append(__file__)


class RunProperty(OP):
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
            "out_tasks": Path('eos_calc_out')
        })
        path_to_work = op_in['target_tasks']
        cwd = os.getcwd()
        self.run(path_to_work)
        os.chdir(cwd)
        shutil.copytree(path_to_work, op_out["out_tasks"])
        return op_out

def main():
    from eos_make_post import (EosMake, EosPost)
    # define input artifacts
    artifact0 = upload_artifact("param.json")
    artifact1 = upload_artifact("POSCAR")
    artifact2 = upload_artifact("frozen_model.pb")
    print(artifact0)
    print(artifact1)
    print(artifact2)

    #define dispatcher
    dispatcher_executor = DispatcherExecutor(
        host="YOUR_HOST", port="YOUR_PORT",
        machine_dict=lbg_machine_dict,
        resources_dict=lbg_resource_dict)

    # define Steps for make, run and post
    step_make = Step(
        name="make-eos",
        template=PythonOPTemplate(EosMake, image="zhuoyli/dflow_test:eos"),
        artifacts={"parameters": artifact0,
                   "structure": artifact1,
                   "potential": artifact2},
    )
    artifact_target_tasks = step_make.outputs.artifacts["tasks"]

    step_run = Step(
        name="run-eos",
        template=PythonOPTemplate(RunProperty,
                                  image="zhuoyli/dflow_test:eos",
                                  command=['python3']),
        artifacts={"target_tasks": artifact_target_tasks}, executor=dispatcher_executor,
        util_command=['python3']
    )
    artifact_out_tasks = step_run.outputs.artifacts["out_tasks"]

    step_post = Step(
        name="post-eos",
        template=PythonOPTemplate(EosPost, image="zhuoyli/dflow_test:eos"),
        artifacts={"result_tasks": artifact_out_tasks}
    )

    # define Workflow for eos
    wf = Workflow(name="eos")
    wf.add(step_make)
    wf.add(step_run)
    wf.add(step_post)
    wf.submit()

    while wf.query_status() in ["Pending", "Running"]:
        time.sleep(1)

    assert (wf.query_status() == "Succeeded")
    step = wf.query_step(name="post-eos")[0]
    assert (step.phase == "Succeeded")

    download_artifact(step.outputs.artifacts["result_json"])
    download_artifact(step.outputs.artifacts["result_out"])

if __name__ == "__main__":
    main()
