import numpy as np


class ExponentiallyWeightedMovingAverage:
    """Running mean and standard deviation with time constant ``tau``.

    ``update`` returns ``(std, mean, std_of_std, mean_std)``. The first call only
    seeds the mean. The spread of the std uses a slower constant (``100 * tau``).
    Ported unchanged from ``DataManagment``, including that ``var_std`` accumulates
    the squared deviation of the value rather than of the std.
    """

    def __init__(self, tau, mean=None):
        self.tau = tau
        self.mean = mean
        self.var = 0.0
        self.tau2 = tau * 100
        self.mean_std = None
        self.var_std = 0.0

    def update(self, current_val, dt):
        alpha = 1.0 - np.exp(-dt / self.tau)
        alpha2 = 1.0 - np.exp(-dt / self.tau2)
        if self.mean is None:
            self.mean = current_val
            self.var = 0.0
            return 0.0, self.mean, 0.0, self.mean_std

        diff = current_val - self.mean
        self.mean += alpha * diff
        self.var = (1.0 - alpha) * (self.var + alpha * diff**2)
        current_std = np.sqrt(max(0.0, self.var))

        if self.mean_std is None:
            self.mean_std = current_std
        else:
            self.mean_std += alpha * (current_std - self.mean_std)
            self.var_std = (1.0 - alpha2) * (self.var_std + alpha2 * diff**2)
        std_dev_of_std = np.sqrt(max(0.0, self.var_std))
        return current_std, self.mean, std_dev_of_std, self.mean_std
