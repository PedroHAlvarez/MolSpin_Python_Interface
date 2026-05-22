import MolSpinPy

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

    dat = MolSpinPy.msd.MsdHandling.ConvertMSDtoDictionary("NV_centre_N14_base.msd")
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


    Action = MolSpinPy.objects.Action(e1.spin,test_action_1,duration=2,interval=1, loop = True)
    Action2 = MolSpinPy.objects.Action(e1.g_tensor, test_action_2, duration = 2, interval=2, a = 5, b=3, parent = Action)
    Action3 = MolSpinPy.objects.Action(e1.spin, test_action_3, duration = 5, loop = True, a = 3, b =4, parent = Action2)
    Action4 = MolSpinPy.objects.Action(e1.spin, MolSpinPy.objects.Actions.LineSpaceScalar(0,0.1,num=100), duration = 100, loop = True)
    Action5 = MolSpinPy.objects.Action(dat['spinsystems']['GS']['transitions']['T0UP'], MolSpinPy.objects.Actions.LineSpaceScalar(0,0.1,num=100), duration = 100, loop = True, key = 'rate')
    #Action6 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LineSpaceScalar(0,0.1,num=100), duration = 100, loop = True, key = 'spinsystems.GS.transitions.T0UP.rate')
    Action7 = MolSpinPy.objects.Action(dat, MolSpinPy.objects.Actions.LineSpaceVector(0,0.1,num=100, direction = MolSpinPy.maths.vector.Vector("0.0 1.0 0.5")), duration = 100, loop = True, key = 'spinsystems.GS.interactions.zeeman.field')
    manager = MolSpinPy.runtime.ActionManager()
    #manager.add_action(Action6)
    manager.add_action(Action7)

    test = MolSpinPy.runtime.Project("test")
    test.attach_dict(dat)
    test._extract_settings()
    test.attach_ActionManager(manager)
    #test._dryRun()
    #test.Deploy()
    id = test.SubmitToHPC(hpc_username="u28375",hpc_host="glogin-p2.hpc.gwdg.de",
    hpc_key_path="~/.ssh/id_ed25519", remote_binary_path="/projects/extern/nhr/nhr_ni/nip00058/dir.project/MolSpin/MolSpin",
    remote_working_dir="/user/benjamin.tigg/u28375", calcs_per_node=20, partition="medium96s:test")
    id= 13921951
    test.WatchHPC(id)
    test.DownloadFromHPC(id, remote_working_dir="/user/benjamin.tigg/u28375", local_npz_output_path="results/")
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
    print("end of testing")

    

    

main()