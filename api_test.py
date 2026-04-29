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

main()