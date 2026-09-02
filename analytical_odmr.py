import numpy as np
import matplotlib.pyplot as plt

# MolSpin Interaction Parameters (MHz and mT)
D = 1336.0           # MHz
Axx, Ayy, Azz = 9.8, 8.6, 10.7  # MHz
gamma_e = 28.024     # MHz / mT
gamma_n = -0.008465  # MHz / mT

Omega_R = 1.2   # Rabi frequency (MW power in MHz)
t_pulse = 0.8   # Pulse length (microseconds)

# Couplings
delta_0 = np.sqrt(2) / 4.0 * (Axx + Ayy)  # ~6.505 MHz
delta_2 = np.sqrt(2) / 4.0 * (Axx - Ayy)  # ~0.424 MHz

# Magnetic Field Range
B_z = np.linspace(44.0, 51.0, 1000)
mw_freq = np.linspace(0, 25.0, 1000)
B_grid, MW_grid = np.meshgrid(B_z, mw_freq)

# Uncoupled Diagonal Elements
E_0u = -2/3 * D - 0.5 * gamma_n * B_z
E_0d = -2/3 * D + 0.5 * gamma_n * B_z
E_du = 1/3 * D - gamma_e * B_z - 0.5 * Azz - 0.5 * gamma_n * B_z
E_dd = 1/3 * D - gamma_e * B_z + 0.5 * Azz + 0.5 * gamma_n * B_z

# Block A: Delta m_F = 0 Eigenvalues
E4 = 0.5 * (E_0d + E_du) + np.sqrt(0.25 * (E_0d - E_du)**2 + delta_0**2)
E5 = 0.5 * (E_0d + E_du) - np.sqrt(0.25 * (E_0d - E_du)**2 + delta_0**2)

# Block B: Delta m_F = 2 Eigenvalues
E3 = 0.5 * (E_0u + E_dd) - np.sqrt(0.25 * (E_0u - E_dd)**2 + delta_2**2)
E6 = 0.5 * (E_0u + E_dd) + np.sqrt(0.25 * (E_0u - E_dd)**2 + delta_2**2)

# ODMR Transitions (relative to zero-state manifold)
nu_blockA_upper = np.abs(E4 - E_0u)
nu_blockA_lower = np.abs(E5 - E_0u)
#nu_blockB_linear = np.abs(E6 - E3)
#nu_blockB_linear = (E_dd - E_0u)  # Corrected to reference the zero-state manifold

# Plotting
plt.figure(figsize=(9, 5.5))
#plt.plot(B_z, nu_blockB_linear, 'r--')#, label=r'Nearly Linear Branch ($gs.td\_d$, $\delta_2 = {delta_2}\ \mathrm{MHz}$)')
plt.plot(B_z, nu_blockA_upper, 'b-')#, label=r'Curved Branch 1 ($gs.t0\_d$, $\delta_0 = {delta_0}\ \mathrm{MHz}$)')
plt.plot(B_z, nu_blockA_lower, 'g-')#, label=r'Curved Branch 2 ($gs.td\_u$, $\delta_0 = {delta_0}\ \mathrm{MHz}$)')

plt.xlabel('Zeeman Field $B_z$ (mT)')
plt.ylabel('ODMR Transition Frequency (MHz)')
plt.title('Corrected Analytical ODMR Transitions ($S=1, I=1/2$)')
plt.ylim(0, 25)
plt.xlim(44, 51)
plt.legend()
plt.grid(True)
plt.show()

#E_tpu = 1/3 * D + gamma_e * B_grid + 0.5 * Azz - 0.5 * gamma_n * B_grid
#E_tpd = 1/3 * D + gamma_e * B_grid - 0.5 * Azz + 0.5 * gamma_n * B_grid
#
#det_0 = E_0d - E_du
#E_0d_hybrid = 0.5 * (E_0d + E_du) + np.sqrt(0.25 * det_0**2 + delta_0**2)
#E_du_hybrid = 0.5 * (E_0d + E_du) - np.sqrt(0.25 * det_0**2 + delta_0**2)
#
#det_2 = E_0u - E_dd
#E_dd_hybrid = 0.5 * (E_0u + E_dd) + np.sqrt(0.25 * det_2**2 + delta_2**2)
#E_0u_hybrid = 0.5 * (E_0u + E_dd) - np.sqrt(0.25 * det_2**2 + delta_2**2)
#
## Mixing coefficients
#sin_theta0 = np.sqrt(0.5 * (1 - det_0 / np.sqrt(det_0**2 + 4 * delta_0**2)))
#cos_theta0 = np.sqrt(0.5 * (1 + det_0 / np.sqrt(det_0**2 + 4 * delta_0**2)))
#
#def rabi_pop(E_target, E_init, Omega_matrix):
#    detuning = MW_grid - np.abs(E_target - E_init)
#    Omega_G = np.sqrt(detuning**2 + Omega_matrix**2)
#    return (Omega_matrix / Omega_G)**2 * np.sin(np.pi * Omega_G * t_pulse)**2
#
#P_t0_d = rabi_pop(E_0d_hybrid, E_0u, Omega_R * sin_theta0)
#P_td_u = rabi_pop(E_du_hybrid, E_0u, Omega_R * cos_theta0)
#P_td_d = rabi_pop(E_dd_hybrid, E_0u, Omega_R * 0.707)
#P_tp_u = rabi_pop(E_tpu, E_0u, Omega_R * 0.707)
#P_tp_d = np.zeros_like(B_grid) # forbidden/off-resonant in this range
#P_t0_u = 1.0 - (P_t0_d + P_td_u + P_td_d + P_tp_u)
#
#fig, axes = plt.subplots(2, 3, figsize=(14, 8))
#
#states = [
#    ("State: gs.t0_u", P_t0_u, axes[0, 0]),
#    ("State: gs.t0_d", P_t0_d, axes[0, 1]),
#    ("State: gs.tp_u", P_tp_u, axes[0, 2]),
#    ("State: gs.tp_d", P_tp_d, axes[1, 0]),
#    ("State: gs.td_u", P_td_u, axes[1, 1]),
#    ("State: gs.td_d", P_td_d, axes[1, 2]),
#]
#
#for title, pop, ax in states:
#    im = ax.pcolormesh(B_grid, MW_grid, pop, shading='auto', cmap='viridis')
#    ax.set_title(title)
#    ax.set_xlabel('gs.zeeman.field.length (mT)')
#    ax.set_ylabel('gs.pulsed_odmr.frequency (MHz)')
#    fig.colorbar(im, ax=ax, label='State population')
#
#plt.tight_layout()
#plt.show()
