from distutils.version import LooseVersion
import time
from pathlib import Path
import glob
import json
import os
import warnings
import re
import shutil
from multiprocessing import Pool
from monty.serialization import loadfn, dumpfn

from dflow import Step, Workflow, download_artifact, upload_artifact
from dflow.python import (OP, OPIO, Artifact, OPIOSign, PythonOPTemplate,
                          upload_packages)

import dpgen.auto_test.lib.util as util
from dpgen.auto_test.calculator import make_calculator
from dpgen.dispatcher.Dispatcher import make_dispatcher
from dpgen.dispatcher.Dispatcher import make_submission
from dpgen.remote.decide_machine import convert_mdata
from dpgen.util import sepline
lammps_task_type = ['deepmd', 'meam', 'eam_fs', 'eam_alloy']

if "__file__" in locals():
    upload_packages.append(__file__)


class RunProperty(OP):
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

    def run_property(self,
                     path_to_work,
                     inter_param,
                     prop_param,
                     mdata):
        # find all POSCARs and their name like mp-xxx
        # ...
        # conf_dirs = glob.glob(confs)
        # conf_dirs.sort()

        #processes = len(property_list)
        pool = Pool(processes=1)
        property_type = 'eos'
        #print("Submit job via %d processes" % processes)
        """
        conf_dirs = []
        for conf in confs:
            conf_dirs.extend(glob.glob(conf))
        conf_dirs.sort()
        task_list = []
        work_path_list = []
        multiple_ret = []
        for ii in conf_dirs:
            sepline(ch=ii, screen=True)
            for jj in property_list:
                # determine the suffix: from scratch or refine
                # ...
                if jj.get("skip", False):
                    continue
                if 'init_from_suffix' and 'output_suffix' in jj:
                    suffix = jj['output_suffix']
                elif 'reproduce' in jj and jj['reproduce']:
                    suffix = 'reprod'
                else:
                    suffix = '00'

                property_type = jj['type']
                path_to_work = os.path.abspath(os.path.join(ii, property_type + '_' + suffix))
                #work_path_list.append(path_to_work)
        """
        task_list = []
        multiple_ret = []
        tmp_task_list = glob.glob(os.path.join(path_to_work, 'task.[0-9]*[0-9]'))
        tmp_task_list.sort()
        task_list.append(tmp_task_list)

        inter_param_prop = inter_param
        if 'cal_setting' in prop_param and 'overwrite_interaction' in prop_param['cal_setting']:
            inter_param_prop = prop_param['cal_setting']['overwrite_interaction']

        # dispatch the tasks
        # POSCAR here is useless
        virtual_calculator = make_calculator(inter_param_prop, "POSCAR")
        forward_files = virtual_calculator.forward_files(property_type)
        forward_common_files = virtual_calculator.forward_common_files(property_type)
        backward_files = virtual_calculator.backward_files(property_type)
        #    backward_files += logs
        # ...
        inter_type = inter_param_prop['type']
        # vasp
        if inter_type == "vasp":
            mdata = convert_mdata(mdata, ["fp"])
        elif inter_type in lammps_task_type:
            mdata = convert_mdata(mdata, ["model_devi"])
        else:
            raise RuntimeError("unknown task %s, something wrong" % inter_type)

        work_path = path_to_work
        all_task = tmp_task_list
        run_tasks = util.collect_task(all_task, inter_type)
        if len(run_tasks) == 0:
            return
        else:
            ret = pool.apply_async(self.worker, (work_path,
                                            all_task,
                                            forward_common_files,
                                            forward_files,
                                            backward_files,
                                            mdata,
                                            inter_type,
                                            ))
            multiple_ret.append(ret)
        pool.close()
        pool.join()
        for ii in range(len(multiple_ret)):
            if not multiple_ret[ii].successful():
                print("ERROR:", multiple_ret[ii].get())
                raise RuntimeError("Job %d is not successful!" % ii)
        print('%d jobs are finished' % len(multiple_ret))


    def worker(self,
               work_path,
               all_task,
               forward_common_files,
               forward_files,
               backward_files,
               mdata,
               inter_type):
        run_tasks = [os.path.basename(ii) for ii in all_task]
        machine, resources, command, group_size = util.get_machine_info(mdata, inter_type)
        api_version = mdata.get('api_version', '0.9')
        if LooseVersion(api_version) < LooseVersion('1.0'):
            warnings.warn(f"the dpdispatcher will be updated to new version."
                f"And the interface may be changed. Please check the documents for more details")
            disp = make_dispatcher(machine, resources, work_path, run_tasks, group_size)
            disp.run_jobs(resources,
                      command,
                      work_path,
                      run_tasks,
                      group_size,
                      forward_common_files,
                      forward_files,
                      backward_files,
                      outlog='outlog',
                      errlog='errlog')
        elif LooseVersion(api_version) >= LooseVersion('1.0'):
            submission = make_submission(
                    mdata_machine=machine,
                    mdata_resources=resources,
                    commands=[command],
                    work_path=work_path,
                    run_tasks=run_tasks,
                    group_size=group_size,
                    forward_common_files=forward_common_files,
                    forward_files=forward_files,
                    backward_files=backward_files,
                    outlog = 'outlog',
                    errlog = 'errlog'
                )
            submission.run_submission()

    @OP.exec_sign_check
    def execute(
            self,
            op_in: OPIO,
    ) -> OPIO:
        op_out = OPIO({
            "workfile": Path("result.json"),
            "param": Path("result.out"),
            "machine": Path("result.out")
        })
        path_to_work = op_in['workfile']
        inter_param = loadfn(op_in['param'])["interaction"]
        prop_param = loadfn(op_in['param'])["properties"]
        mdata = loadfn(op_in['machine'])
        self.run_property(path_to_work, inter_param, prop_param, mdata)

        return op_out


def test_python():
    wf = Workflow(name="run_property")

    artifact0 = upload_artifact("eos_00")
    artifact1 = upload_artifact("param.json")
    artifact2 = upload_artifact("machine.json")
    print(artifact0)
    # print(artifact3)
    step = Step(
        name="step",
        template=PythonOPTemplate(RunProperty, image="zhuoyli/dflow_test:eos"),
        artifacts={"workfile": artifact0,
                   "param": artifact1,
                   "machine":  artifact2}
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
