import MolSpinPy

def main():
    MolSpinPy.utility.regex_functions.test_tensor_input()
    MolSpinPy.msd.FileTemplate.test()

    ss = MolSpinPy.objects.spin_system.SpinSystem("test")
    e1 = MolSpinPy.objects.spin_object.Electron("e1")
    e1.set_spin_value(1.0)
    #e1.set_spin_value(1.2)
    ss.add_electron(e1)
    a = ss.ConvertToDictionary()
    print(a)

    dat = MolSpinPy.msd.MsdHandling.ConvertMSDtoDictionary("NV_centre_N14_base.msd")
    test2 = MolSpinPy.msd.FileTemplate.get_template("BasicTemplate.msd")
    print(test2.render_to_file(dat, "output2.msd"))
    

main()