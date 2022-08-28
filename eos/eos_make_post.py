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

import dpgen.auto_test.lib.vasp as vasp
from monty.serialization import loadfn, dumpfn
from dpgen.auto_test.calculator import make_calculator
from dpgen.auto_test.refine import make_refine
from dpgen.auto_test.reproduce import make_repro
from dpgen.auto_test.reproduce import post_repro
from dpgen import dlog

if "__file__" in locals():
    upload_packages.append(__file__)


class EosMake(OP):
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
            'tasks': Artifact(Path)
        })

    @OP.exec_sign_check
    def execute(
            self,
            op_in: OPIO,
    ) -> OPIO:
        op_out = OPIO({
            "tasks": Path("eos_tasks")
        })

        parameter = loadfn(op_in['parameters'])["properties"]
        inter_param_prop = loadfn(op_in['parameters'])["interaction"]
        potential = op_in['potential']

        refine = False
        parameter['reproduce'] = parameter.get('reproduce', False)
        reprod = parameter['reproduce']
        if not reprod:
            if not ('init_from_suffix' in parameter and 'output_suffix' in parameter):
                vol_start = parameter['vol_start']
                vol_end = parameter['vol_end']
                vol_step = parameter['vol_step']
                parameter['vol_abs'] = parameter.get('vol_abs', False)
                vol_abs = parameter['vol_abs']
            parameter['cal_type'] = parameter.get('cal_type', 'relaxation')
            cal_type = parameter['cal_type']
            default_cal_setting = {"relax_pos": True,
                                   "relax_shape": True,
                                   "relax_vol": False}
            if 'cal_setting' not in parameter:
                parameter['cal_setting'] = default_cal_setting
            else:
                if "relax_pos" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_pos'] = default_cal_setting['relax_pos']
                if "relax_shape" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_shape'] = default_cal_setting['relax_shape']
                if "relax_vol" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_vol'] = default_cal_setting['relax_vol']
            cal_setting = parameter['cal_setting']
        else:
            parameter['cal_type'] = 'static'
            cal_type = parameter['cal_type']
            default_cal_setting = {"relax_pos": False,
                                   "relax_shape": False,
                                   "relax_vol": False}
            if 'cal_setting' not in parameter:
                parameter['cal_setting'] = default_cal_setting
            else:
                if "relax_pos" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_pos'] = default_cal_setting['relax_pos']
                if "relax_shape" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_shape'] = default_cal_setting['relax_shape']
                if "relax_vol" not in parameter['cal_setting']:
                    parameter['cal_setting']['relax_vol'] = default_cal_setting['relax_vol']
            cal_setting = parameter['cal_setting']
            parameter['init_from_suffix'] = parameter.get('init_from_suffix', '00')
            init_from_suffix = parameter['init_from_suffix']

        path_to_work = os.path.abspath(op_out['tasks'])
        # path_to_equi = os.path.abspath(op_in['structure'])
        equi_contcar = os.path.abspath(op_in['structure'])

        if 'start_confs_path' in parameter and os.path.exists(parameter['start_confs_path']):
            init_path_list = glob.glob(os.path.join(parameter['start_confs_path'], '*'))
            struct_init_name_list = []
            for ii in init_path_list:
                struct_init_name_list.append(ii.split('/')[-1])
            struct_output_name = path_to_work.split('/')[-2]
            assert struct_output_name in struct_init_name_list
            path_to_equi = os.path.abspath(os.path.join(parameter['start_confs_path'],
                                                        struct_output_name, 'relaxation', 'relax_task'))

        cwd = os.getcwd()
        task_list = []

        if reprod:
            print('eos reproduce starts')
            if 'init_data_path' not in parameter:
                raise RuntimeError("please provide the initial data path to reproduce")
            init_data_path = os.path.abspath(parameter['init_data_path'])
            task_list = make_repro(init_data_path, init_from_suffix,
                                   path_to_work, parameter.get('reprod_last_frame', True))
            os.chdir(cwd)

        else:
            if refine:
                print('eos refine starts')
                task_list = make_refine(parameter['init_from_suffix'],
                                        parameter['output_suffix'],
                                        path_to_work)
                os.chdir(cwd)

                init_from_path = re.sub(parameter['output_suffix'][::-1],
                                        parameter['init_from_suffix'][::-1],
                                        path_to_work[::-1], count=1)[::-1]
                task_list_basename = list(map(os.path.basename, task_list))

                for ii in task_list_basename:
                    init_from_task = os.path.join(init_from_path, ii)
                    output_task = os.path.join(path_to_work, ii)
                    os.chdir(output_task)
                    if os.path.isfile('eos.json'):
                        os.remove('eos.json')
                    if os.path.islink('eos.json'):
                        os.remove('eos.json')
                    os.symlink(os.path.relpath(os.path.join(init_from_task, 'eos.json')), 'eos.json')
                os.chdir(cwd)

            else:
                print('gen eos from ' + str(vol_start) + ' to ' + str(vol_end) + ' by every ' + str(vol_step))
                if vol_abs:
                    dlog.info('treat vol_start and vol_end as absolute volume')
                else:
                    dlog.info('treat vol_start and vol_end as relative volume')
                # equi_contcar = os.path.join(path_to_equi, 'CONTCAR')
                equi_contcar = os.path.abspath(op_in['structure'])
                if not os.path.exists(equi_contcar):
                    raise RuntimeError("please do relaxation first")
                vol_to_poscar = vasp.poscar_vol(equi_contcar) / vasp.poscar_natoms(equi_contcar)
                parameter['scale2equi'] = []

        task_num = 0
        while vol_start + vol_step * task_num < vol_end:
            vol = vol_start + task_num * vol_step
            output_task = os.path.join(path_to_work, 'task.%06d' % task_num)
            os.makedirs(output_task, exist_ok=True)
            os.chdir(output_task)
            task_list.append(output_task)
            shutil.copy(equi_contcar, 'POSCAR.orig')
            # scale = vol ** (1. / 3.)
            if vol_abs:
                scale = (vol / vol_to_poscar) ** (1. / 3.)
                eos_params = {'volume': vol, 'scale': scale}
            else:
                scale = vol ** (1. / 3.)
                eos_params = {'volume': vol * vol_to_poscar, 'scale': scale}
            dumpfn(eos_params, 'eos.json', indent=4)
            parameter['scale2equi'].append(scale)  # 06/22
            vasp.poscar_scale('POSCAR.orig', 'POSCAR', scale)
            #os.symlink('../frozen_model.pb', 'frozen_model.pb')
            #shutil.copyfile(potential, 'frozen_model.pb')
            task_num += 1
            os.chdir(cwd)

        for kk in task_list:
            poscar = os.path.join(kk, 'POSCAR')
            inter = make_calculator(inter_param_prop, poscar)
            inter.make_potential_files(os.path.abspath(kk))
            # dlog.debug(prop.task_type())  ### debug
            inter.make_input_file(kk, 'eos', parameter)
            os.chdir(kk)
            if os.path.islink('frozen_model.pb'):
                os.remove('frozen_model.pb')
            shutil.copyfile(potential, 'frozen_model.pb')
            os.chdir(cwd)

        os.chdir(path_to_work)
        if os.path.islink('frozen_model.pb'):
            os.remove('frozen_model.pb')
        shutil.copyfile(potential, 'frozen_model.pb')
        os.chdir(cwd)
        # with open('eos_make_log.txt', 'w+') as fout:
        #     print('eos make end', file=fout)
        return op_out

class EosPost(OP):
    def __init__(self):
        pass

    @classmethod
    def get_input_sign(cls):
        return OPIOSign({
            'result_tasks': Artifact(Path)
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
                     op_in['result_tasks'])

        return op_out


if __name__ == "__main__":
    wf = Workflow(name="eos-make")

    artifact0 = upload_artifact("param.json")
    artifact1 = upload_artifact("POSCAR")
    artifact2 = upload_artifact("frozen_model.pb")
    print(artifact0)
    print(artifact1)
    print(artifact2)
    # print(artifact3)
    step = Step(
        name="step",
        template=PythonOPTemplate(EosMake, image="zhuoyli/dflow_test:cn"),
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
