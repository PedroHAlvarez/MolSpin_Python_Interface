import MolSpinPy
import json
import os
import shutil
import numpy as np

def main():
    MolSpinPy.utility.regex_functions.test_tensor_input()
    MolSpinPy.msd.FileTemplate.test()

    ss = MolSpinPy.objects.spin_system.SpinSystem("test")
    e1 = MolSpinPy.objects.spin_object.Electron("e1")
    x = e1.spin
    e1.spin = 4.0
    #x = 0.5
    #e1.set_spin_value(1.0)
    #e1.set_spin_value(1.2)
    ss.add_electron(e1)
    a = ss.ConvertToDictionary()
    print(a)

    dat = MolSpinPy.msd.MsdHandling.ConvertMSDtoDictionary("NV_centre_N14_GS_T-0.msd")
    test2 = MolSpinPy.msd.FileTemplate.get_template("BasicTemplate.msd")
    print(test2.render_to_file(dat, "output2.msd"))

    @MolSpinPy.ActionScript
    def test_action_1(step,var,a):
        return var + (step * a)
    @MolSpinPy.ActionScript
    def test_action_2(step,a : float,b : int):
        return a + step * b
    @MolSpinPy.ActionScript
    def test_action_3(a,b):
        return a + b
    @MolSpinPy.ActionScript
    def test_action_5(var,a,b):
        var.value = a+b
    #@MolSpinPy.objects.ActionScript
    #def test_action_4(a,b):
    #   print(a+b)


    #Action = MolSpinPy.objects.Action(e1.spin,test_action_1,duration=2,interval=1, loop = True)
    #Action2 = MolSpinPy.objects.Action(e1.g_tensor, test_action_2, duration = 2, interval=2, a = 5, b=3, parent = Action)
    #Action3 = MolSpinPy.objects.Action(e1.spin, test_action_3, duration = 5, loop = True, a = 3, b =4, parent = Action2)
    #Action4 = MolSpinPy.objects.Action(e1.spin, MolSpinPy.objects.Actions.LineSpaceScalar(0,0.1,num=100), duration = 100, loop = True)
    #Action5 = MolSpinPy.objects.Action(dat['spinsystems']['GS']['transitions']['T0UP'], MolSpinPy.objects.Actions.LineSpaceScalar(0,0.1,num=100), duration = 100, loop = True, key = 'rate')
    #Action6 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LineSpaceScalar(0,0.1,num=100), duration = 100, loop = True, key = 'spinsystems.GS.transitions.T0UP.rate')
    #Action7 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LineSpaceVector(0,0.1,num=100, direction = MolSpinPy.maths.vector.Vector("0.0 1.0 0.5")), duration = 100, loop = True, key = 'spinsystems.GS.interactions.zeeman.field')
    StrainModAction = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LogSpaceVector(start = 5e-6, stop = 5e-2, num = 100, Exponent = False, Normalize = False,direction = MolSpinPy.maths.vector.Vector("1.0 1.0 1.0")), duration = 100, loop = True, key = 'spinsystems.GS.interactions.strain.e')
    StrainFixedAction = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LogSpaceVector(start = 1e-5, stop = 1e-1, num = 100, Exponent = False, Normalize = False, direction = MolSpinPy.maths.vector.Vector("1.0 1.0 1.0")), duration = 100, loop = True, key = 'spinsystems.GS.interactions.strain_modulated.e')
    manager = MolSpinPy.runtime.ActionManager()
    manager.add_action(StrainModAction)
    manager.add_action(StrainFixedAction)
    #manager.add_action(Action6)
    #manager.add_action(Action7)

    test = MolSpinPy.runtime.Project("test")
    test.attach_dict(dat)
    test._extract_settings()
    test.attach_ActionManager(manager)
    test._dryRun()
    #test._dryRun()
    test.Deploy()
    #id = test.SubmitToHPC(hpc_username="u28375",hpc_host="glogin-p2.hpc.gwdg.de",
    #hpc_key_path="~/.ssh/id_ed25519", remote_binary_path="/projects/extern/nhr/nhr_ni/nip00058/dir.project/MolSpin/MolSpin",
    #remote_working_dir="/user/benjamin.tigg/u28375", calcs_per_node=20, partition="medium96s:test")
    #id= 13921951
    #test.WatchHPC(id)
    #test.DownloadFromHPC(id, remote_working_dir="/user/benjamin.tigg/u28375", local_npz_output_path="results/")
    #Action7.Test()
    #Action.a = 1
    #Action.state.a = 1
    #for i in range(0,10000):
    #    #s1 = Action.step(i,True)
    #    #s2 = Action2.step(i,True)
    #    #s3 = Action3.step(i, True)
    #    #s4 = Action4.step(i)
    #    #s5 = Action5.step(i)
    #    s6 = Action6.step(i)
    #    s7  = Action7.step(i)
    #    #print(f"{s1},{s2},{s3}")
    #print("end of testing")

#main()

def StrainT1times():
    #potentially create a wrapper object for the dictionary that encompesses the case map but behaves like a normal dictionary otherwise, so that the user can use the case map to access values in the dictionary without worrying about the case sensitivity of the keys. This would be a more elegant solution than having to pass around the case map separately and manually use it to access values in the dictionary.
    #dat = MolSpinPy.msd.MsdHandling.ConvertMSDtoDictionary("NV_centre_N14_GS_T-0.msd")
    dat = MolSpinPy.msd.MsdHandling.ConvertMSDtoDictionary("NV_centre_N14.msd")

    #@MolSpinPy.ActionScript
    #def IsotropicPhononBath(step, var, state, start, stop, num):
    #    return

    
    #creating a test action variable
    test_list_var = MolSpinPy.objects.DictionaryBoundVariable.test_create(dat, 'spinsystems.GS.interactions.strain_modulated.e')

    StrainModAction = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LogSpaceVector(start = 5e-6, stop = 5e-2, num = 100, Exponent = False, Normalize = False,direction = MolSpinPy.maths.vector.Vector("1.0 1.0 1.0")), duration = 100, loop = True, key = 'spinsystems.GS.interactions.strain_modulated.e')
    StrainFixedAction = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LogSpaceVector(start = 1e-5, stop = 1e-1, num = 100, Exponent = False, Normalize = False, direction = MolSpinPy.maths.vector.Vector("1.0 1.0 1.0")), duration = 100, loop = True, key = 'spinsystems.GS.interactions.strain.e')
    manager = MolSpinPy.runtime.ActionManager()
    manager.add_action(StrainModAction)
    manager.add_action(StrainFixedAction)
    project = MolSpinPy.runtime.Project("StrainT1times-3")
    project.attach_dict(dat)
    project._extract_settings()
    project.attach_ActionManager(manager)
    # cluster_profile is a registered name ("gwdg", "rosa", see HpcProfile.available())
    # or an HpcProfile instance (see CustomClusterProfile below).
    project.LoadHPC(hpc_username="u28375",hpc_host="glogin-p2.hpc.gwdg.de", hpc_key_path="~/.ssh/id_ed25519", remote_working_dir="/user/benjamin.tigg/u28375", cluster_profile="gwdg")
    # First time on a cluster: clone + (venv) + build. Afterwards use UpdateBinary.
    # project.InstallBinary("/projects/extern/nhr/nhr_ni/nip00058/dir.project/MolSpinBenji", repo_url="https://github.com/<owner>/MolSpin.git",
    #                       armadillo_path="/projects/extern/nhr/nhr_ni/nip00058/dir.project/armadillo-12")
    # Partition, modules and make args come from the profile; armadillo_path is only
    # used by profiles with use_external_armadillo_path=True (gwdg).
    project.UpdateBinary("/projects/extern/nhr/nhr_ni/nip00058/dir.project/MolSpinBenji", armadillo_path="/projects/extern/nhr/nhr_ni/nip00058/dir.project/armadillo-12")
    return
    # partition defaults to the profile's default_partition when omitted
    id = project.SubmitToHPC(hpc_username="u28375",hpc_host="glogin-p2.hpc.gwdg.de",
    hpc_key_path="~/.ssh/id_ed25519", remote_binary_path="/projects/extern/nhr/nhr_ni/nip00058/dir.project/MolSpinBenji",
    remote_working_dir="/user/benjamin.tigg/u28375", partition="standard96s:test", walltime="1:00:00", max_nodes=5, max_concurrent=10, est_sim_time=0.5, safety_buffer=1.4,
    armadillo="/projects/extern/nhr/nhr_ni/nip00058/dir.project/armadillo-12")
    #id= 13921951
    #id = ['14453268','14453267']
    project.WatchHPC(id)
    #project.LoadHPC(hpc_username="u28375",hpc_host="glogin-p2.hpc.gwdg.de",
    #    hpc_key_path="~/.ssh/id_ed25519", remote_binary_path="/projects/extern/nhr/nhr_ni/nip00058/dir.project/MolSpinBenji",
    #    remote_working_dir="/user/benjamin.tigg/u28375")
    project.DownloadFromHPC(id, remote_working_dir="/user/benjamin.tigg/u28375", local_npz_output_path="results/")
    #project.Deploy(NPZ = True, max_processes = 20)

def CustomClusterProfile():
    # Dummy profile for a made-up cluster. Nothing here is real: replace the
    # modules/partitions with what `module avail` and `sinfo` show on your cluster.
    dummy = MolSpinPy.runtime.HpcProfile(
        name="dummycluster",
        default_partition="compute",
        runtime_modules=("gcc/12.2.0", "Armadillo/12.6.0", "python/3.11"),
        build_modules=("gcc/12.2.0", "Armadillo/12.6.0"),
        build_partition="debug",
        activate_venv=True,
        use_external_armadillo_path=False,
        build_make_args=("ARCHFLAGS=",),
        metadata_extra={"cluster_profile": "dummycluster"},
    )

    # Option 1: register it so it can be selected by name.
    MolSpinPy.runtime.HpcProfile.register(dummy)
    print(MolSpinPy.runtime.HpcProfile.available())  # ['dummycluster', 'gwdg', 'rosa']

    dat = MolSpinPy.msd.MsdHandling.ConvertMSDtoDictionary("NV_centre_N14.msd")
    project = MolSpinPy.runtime.Project("DummyClusterTest")
    project.attach_dict(dat)
    project._extract_settings()
    project.attach_ActionManager(MolSpinPy.runtime.ActionManager())
    project.LoadHPC(hpc_username="user", hpc_host="login.dummy.example", hpc_key_path="~/.ssh/id_ed25519",
                    remote_working_dir="/home/user/work", cluster_profile="dummycluster")

    # Option 2: pass the instance directly (no registration needed), optionally tweaked:
    #   cluster_profile=dummy.with_overrides(default_partition="gpu")
    #
    # project.UpdateBinary("/home/user/MolSpin")
    # id = project.SubmitToHPC(hpc_username="user", hpc_host="login.dummy.example", hpc_key_path="~/.ssh/id_ed25519",
    #                          remote_binary_path="/home/user/MolSpin", remote_working_dir="/home/user/work")
    # project.WatchHPC(id)
    # project.DownloadFromHPC(id, remote_working_dir="/home/user/work", local_npz_output_path="results/")

def StrainPL():
    dat = MolSpinPy.msd.MsdHandling.ConvertMSDtoDictionary("NV_centre_N14.msd")
    StrainModAction1 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LogSpaceVector(start = 5e-6, stop = 5e-2, num = 100, Exponent = False, Normalize = False,direction = MolSpinPy.maths.vector.Vector("1.0 1.0 1.0")), duration = 100, loop = True, key = 'spinsystems.GS.interactions.strain_modulated.e')
    StrainFixedAction1 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LogSpaceVector(start = 1e-5, stop = 1e-1, num = 100, Exponent = False, Normalize = False, direction = MolSpinPy.maths.vector.Vector("1.0 1.0 1.0")), duration = 100, loop = True, key = 'spinsystems.GS.interactions.strain.e')
    StrainModAction2 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LogSpaceVector(start = 5e-6, stop = 5e-2, num = 100, Exponent = False, Normalize = False,direction = MolSpinPy.maths.vector.Vector("1.0 1.0 1.0")), duration = 100, loop = True, key = 'spinsystems.ES.interactions.strain_modulated.e')
    StrainFixedAction2 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LogSpaceVector(start = 1e-5, stop = 1e-1, num = 100, Exponent = False, Normalize = False, direction = MolSpinPy.maths.vector.Vector("1.0 1.0 1.0")), duration = 100, loop = True, key = 'spinsystems.ES.interactions.strain.e')
    BFieldScan1 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LineSpaceVector(start = 0.0, stop = 0.15, num = 150, Normalize=True, direction=MolSpinPy.maths.vector.Vector("0.0 0.0 1.0")),duration=150, key='spinsystems.GS.interactions.zeeman.field',interval=100)
    BFieldScan2 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LineSpaceVector(start = 0.0, stop = 0.15, num = 150, Normalize=True, direction=MolSpinPy.maths.vector.Vector("0.0 0.0 1.0")),duration=150, key='spinsystems.ES.interactions.zeeman.field',interval=100)
    BFieldScan3 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LineSpaceVector(start = 0.0, stop = 0.15, num = 150, Normalize=True, direction=MolSpinPy.maths.vector.Vector("0.0 0.0 1.0")),duration=150, key='spinsystems.GS.interactions.nuclearzeeman.field',interval=100)
    BFieldScan4 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LineSpaceVector(start = 0.0, stop = 0.15, num = 150, Normalize=True, direction=MolSpinPy.maths.vector.Vector("0.0 0.0 1.0")),duration=150, key='spinsystems.ES.interactions.nuclearzeeman.field',interval=100)
    manager = MolSpinPy.runtime.ActionManager()
    manager.add_action(StrainModAction1)
    manager.add_action(StrainFixedAction1)
    manager.add_action(StrainModAction2)
    manager.add_action(StrainFixedAction2)
    manager.add_action(BFieldScan1)
    manager.add_action(BFieldScan2)
    manager.add_action(BFieldScan3)
    manager.add_action(BFieldScan4)
    project = MolSpinPy.runtime.Project("PL-Strain")
    project.attach_dict(dat)
    project._extract_settings()
    project.attach_ActionManager(manager)
    
    #project._dryRun()
    project.Deploy(NPZ=True, max_processes=20)

def test():
    dat = MolSpinPy.msd.MsdHandling.ConvertMSDtoDictionary("MagLOV.msd")
    _template = MolSpinPy.msd.FileTemplate.get_template("BasicTemplate.msd")
    _template.render_to_file(dat, "output.msd")
    print(dat)

def test2():
    #build a radical pair
    from MolSpinPy.objects.spin_object import Electron, Nucleus
    from MolSpinPy.objects.spin_system import SpinSystem
    from MolSpinPy.objects.interactions import Zeeman_Interaction, Hyperfine_Interaction, Dipolar_Interaction

    radical_pair = SpinSystem("radical_pair")
    e1 = Electron("e1")
    e2 = Electron("e2")
    radical_pair.add_electron(e1)
    radical_pair.add_electron(e2)
    n1 = Nucleus("n1")
    n1.spin = 1
    radical_pair.add_nucleus(n1)
    zeeman = Zeeman_Interaction("zeeman", [e1,e2], field=MolSpinPy.maths.vector.Vector("0.0 0.0 0.1"))
    hyperfine = Hyperfine_Interaction("hyperfine", spin1=e1, spin2=n1, tensor=MolSpinPy.maths.Isotropic("0.01"))
    dipolar = Dipolar_Interaction("dipolar", spin1=e1,spin2=e2, tensor=MolSpinPy.maths.tensor.Anisotropic("-0.01,-0.01,0.02"))
    radical_pair.add_interaction(zeeman)
    radical_pair.add_interaction(hyperfine)
    radical_pair.add_interaction(dipolar)


    t0 = radical_pair.add_state(MolSpinPy.objects.State("T0", definition=([e1,e2], [(1, [1, -1]), (1, [-1, 1])])))
    tp = radical_pair.add_state(MolSpinPy.objects.State("T+", definition=([e1,e2], [(1, [1, 1])])))
    tm = radical_pair.add_state(MolSpinPy.objects.State("T-", definition=([e1,e2], [(1, [-1, -1])])))
    s = radical_pair.add_state(MolSpinPy.objects.State("S", definition=([e1,e2], [(1, [1, -1]), (-1, [-1, 1])])))

    #n1u = radical_pair.add_state(MolSpinPy.objects.State("n1u", definition={n1: 1}))
    radical_pair.add_transition(MolSpinPy.objects.Transition(name="test",source=t0, targetstate=tp, rate=0.01,include_all_nuclear=True))

    ss_name, test_dict_rp = radical_pair.ConvertToDictionary()
    print(test_dict_rp)

    test_dict = {
        "spinsystems": {
            ss_name: test_dict_rp 
        }
    }

    #render to msd file
    _template = MolSpinPy.msd.FileTemplate.get_template("BasicTemplate.msd")
    _template.render_to_file(test_dict, "radical_pair_test.msd")




METADATA_TEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metadata_test_output")

def write_and_read_metadata(metadata, steps, label="metadata"):
    """Write the metadata JSON/markdown files to a local folder and return (json_path, parsed_json)."""
    out_dir = os.path.join(METADATA_TEST_DIR, label)
    os.makedirs(out_dir, exist_ok=True)
    json_path, md_path = metadata.write(out_dir, steps=steps, execution_mode="local")
    assert os.path.isfile(json_path) and os.path.isfile(md_path)
    with open(json_path, "r", encoding="utf-8") as f:
        return json_path, json.load(f)

def test_loader_roundtrip():
    from MolSpinPy.objects import Settings, Task
    from MolSpinPy.objects.spin_object import Electron
    from MolSpinPy.runtime import ProjectMetadata, ProjectLoader
    from MolSpinPy.maths.vector import Vector
    from MolSpinPy.objects import interactions

    p = MolSpinPy.runtime.Project("t")
    ss = MolSpinPy.objects.spin_system.SpinSystem("GS")
    ss.add_electron(Electron("e1"))
    ss.add_interaction(interactions.Zeeman_Interaction("zeeman", ss.electrons[0], field=Vector("0.0 0.0 0.1")))
    p.add_spin_system(ss)
    p.set_settings(Settings(steps=5))
    p.add_task(Task("TE", type="x"))

    @MolSpinPy.ActionScript
    def foo(step, var, a=2):
        return np.asarray(var) + a

    a1 = MolSpinPy.objects.Action(p.MSDdict, MolSpinPy.objects.Actions.LineSpaceVector(start=0, stop=1, num=5, direction=Vector("0 0 1")),
                                  key='spinsystems.GS.interactions.zeeman.field', duration=5, loop=True)
    a2 = MolSpinPy.objects.Action(p.MSDdict, foo, key='spinsystems.GS.interactions.zeeman.field', parent=a1, a=3)
    m = MolSpinPy.runtime.ActionManager()
    m.add_action(a1)
    m.add_action(a2, priority=2)
    json_path, md = write_and_read_metadata(ProjectMetadata("t", p._template, p.MSDdict, m, p._settings), 5, "loader_roundtrip")

    try:
        ProjectLoader(json_path).build()
    except PermissionError as e:
        print("blocked:", e)
    q = ProjectLoader(json_path, allow_code=True).build()
    assert q.MSDdict["settings"] == p.MSDdict["settings"] and q._settings["steps"] == 5
    assert q.MSDdict["spinsystems"] == p.MSDdict["spinsystems"]
    md2 = ProjectMetadata("t", q._template, q.MSDdict, q.manager, q._settings).as_dict(5, "local")
    for k in ("function_type", "function_config", "function_parameters", "timing", "priority", "parent_id", "key", "children", "sequences"):
        assert [a[k] for a in md["parameter_sweep"]["actions"]] == [a[k] for a in md2["parameter_sweep"]["actions"]], k
    print("loader roundtrip ok")

def test_object_bound_actions():
    from MolSpinPy.objects import Settings, Task, State, Transition
    from MolSpinPy.objects.spin_object import Electron, Nucleus
    from MolSpinPy.runtime import ProjectMetadata, ProjectLoader
    from MolSpinPy.maths.vector import Vector
    from MolSpinPy.maths import tensor
    from MolSpinPy.objects import interactions

    p = MolSpinPy.runtime.Project("t")
    ss = MolSpinPy.objects.spin_system.SpinSystem("GS")
    e1 = ss.add_electron(Electron("e1"))
    n1 = ss.add_nucleus(Nucleus("n1"))
    ss.add_interaction(interactions.Zeeman_Interaction("zeeman", e1, Vector("0.0 0.0 0.1")))
    ss.add_interaction(interactions.Hyperfine_Interaction("hf", e1, n1, tensor.Anisotropic("1.0, 2.0, 3.0")))
    s0 = ss.add_state(State("S", "spin(e1) = |0.5>"))
    tr = ss.add_transition(Transition("decay", source="S", rate=0.01))
    ss.set_property("initialstate", s0)
    p.add_spin_system(ss)
    p.set_settings(Settings(steps=4))
    p.add_task(Task("TE", type="x"))

    # two object-bound actions and one dictionary-bound action
    a1 = MolSpinPy.objects.Action(e1.spin, MolSpinPy.objects.Actions.LineSpaceScalar(0.5, 2.0, num=4), duration=4, loop=True)
    a2 = MolSpinPy.objects.Action(tr.rate, MolSpinPy.objects.Actions.LineSpaceScalar(0.1, 0.4, num=4), duration=4, loop=True)
    a3 = MolSpinPy.objects.Action(p.MSDdict, MolSpinPy.objects.Actions.LineSpaceVector(start=0, stop=1, num=4, direction=Vector("0 0 1")),
                                  key='spinsystems.GS.interactions.zeeman.field', duration=4, loop=True)
    m = MolSpinPy.runtime.ActionManager(registry={})
    for a in (a1, a2, a3):
        m.add_action(a)
    p.attach_ActionManager(m)

    json_path, md = write_and_read_metadata(
        ProjectMetadata("t", p._template, p.MSDdict, m, p._settings, spin_systems=p._spin_systems), 4, "object_bound")
    print([a["binding"] for a in md["parameter_sweep"]["actions"]])

    def run(proj):
        out = []
        for i in range(4):
            proj.manager.run(i)
            proj._sync_object_systems()
            d = proj.MSDdict["spinsystems"]["GS"]
            out.append((d["spins"]["electrons"]["e1"]["spin"], d["transitions"]["decay"]["rate"]))
        return out

    q = ProjectLoader(json_path).build()
    r1, r2 = run(p), run(q)
    print(r1)
    print(r2)
    assert r1 == r2 and r1[3][0] == 2.0
    print("object-bound roundtrip ok")

def test_dictionary_bound_loader():
    from MolSpinPy.runtime import ProjectMetadata, ProjectLoader
    from MolSpinPy.maths.vector import Vector

    p = MolSpinPy.runtime.Project("t")
    dat = MolSpinPy.msd.MsdHandling.ConvertMSDtoDictionary("4H_SiC_strain_relaxation.msd")
    p.attach_dict(dat)
    p._extract_settings()
    a1 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LineSpaceVector(start=0, stop=1, num=5, direction=Vector("0 0 1")),
                                  key='spinsystems.GS.interactions.zeeman.field', duration=5, loop=True)
    m = MolSpinPy.runtime.ActionManager(registry={})
    m.add_action(a1)
    json_path, md = write_and_read_metadata(ProjectMetadata("t", p._template, p.MSDdict, m,     p._settings), 5, "dictionary_bound")
    q = ProjectLoader(json_path).build()
    for i in range(5):
        m.run(i)
        q.manager.run(i)
    assert m._actions[0].value.tolist() == q.manager._actions[0].value.tolist()
    print("dictionary-bound loader ok", q.manager._actions[0].value)

def test_custom_action_passing():
    from MolSpinPy.objects import Settings
    from MolSpinPy.objects.spin_object import Electron
    from MolSpinPy.runtime import ProjectMetadata, ProjectLoader

    p = MolSpinPy.runtime.Project("t")
    ss = MolSpinPy.objects.spin_system.SpinSystem("GS")
    e1 = ss.add_electron(Electron("e1"))
    tr = ss.add_transition(MolSpinPy.objects.Transition("decay", source="S", rate=0.01))
    p.add_spin_system(ss)
    p.set_settings(Settings(steps=6))

    @MolSpinPy.ActionScript
    def ramp(step, var, state, gain=2.0, offset=0.5):
        if step == 0:
            state.total = 0.0
        state.total += gain
        return offset + state.total + np.sqrt(4.0)

    @MolSpinPy.ActionScript
    def from_list(step, var, values):
        return values

    # gain is overridden, offset keeps its default, values is a per-step sequence
    a1 = MolSpinPy.objects.Action(e1.spin, ramp, duration=6, loop=True, gain=3.0)
    a2 = MolSpinPy.objects.Action(tr.rate, from_list, duration=6, loop=True, values=[0.1, 0.2, 0.3])
    m = MolSpinPy.runtime.ActionManager(registry={})
    m.add_action(a1)
    m.add_action(a2)
    p.attach_ActionManager(m)

    json_path, md = write_and_read_metadata(
        ProjectMetadata("t", p._template, p.MSDdict, m, p._settings, spin_systems=p._spin_systems), 6, "custom_actions")
    entries = md["parameter_sweep"]["actions"]
    assert entries[0]["function_parameters"] == {"gain": 3.0, "offset": 0.5}, entries[0]["function_parameters"]
    assert "def ramp" in entries[0]["function_source"] and entries[0]["function_source_sha256"]
    assert entries[1]["sequences"] == {"values": [0.1, 0.2, 0.3]}, entries[1]["sequences"]

    # custom functions must not run without explicit permission
    try:
        ProjectLoader(json_path).build()
        raise AssertionError("custom function loaded without allow_code")
    except PermissionError:
        pass

    # a tampered source in the file on disk must be rejected
    import copy, os
    bad = copy.deepcopy(md)
    bad["parameter_sweep"]["actions"][0]["function_source"] = bad["parameter_sweep"]["actions"][0]["function_source"].replace("offset +", "offset -")
    bad_path = os.path.join(os.path.dirname(json_path), "tampered_metadata.json")
    with open(bad_path, "w", encoding="utf-8") as f:
        json.dump(bad, f)
    try:
        ProjectLoader(bad_path, allow_code=True).build()
        raise AssertionError("tampered source was accepted")
    except ValueError:
        pass

    # the rebuilt actions must behave identically to the originals
    q = ProjectLoader(json_path, allow_code=True).build()
    qe1 = q._spin_systems["GS"].electrons[0]
    qtr = q._spin_systems["GS"].transitions[0]

    def run(proj, electron, transition):
        out = []
        for i in range(6):
            proj.manager.run(i)
            out.append((float(electron.spin.value), transition._rate))
        return out

    original, rebuilt = run(p, e1, tr), run(q, qe1, qtr)
    print(original)
    print(rebuilt)
    assert original == rebuilt
    assert original[0][0] == 0.5 + 3.0 + 2.0
    assert original[1][0] == 0.5 + 6.0 + 2.0
    print("custom action passing ok")

# Module level pieces used by the complex custom action below
import math
from math import sqrt as _root

SCALE = 2.0
WEIGHTS = [0.5, 1.0, 1.5]
PROFILE = np.array([1.0, 2.0, 4.0])

def _clamp(x, low, high):
    return max(low, min(high, x))

def _shape(step):
    return _clamp(WEIGHTS[step % len(WEIGHTS)] * SCALE, 0.0, 10.0) + _root(PROFILE[step % 3]) + math.floor(step / 2)

def test_custom_action_dependencies():
    import copy
    from MolSpinPy.objects import Settings
    from MolSpinPy.objects.spin_object import Electron
    from MolSpinPy.utility import code_capture
    from MolSpinPy.runtime import ProjectMetadata, ProjectLoader

    p = MolSpinPy.runtime.Project("t")
    ss = MolSpinPy.objects.spin_system.SpinSystem("GS")
    tr = ss.add_transition(MolSpinPy.objects.Transition("decay", source="S", rate=0.01))
    p.add_spin_system(ss)
    p.set_settings(Settings(steps=6))
    offset = 0.25  # closure variable

    @MolSpinPy.ActionScript
    def complex_action(step, var, gain=1.0):
        return gain * _shape(step) + offset

    a1 = MolSpinPy.objects.Action(tr.rate, complex_action, duration=6, loop=True, gain=2.0)
    m = MolSpinPy.runtime.ActionManager(registry={})
    m.add_action(a1)
    p.attach_ActionManager(m)

    json_path, md = write_and_read_metadata(
        ProjectMetadata("t", p._template, p.MSDdict, m, p._settings, spin_systems=p._spin_systems), 6, "custom_dependencies")
    entry = md["parameter_sweep"]["actions"][0]
    deps = {d["name"]: d for d in entry["function_dependencies"]}
    print([(d["kind"], d["name"]) for d in entry["function_dependencies"]])
    assert {"_shape", "_clamp", "SCALE", "WEIGHTS", "PROFILE", "_root", "math", "offset"} <= set(deps)
    assert deps["_shape"]["kind"] == "function" and deps["PROFILE"]["kind"] == "constant"
    assert deps["_root"]["source"] == "from math import sqrt as _root\n"
    order = [d["name"] for d in entry["function_dependencies"]]
    assert order.index("_clamp") < order.index("_shape")  # helpers precede what uses them
    assert "def _shape" not in entry["function_source"] and entry["function_dependencies_sha256"]

    q = ProjectLoader(json_path, allow_code=True).build()
    qtr = q._spin_systems["GS"].transitions[0]
    original, rebuilt = [], []
    for i in range(6):
        m.run(i)
        q.manager.run(i)
        original.append(float(tr._rate))
        rebuilt.append(float(qtr._rate))
    print(original)
    assert original == rebuilt and original[0] == 2.0 * (1.0 + 1.0 + 0) + 0.25

    # tampering with a dependency in the file on disk must be rejected
    bad = copy.deepcopy(md)
    for d in bad["parameter_sweep"]["actions"][0]["function_dependencies"]:
        if d["name"] == "SCALE":
            d["source"] = "SCALE = 3.0\n"
    bad_path = os.path.join(os.path.dirname(json_path), "tampered_dependency_metadata.json")
    with open(bad_path, "w", encoding="utf-8") as f:
        json.dump(bad, f)
    try:
        ProjectLoader(bad_path, allow_code=True).build()
        raise AssertionError("tampered dependency was accepted")
    except ValueError:
        pass

    # a re-hashed dependency that imports a module outside the allow-list must still be refused
    evil = copy.deepcopy(md)
    evil_deps = evil["parameter_sweep"]["actions"][0]["function_dependencies"]
    evil_deps.insert(0, {"name": "os", "kind": "import", "source": "import os\n"})
    evil["parameter_sweep"]["actions"][0]["function_dependencies_sha256"] = code_capture.dependencies_digest(evil_deps)
    evil_path = os.path.join(os.path.dirname(json_path), "disallowed_import_metadata.json")
    with open(evil_path, "w", encoding="utf-8") as f:
        json.dump(evil, f)
    try:
        ProjectLoader(evil_path, allow_code=True).build()
        raise AssertionError("disallowed import was accepted")
    except PermissionError:
        pass

    # something that cannot be captured must fail when the action is built, not silently at reload
    handle = open(__file__, "r")
    try:
        @MolSpinPy.ActionScript
        def uncapturable(step, var):
            return float(len(handle.name))
        raise AssertionError("uncapturable dependency was accepted")
    except ValueError as e:
        print("rejected:", e)
    finally:
        handle.close()
    print("custom action dependencies ok")

import fnmatch

def test_external_modules():
    import warnings
    from MolSpinPy.objects import Settings
    from MolSpinPy.runtime import ProjectMetadata, ProjectLoader
    from MolSpinPy.utility import code_capture

    # use a throwaway permitted-modules list so the test never touches the real installation's list
    permitted_file = os.path.join(METADATA_TEST_DIR, "external_modules", "permitted_modules.json")
    os.makedirs(os.path.dirname(permitted_file), exist_ok=True)
    if os.path.exists(permitted_file):
        os.remove(permitted_file)
    os.environ[code_capture.PERMITTED_MODULES_ENV] = permitted_file

    p = MolSpinPy.runtime.Project("t")
    ss = MolSpinPy.objects.spin_system.SpinSystem("GS")
    tr = ss.add_transition(MolSpinPy.objects.Transition("decay", source="S", rate=0.01))
    p.add_spin_system(ss)
    p.set_settings(Settings(steps=3))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @MolSpinPy.ActionScript
        def uses_modules(step, var):
            import colorsys  # imported inside the body
            return (0.5 if fnmatch.fnmatch("a.txt", "*.txt") else 0.1) + colorsys.rgb_to_hsv(0.0, 0.0, 0.0)[2] + step
    messages = [str(w.message) for w in caught if "allow-list" in str(w.message)]
    assert messages and "fnmatch" in messages[0] and "colorsys" in messages[0], messages

    a1 = MolSpinPy.objects.Action(tr.rate, uses_modules, duration=3, loop=True)
    m = MolSpinPy.runtime.ActionManager(registry={})
    m.add_action(a1)
    p.attach_ActionManager(m)
    json_path, md = write_and_read_metadata(
        ProjectMetadata("t", p._template, p.MSDdict, m, p._settings, spin_systems=p._spin_systems), 3, "external_modules")
    entry = md["parameter_sweep"]["actions"][0]
    assert entry["function_external_modules"] == ["colorsys", "fnmatch"], entry["function_external_modules"]
    with open(os.path.join(os.path.dirname(json_path), "t_metadata.md"), encoding="utf-8") as f:
        md_text = f.read()
    assert "WARNING" in md_text and "allow_modules" in md_text

    # refused by default, and the error names the modules
    for kwargs in ({}, {"allow_modules": ["fnmatch"]}):
        try:
            ProjectLoader(json_path, allow_code=True, **kwargs).build()
            raise AssertionError("external modules were accepted without full permission")
        except PermissionError as e:
            assert "colorsys" in str(e)

    # explicit permission works and behaves identically; nothing was remembered by the refused loads
    assert code_capture.list_permitted_modules() == []
    q = ProjectLoader(json_path, allow_code=True, allow_modules=["fnmatch", "colorsys"], remember_modules=False).build()
    assert code_capture.list_permitted_modules() == []
    qtr = q._spin_systems["GS"].transitions[0]
    for i in range(3):
        m.run(i)
        q.manager.run(i)
        assert tr._rate == qtr._rate == 0.5 + i
    ProjectLoader(json_path, allow_code=True, allow_modules=True).build()
    assert code_capture.list_permitted_modules() == []  # allow_modules=True is never remembered

    # a named permission is remembered on this installation and extends the allow-list afterwards
    ProjectLoader(json_path, allow_code=True, allow_modules=["fnmatch", "colorsys"]).build()
    assert code_capture.list_permitted_modules() == ["colorsys", "fnmatch"]
    assert os.path.isfile(permitted_file)
    ProjectLoader(json_path, allow_code=True).build()  # no allow_modules needed now
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")

        @MolSpinPy.ActionScript
        def uses_trusted(step, var):
            return float(fnmatch.fnmatch("a.txt", "*.txt")) + step
    assert not [w for w in caught if "allow-list" in str(w.message)], "remembered modules should not warn"
    # the remembered list is local: it is not written into the metadata
    assert "permitted_modules" not in json.dumps(md)

    # revoking one module makes the loader refuse it again, and name only that one
    assert code_capture.revoke_modules(["colorsys"]) == ["fnmatch"]
    try:
        ProjectLoader(json_path, allow_code=True).build()
        raise AssertionError("revoked module was still accepted")
    except PermissionError as e:
        assert "colorsys" in str(e) and "fnmatch" not in str(e)
    finally:
        os.environ.pop(code_capture.PERMITTED_MODULES_ENV, None)
    print("external modules ok")

# ---- Module level pieces for the very complex action --------------------------------------
import itertools
import functools

_MODES = {"smooth": 0.9, "sharp": 0.4, "off": None}
_PHASES = (0.0, 1.5707963267948966, 3.141592653589793)
_LABEL = "complex-action"
_ENABLED = True
_KERNEL = np.array([[0.25, 0.5, 0.25], [0.1, 0.8, 0.1]])


def _is_even(n):
    return True if n == 0 else _is_odd(n - 1)


def _is_odd(n):
    return False if n == 0 else _is_even(n - 1)


def _fib(n, _memo={}):
    if n < 2:
        return n
    if n not in _memo:
        _memo[n] = _fib(n - 1) + _fib(n - 2)
    return _memo[n]


def _cumulative(values):
    return list(itertools.accumulate(values))


def _kernel_response(signal):
    rows = [np.convolve(signal, row, mode="same") for row in _KERNEL]
    return float(np.mean(rows))


class _Smoother:
    """Exponential smoother with history; stored in the action state so it survives across steps."""
    DECAY_FLOOR = 0.05

    def __init__(self, mode):
        factor = _MODES.get(mode)
        self.factor = _MODES["smooth"] if factor is None else max(factor, self.DECAY_FLOOR)
        self.history = []

    def push(self, value):
        previous = self.history[-1] if self.history else value
        self.history.append(self.factor * previous + (1.0 - self.factor) * value)
        return self.history[-1]

    def window(self, size):
        return self.history[-size:]


def _phase_weight(step):
    def inner(index):
        return math.cos(_PHASES[index % len(_PHASES)] + step * 0.1)
    return sum(inner(i) for i in range(len(_PHASES))) / len(_PHASES)


def _guarded_ratio(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return 0.0


def test_very_complex_action():
    from MolSpinPy.objects import Settings
    from MolSpinPy.runtime import ProjectMetadata, ProjectLoader
    from MolSpinPy.utility import code_capture

    steps = 12
    p = MolSpinPy.runtime.Project("t")
    ss = MolSpinPy.objects.spin_system.SpinSystem("GS")
    tr = ss.add_transition(MolSpinPy.objects.Transition("decay", source="S", rate=0.01))
    p.add_spin_system(ss)
    p.set_settings(Settings(steps=steps))
    base_rate = 0.02  # closure variable

    @MolSpinPy.ActionScript
    def very_complex(step, var, state, mode="smooth", window=3, boost=1.0, drive=None):
        if step == 0:
            state.smoother = _Smoother(mode)
            state.drive_total = 0.0
        drive_value = 0.0 if drive is None else drive
        state.drive_total += drive_value

        raw = _phase_weight(step) + _fib(step % 10) / 10.0
        smoothed = state.smoother.push(raw)
        recent = _cumulative(state.smoother.window(window))
        response = _kernel_response(np.array(recent + [smoothed, boost]))
        parity = 1.0 if _is_even(step) else -1.0
        ratio = _guarded_ratio(response, step - 3)  # step 3 hits the ZeroDivisionError branch
        label_bonus = len(_LABEL) * 0.001 if _ENABLED else 0.0
        return abs(base_rate + 0.01 * parity * response + 0.001 * ratio + 0.001 * state.drive_total + label_bonus)

    drive = [0.0, 1.0, 0.5, 2.0, 0.0, 1.0, 0.5, 2.0, 0.0, 1.0, 0.5, 2.0]
    a1 = MolSpinPy.objects.Action(tr.rate, very_complex, duration=steps, loop=True,
                                  mode="sharp", window=4, drive=drive)
    m = MolSpinPy.runtime.ActionManager(registry={})
    m.add_action(a1)
    p.attach_ActionManager(m)

    json_path, md = write_and_read_metadata(
        ProjectMetadata("t", p._template, p.MSDdict, m, p._settings, spin_systems=p._spin_systems), steps, "very_complex")
    entry = md["parameter_sweep"]["actions"][0]
    deps = {d["name"]: d for d in entry["function_dependencies"]}
    names = [d["name"] for d in entry["function_dependencies"]]
    print(names)

    expected = {"_Smoother", "_MODES", "_fib", "_cumulative", "_kernel_response", "_phase_weight", "_guarded_ratio",
                "_is_even", "_is_odd", "_KERNEL", "_PHASES", "_LABEL", "_ENABLED", "itertools", "math", "np", "base_rate"}
    missing = expected - set(names)
    assert not missing, missing
    assert len(names) == len(set(names)), "a dependency was recorded twice"
    assert deps["_Smoother"]["kind"] == "class" and deps["_KERNEL"]["kind"] == "constant"
    assert deps["itertools"]["kind"] == "import" and deps["_MODES"]["kind"] == "constant"
    assert entry["function_external_modules"] == [], entry["function_external_modules"]
    assert entry["sequences"] == {"drive": drive}, entry["sequences"]
    # helpers must precede what uses them
    for early, late in (("_KERNEL", "_kernel_response"), ("_MODES", "_Smoother"), ("itertools", "_cumulative")):
        assert names.index(early) < names.index(late), (early, late)

    q = ProjectLoader(json_path, allow_code=True).build()
    qtr = q._spin_systems["GS"].transitions[0]
    original, rebuilt = [], []
    for i in range(steps):
        m.run(i)
        q.manager.run(i)
        original.append(tr._rate)
        rebuilt.append(qtr._rate)
    print(original)
    assert original == rebuilt, (original, rebuilt)
    assert len(set(original)) > steps // 2, "the action should produce varying values"

    # the rebuilt function must behave the same with different parameters too
    bound = q.manager._actions[0]
    assert bound.func._param["mode"] == "sharp" and bound.func._param["window"] == 4

    # corrupt one nested helper in the file on disk: the hash check must catch it
    import copy
    bad = copy.deepcopy(md)
    for d in bad["parameter_sweep"]["actions"][0]["function_dependencies"]:
        if d["name"] == "_is_odd":
            d["source"] = d["source"].replace("False", "True")
    bad_path = os.path.join(os.path.dirname(json_path), "tampered_helper_metadata.json")
    with open(bad_path, "w", encoding="utf-8") as f:
        json.dump(bad, f)
    try:
        ProjectLoader(bad_path, allow_code=True).build()
        raise AssertionError("tampered helper was accepted")
    except ValueError:
        pass
    print("very complex action ok")

def _logged(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapper

@_logged
def _decorated_helper(x):
    return x * 2

def test_decorated_helper_rejected():
    try:
        @MolSpinPy.ActionScript
        def uses_decorated(step, var):
            return _decorated_helper(step) * 0.01
    except ValueError as e:
        assert "_decorated_helper" in str(e) and "_logged" in str(e), str(e)
        print("rejected:", e)
    else:
        raise AssertionError("decorated helper was accepted")
    print("decorated helper rejected ok")

def _chain_0():
    return 1.0

def _chain_1():
    return _chain_0() + 1.0

def _chain_2():
    return _chain_1() + 1.0

def _chain_3():
    return _chain_2() + 1.0

def test_dependency_limits():
    from MolSpinPy.utility import code_capture

    def uses_chain(step, var):
        return _chain_3() * 0.01

    # action -> _chain_3 -> _chain_2 -> _chain_1 -> _chain_0 is 5 levels deep
    assert len(code_capture.capture_dependencies(uses_chain, max_depth=5)) == 4
    try:
        code_capture.capture_dependencies(uses_chain, max_depth=4)
        raise AssertionError("depth limit was not enforced")
    except ValueError as e:
        assert "deeper than the limit of 4" in str(e) and "_chain_0" in str(e) and "uses_chain" in str(e), str(e)
        print("rejected:", e)

    try:
        code_capture.capture_dependencies(uses_chain, max_dependencies=3)
        raise AssertionError("dependency count limit was not enforced")
    except ValueError as e:
        assert "more than 3 items" in str(e), str(e)

    # the module level defaults apply to actions created normally, and can be raised
    original = code_capture.MAX_DEPENDENCY_DEPTH
    code_capture.MAX_DEPENDENCY_DEPTH = 3
    try:
        try:
            @MolSpinPy.ActionScript
            def too_deep(step, var):
                return _chain_3() * 0.01
            raise AssertionError("default depth limit was not enforced")
        except ValueError as e:
            assert "deeper than the limit of 3" in str(e), str(e)
    finally:
        code_capture.MAX_DEPENDENCY_DEPTH = original

    # a self-recursive or mutually recursive helper is not a runaway chain
    assert len(code_capture.capture_dependencies(lambda_free_recursive_action)) == 2
    print("dependency limits ok")

def lambda_free_recursive_action(step, var):
    return 1.0 if _is_even(step) else 0.0


_OPTIMUM = np.array([0.3, -0.2, 0.5])

def _fake_molspin_run(executable_path, file_path, log_dir, NPZ=False, npz_dir=None, silent=True):
    # Stands in for the MolSpin binary. It reads the zeeman field written into the msd and
    # writes a .dat with a "fitness" column: one broad peak at _OPTIMUM plus local ripples.
    import re
    text = open(file_path).read()
    name, idx = os.path.basename(file_path)[:-4].rsplit("_", 1)
    field = re.search(r'Interaction zeeman\s*\{[^}]*?field\s*=\s*"([^"]+)"', text).group(1)
    genome = np.array([float(x) for x in field.split()])
    off = genome - _OPTIMUM
    fitness = -np.sum(off ** 2) + 0.05 * np.sum(np.cos(20 * off))
    out = os.path.join(os.path.dirname(file_path), "molspin_results", f"{name}-TE-{idx}.dat")
    with open(out, "w") as f:
        f.write("group fitness\nA %r\n" % float(fitness))
    return None

def test_feedback_action():
    """A small genetic algorithm: each generation is a batch of experiments, and the next
    generation is bred from the best results of the previous one. Sizes vary per generation."""

    @MolSpinPy.FeedbackScript
    def genome(step, var, state, index, generation):
        # Runs once per experiment: returns this member's genome as the zeeman field.
        if not hasattr(state, "population"):
            g = np.random.default_rng(1000 + index).uniform(-1, 1, 3)  # random first generation
        else:
            g = state.population[index]
        return np.asarray(g, dtype=float)

    @genome.on_generation
    def evolve(results, generation, state, stop, elite: int = 2, tournament: int = 3):
        # Runs once between generations. Fitness comes only from the (fake) MolSpin output.
        if not hasattr(state, "rng"):
            state.rng = np.random.default_rng(7)
            state.history = []
        rng = state.rng
        n = len(results)
        fitness = np.array([float(results[i]["TE"]["fitness"][0]) for i in range(n)])
        if hasattr(state, "population"):
            pop = np.array(state.population)
        else:
            pop = np.array([np.random.default_rng(1000 + i).uniform(-1, 1, 3) for i in range(n)])

        order = np.argsort(fitness)[::-1]
        state.best, state.best_fitness = pop[order[0]].tolist(), float(fitness[order[0]])
        state.history.append({"generation": generation, "size": n,
                              "best": state.best_fitness, "mean": float(fitness.mean())})
        if np.linalg.norm(pop[order[0]] - [0.3, -0.2, 0.5]) < 0.03:
            stop()

        def pick():
            # tournament selection: the fittest of a few random members becomes a parent
            contenders = rng.integers(0, n, tournament)
            return pop[contenders[np.argmax(fitness[contenders])]]

        next_size = max(8, 20 - 4 * generation)      # the batch size is free to change: 24, 20, 16, 12, 8...
        sigma = 0.3 * 0.7 ** generation              # mutations shrink as the search converges
        children = [pop[i] for i in order[:elite]]   # elitism: the best survive unchanged
        while len(children) < next_size:
            a, b = pick(), pick()
            mix = rng.uniform(0, 1, 3)               # crossover: blend each gene of two parents
            children.append(mix * a + (1 - mix) * b + rng.normal(0, sigma, 3))  # mutation
        state.population = [c.tolist() for c in children]
        return next_size                             # state.next_batch = next_size also works

    dat = MolSpinPy.msd.MsdHandling.ConvertMSDtoDictionary("NV_centre_N14_old.msd")
    manager = MolSpinPy.runtime.ActionManager()
    manager.add_action(MolSpinPy.objects.Action(dat, genome, key="spinsystems.GS.interactions.zeeman.field"))
    try:
        manager.add_action(MolSpinPy.objects.Action(dat, genome, key="spinsystems.GS.interactions.nuclearzeeman.field"))
        raise AssertionError("a second feedback action was accepted")
    except ValueError:
        pass

    project = MolSpinPy.runtime.Project("feedback_test")
    project.attach_dict(dat)
    project._extract_settings()
    project.attach_ActionManager(manager)
    project._executable_path = os.path.abspath(__file__)  # any existing file; the run is faked

    original = MolSpinPy.runtime.Project._execute_single_file_local
    MolSpinPy.runtime.Project._execute_single_file_local = staticmethod(_fake_molspin_run)
    try:
        project.Deploy(batch=24, max_generations=15)
    finally:
        MolSpinPy.runtime.Project._execute_single_file_local = original

    history = genome.state.history
    print(f"{'gen':>3} {'size':>4} {'best fitness':>13} {'mean fitness':>13}")
    for h in history:
        print(f"{h['generation']:>3} {h['size']:>4} {h['best']:>13.4f} {h['mean']:>13.4f}")
    print("best genome:", np.round(genome.state.best, 3), "optimum:", _OPTIMUM)

    sizes = [g["size"] for g in genome._generation_log]
    assert sizes[:4] == [24, 20, 16, 12] and all(a >= b for a, b in zip(sizes, sizes[1:])), sizes
    assert history[-1]["mean"] > history[0]["mean"], "the population did not improve"
    assert np.linalg.norm(np.array(genome.state.best) - _OPTIMUM) < 0.1, genome.state.best
    try:
        project.LoadHPC("u", "h", "k", "/tmp")
        raise AssertionError("HPC accepted a feedback action")
    except RuntimeError:
        pass
    shutil.rmtree("outputs/feedback_test", ignore_errors=True)
    print("feedback action ok")


#StrainT1times()
#StrainPL()
#test()
#test2()
test_loader_roundtrip()
test_object_bound_actions()
test_dictionary_bound_loader()
test_custom_action_passing()
test_custom_action_dependencies()
test_external_modules()
test_very_complex_action()
test_decorated_helper_rejected()
test_dependency_limits()
test_feedback_action()
