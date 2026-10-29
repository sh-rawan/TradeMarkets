"""Student-t forecast distributions as published in features/forecasts (mean, std, nu):
the central ranges drawn on charts and the CRPS used to score them."""
import numpy as np
from scipy.special import beta as beta_fn
from scipy.stats import t as student_t


def scale(std, nu):
    """Scale parameter of a Student-t with the given std dev."""
    return std * np.sqrt((nu - 2) / nu)


def halfwidth(std, nu, p):
    """Half-width of the central p range (e.g. 0.68, 0.95) of a Student-t with this std dev."""
    return student_t.ppf(0.5 + p / 2, nu) * scale(std, nu)


def crps(mean, std, nu, actual):
    """CRPS of a Student-t forecast (closed form), elementwise. Lower is better."""
    s = scale(std, nu)
    z = (actual - mean) / s
    tail = 2 * np.sqrt(nu) * beta_fn(0.5, nu - 0.5) / ((nu - 1) * beta_fn(0.5, nu / 2) ** 2)
    return s * (z * (2 * student_t.cdf(z, nu) - 1) + 2 * student_t.pdf(z, nu) * (nu + z ** 2) / (nu - 1) - tail)
