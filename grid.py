import glob
import multiprocessing as mp
import threading
import time
import os, sys
import shutil
import tarfile
from itertools import repeat

import numpy as np
from MESAcontroller import MesaAccess, ProjectOps
from rich import print, progress, prompt, live, console, panel

import helper

def progress_columns(n):
    progress_columns = (#progress.TextColumn(helper.scrap_age(n)),
                progress.SpinnerColumn(),
                progress.TextColumn("[progress.description]{task.description}"),
                progress.BarColumn(bar_width=60),
                progress.MofNCompleteColumn(),
                progress.TaskProgressColumn(),
                progress.TimeElapsedColumn())
    return progress_columns

def live_display(n):
    ## Progress bar
    progressbar = progress.Progress(*progress_columns(n), disable=False)
    group = console.Group(panel.Panel(progressbar, expand=False), panel.Panel(helper.scrap_age(n), expand=False))
    return live.Live(group), progressbar, group

def update_live_display(live_disp, progressbar, group, n, stop=False):
    try:
        while True:
            group = console.Group(panel.Panel(progressbar, expand=False), panel.Panel(helper.scrap_age(n), expand=False))
            time.sleep(0.3)
            live_disp.update(group, refresh=True)
            if stop is True:
                break
    except KeyboardInterrupt:
        raise KeyboardInterrupt


    
def evo_star(mass, metallicity, coarse_age, v_surf_init=0, model=0, rotation=True, 
            save_model=False, logging=True, loadInlists=False, parallel=False):
    ## Create working directory
    name = f"gridwork/work_{model}"
    proj = ProjectOps(name)     
    proj.create(overwrite=True) 
    proj.make()
    star = MesaAccess(name)
    star.load_HistoryColumns("./templates/history_columns.list")
    star.load_ProfileColumns("./templates/profile_columns.list")

    initial_mass = mass
    Zinit = metallicity

    ## Get Parameters
    terminal_age = float(np.round(2500/initial_mass**2.5,1)*1.0E6)
    phases_params = helper.phases_params(initial_mass, Zinit)     
    if rotation:
        templates = sorted(glob.glob("./urot/*inlist*"))
        # phase_max_age = [1.0E-3, 0.25E6, 1E6, coarse_age, 4.0E7, terminal_age]
        phase_max_age = [1.0E-3, 2E6, coarse_age, 4.0E7, terminal_age]
        rotation_init_params = {'change_v_flag': True,
                                'new_v_flag': True,
                                'change_rotation_flag': True,
                                'new_rotation_flag': True,
                                'set_initial_surface_rotation_v': True,
                                'set_surface_rotation_v': True,
                                'new_surface_rotation_v': v_surf_init,
                                'set_uniform_am_nu_non_rot': True}
    else:
        templates = sorted(glob.glob("./inlists/*inlist*"))
        phase_max_age = [1.0E-3, 2E6, coarse_age, 4.0E7, terminal_age]

    if loadInlists:
        ## Run MESA from pre-made inlists
        for phase_name in phases_params.keys():
            print(phase_name)
            star.load_InlistProject(templates.pop(0))
            star.set('initial_mass', initial_mass, force=True)
            star.set('initial_z', Zinit, force=True)
            star.set('max_age', phase_max_age.pop(0))
            if phase_name == "Start rotation":
                star.set('new_surface_rotation_v', v_surf_init)
            if phase_name == "Initial Contraction":
                proj.run(logging=logging, parallel=parallel)
            else:
                proj.resume(logging=logging, parallel=parallel)
    else:
        ## Run MESA from inlist template by setting parameters for each phase
        inlist_template = "./templates/inlist_template"
        for phase_name, input_params in phases_params.items():
            print(phase_name)
            star.load_InlistProject(inlist_template)
            star.set(input_params, force=True)
            star.set('max_age', phase_max_age.pop(0))
            if phase_name == "Initial Contraction":
                if rotation:
                    ## Initiate rotation
                    star.set(rotation_init_params, force=True)
                proj.run(logging=logging, parallel=parallel)
            else:
                proj.resume(logging=logging, parallel=parallel)

    # Run GYRE
    proj = ProjectOps(name)
    proj.runGyre(gyre_in="templates/gyre_rot_template_dipole.in", data_format="FGONG", files='all', logging=True, parallel=False)
    # proj.runGyre(gyre_in="templates/gyre_rot_template_l2.in", data_format="FGONG", files='all', logging=True, parallel=False)
    # proj.runGyre(gyre_in="templates/gyre_rot_template_all_modes.in", data_format="FGONG", files='all', logging=True, parallel=False)

    ## Archive LOGS
    os.mkdir(f"grid_archive/gyre/freqs_{model}")
    shutil.copy(f"{name}/LOGS/history.data", f"grid_archive/histories/history_{model}.data")
    shutil.copy(f"{name}/LOGS/profiles.index", f"grid_archive/profiles/profiles_{model}.index")
    for file in glob.glob(f"{name}/LOGS/*-freqs.dat"):
        shutil.copy(file, f"grid_archive/gyre/freqs_{model}")
    if save_model:
        compressed_file = f"grid_archive/models/model_{model}.tar.gz"
        with tarfile.open(compressed_file,"w:gz") as tarhandle:
            tarhandle.add(name, arcname=os.path.basename(name))
    shutil.rmtree(name)




def run_grid(parallel=False, show_progress=False, create_grid=True, rotation=True, save_model=True, 
            loadInlists=False, logging=True, overwrite=None, testrun=False):
    if testrun:
        masses = [1.36, 1.36, 1.36, 1.36, 1.36, 1.36]
        metallicities = [0.001, 0.001, 0.001, 0.001, 0.001, 0.001]
        coarse_age_list = [1E6, 1E6, 1E6, 1E6, 1E6, 1E6]
        v_surf_init_list = [0.1, 1, 5, 10, 15, 20]
    else:
        if create_grid:
            ## Create grid
            sample_masses = np.arange(1.36, 2.22, 0.02)                ## 1.36 - 2.20 Msun (0.02 Msun step)
            sample_metallicities = np.arange(0.001, 0.0101, 0.0001)    ## 0.001 - 0.010 (0.0001 step)
            masses = np.repeat(sample_masses, len(sample_metallicities))
            metallicities = np.tile(sample_metallicities, len(sample_masses))
            coarse_age_list = 1E6 * np.ones(len(masses))               ## 1E6 yr
            v_surf_init_list = np.random.randint(1, 10, len(masses)).astype(float) * 30

        else:
            ## Load grid
            arr = np.genfromtxt("coarse_age_map.csv",
                            delimiter=",", dtype=str, skip_header=1)
            masses = arr[:,0].astype(float)
            metallicities = arr[:,1].astype(float)
            coarse_age_list = [age*1E6 if age != 0 else 20*1E6 for age in arr[:,2].astype(float)]
            v_surf_init_list = np.random.randint(1, 10, len(masses)).astype(float) * 30

    ## Create archive directories
    if os.path.exists("grid_archive"):
        if overwrite:
            shutil.rmtree("grid_archive")
        else:
            if overwrite is None:
                if prompt.Confirm.ask("Overwrite existing grid_archive?"):
                    shutil.rmtree("grid_archive")
            if os.path.exists("grid_archive"):
                print("Moving old grid_archive(s) to grid_archive_old(:)")
                old = 0
                while os.path.exists(f"grid_archive_old{old}"):
                    old += 1
                    if old >= 3:
                        break
                while old > 0:
                    shutil.move(f"grid_archive_old{old-1}", f"grid_archive_old{old}")
                    old -= 1
                shutil.move("grid_archive", f"grid_archive_old{old}")    
    os.mkdir("grid_archive")
    os.mkdir("grid_archive/models")
    os.mkdir("grid_archive/histories")
    os.mkdir("grid_archive/profiles")
    os.mkdir("grid_archive/gyre")

    ## Create work directory
    if os.path.exists("gridwork"):
        shutil.rmtree("gridwork")
    os.mkdir("gridwork")


    ## Run grid ##
    if parallel:
        ## Run grid in parallel
        ## OMP_NUM_THREADS x n_processes = Total cores available
        n_processes = -(-os.cpu_count() // int(os.environ['OMP_NUM_THREADS']))  ## Gives best performance
        n_processes -= 1


        live_disp, progressbar, group = live_display(n_processes)
        with live_disp:
            length = len(masses)
            task = progressbar.add_task("[b i green]Running...", total=length)
            args = zip(masses, metallicities, coarse_age_list, v_surf_init_list,
                    range(length), repeat(rotation), repeat(save_model), 
                    repeat(logging), repeat(loadInlists), repeat(parallel))
            try:
                stop_thread = False
                thread = threading.Thread(target=update_live_display, 
                            args=(live_disp, progressbar, group, n_processes, lambda : stop_thread,))
                thread.start()
                with mp.Pool(n_processes, initializer=helper.mute) as pool:
                    for proc in pool.istarmap(evo_star, args):
                        progressbar.advance(task)
                stop_thread = True
                thread.join()
            except KeyboardInterrupt:
                os.system("echo && echo KeyboardInterrupt && echo")
                os._exit(1)
                
    else:
        # Run grid in serial
        model = 1
        for mass, metallicity, v_surf_init, coarse_age in zip(masses, metallicities, v_surf_init_list, coarse_age_list):
            print(f"[b i yellow]Running model {model} of {len(masses)}")
            evo_star(mass, metallicity, coarse_age, v_surf_init, model=model, 
                        rotation=rotation, save_model=save_model, logging=logging, loadInlists=loadInlists)

            model += 1
            print(f"[b i green]Done with model {model-1} of {len(masses)}")
            # os.system("clear")

## Main script
if __name__ == "__main__":
    # run_grid()
    run_grid(parallel=True, show_progress=True, save_model=True, overwrite=True, testrun=False)

    

