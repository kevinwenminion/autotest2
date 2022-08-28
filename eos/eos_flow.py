import time

from dflow import Step, Workflow, download_artifact, upload_artifact
from dflow.python import PythonOPTemplate
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
        "email": "zhuoyli@connect.hku.hk",
        "password": "enoughBor715!",
        "program_id": 2315,
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


def main():
    from eos_make_post import (EosMake, EosPost)
    from run_property import RunProperty
    # define input artifacts
    artifact0 = upload_artifact("param.json")
    artifact1 = upload_artifact("POSCAR")
    artifact2 = upload_artifact("frozen_model.pb")
    print(artifact0)
    print(artifact1)
    print(artifact2)

    #define dispatcher
    dispatcher_executor = DispatcherExecutor(
        host="127.0.0.1", port="2746",
        machine_dict=lbg_machine_dict,
        resources_dict=lbg_resource_dict)

    # define Steps for make, run and post
    step_make = Step(
        name="make-eos",
        template=PythonOPTemplate(EosMake, image="zhuoyli/dflow_test:local_cn"),
        artifacts={"parameters": artifact0,
                   "structure": artifact1,
                   "potential": artifact2},
    )
    artifact_target_tasks = step_make.outputs.artifacts["tasks"]

    step_run = Step(
        name="run-eos",
        template=PythonOPTemplate(RunProperty,
                                  image="zhuoyli/dflow_test:local_cn",
                                  command=['python3']),
        artifacts={"target_tasks": artifact_target_tasks}, executor=dispatcher_executor,
        util_command=['python3']
    )
    artifact_out_tasks = step_run.outputs.artifacts["out_tasks"]

    step_post = Step(
        name="post-eos",
        template=PythonOPTemplate(EosPost, image="zhuoyli/dflow_test:local_cn"),
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
