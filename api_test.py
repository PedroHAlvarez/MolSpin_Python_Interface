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

    @MolSpinPy.objects.ActionScript
    def test_action_1(step,var,a):
        return var + (step * a)
    @MolSpinPy.objects.ActionScript
    def test_action_2(step,a : float,b : int):
        return a + step * b
    @MolSpinPy.objects.ActionScript
    def test_action_3(a,b):
        return a + b
    @MolSpinPy.objects.ActionScript
    def test_action_5(var,a,b):
        var.value = a+b
    #@MolSpinPy.objects.ActionScript
    #def test_action_4(a,b):
    #   print(a+b)

    Action = MolSpinPy.objects.Action(e1.spin,test_action_1,duration=100,interval=1)
    Action2 = MolSpinPy.objects.Action(e1.spin, test_action_2, duration = 10, interval=1, a = 5, b='hello')
    print("end of testing")

    

main()