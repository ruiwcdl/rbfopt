"""Routines for trust-region based local search.

This module contains all functions that are necessary to implement a
trust-region based local search to refine the solution quality. The
local search exploits a linear model of the objective function.

Licensed under Revised BSD license, see LICENSE.
(C) Copyright International Business Machines Corporation 2017.

"""

from __future__ import print_function
from __future__ import division
from __future__ import absolute_import

import numpy as np
import scipy.spatial as ss
import rbfopt_config as config
import rbfopt_utils as ru
from rbfopt_settings import RbfoptSettings


def init_trust_region(settings, n, k, node_pos, center):
    """Initialize the trust region.

    Determine which nodes should be used to create a linear model of
    the objective function, and determine the initial radius of the
    trust region.

    Parameters
    ----------
    settings : :class:`rbfopt_settings.RbfoptSettings`.
        Global and algorithmic settings.

    n : int
        Dimension of the problem, i.e. the size of the space.

    k : int
        Number of interpolation nodes.

    node_pos : 2D numpy.ndarray[float]
        List of coordinates of the nodes.

    center : 1D numpy.ndarray[float]
        Node that acts as a center for the quadratic model.

    Returns
    -------
    (1D numpy.ndarray[int], float)
        Indices in node_pos of points to build the model, and initial
        radius of the trust region.

    Raises
    ------
    numpy.linalg.LinAlgError
        If the matrix cannot be computed for numerical reasons.

    """
    assert(isinstance(node_pos, np.ndarray))
    assert(len(node_pos)==k)
    assert(k >= 2)
    assert(isinstance(center, np.ndarray))
    assert(len(np.atleast_1d(center))==n)
    assert(isinstance(settings, RbfoptSettings))
    # Find points closest to the given point
    dist = ss.distance.cdist(np.atleast_2d(center), node_pos)
    dist_order = np.argsort(dist[0])
    # The nodes to keep are those closest to the center
    num_to_keep = min(n + 1, k)
    # Build array of nodes to keep
    model_set = dist_order[np.arange(num_to_keep)]
    tr_radius = max(np.percentile(dist[0, model_set[1:]], 0.5),
                    settings.tr_min_radius * 
                    2**settings.tr_init_radius_multiplier)
    return (model_set, tr_radius)
# -- end function

def get_linear_model(settings, n, k, node_pos, node_val, model_set):
    """Compute a linear model of the function.

    Determine a linear model h^T x + b of the objective function in an
    area that is centered on the given node. The model is computed by
    solving a (not necessarily square) linear system, inducing
    sparsity.

    Parameters
    ----------
    settings : :class:`rbfopt_settings.RbfoptSettings`.
        Global and algorithmic settings.

    n : int
        Dimension of the problem, i.e. the size of the space.

    k : int
        Number of interpolation nodes.

    node_pos : 2D numpy.ndarray[float]
        List of coordinates of the nodes.

    node_val : 1D numpy.ndarray[float]
        List of values of the function at the nodes.

    model_set : 1D numpy.ndarray[int]
        Indices of points in node_pos to be used to compute model.

    Returns
    -------
    1D numpy.ndarray[float], float
        Coefficients of the quadratic model h, b.

    Raises
    ------
    numpy.linalg.LinAlgError
        If the matrix cannot be computed for numerical reasons.

    """
    assert(isinstance(node_pos, np.ndarray))
    assert(len(node_pos)==k)
    assert(isinstance(node_val, np.ndarray))
    assert(len(node_val)==k)
    assert(isinstance(model_set, np.ndarray))
    assert(isinstance(settings, RbfoptSettings))
    model_size = len(model_set)
    # Determine the coefficients of the underdetermined linear system.
    lstsq_mat = np.hstack((node_pos[model_set], np.ones((model_size, 1))))
    # Solve least squares system and recover quadratic form
    try:
        x, res, rank, s = np.linalg.lstsq(lstsq_mat, node_val[model_set])
    except np.linalg.LinAlgError as e:
        print('Exception raised trying to compute quadratic model',
              file=sys.stderr)
        print(e, file=sys.stderr)
        raise e
    h = x[:n]
    b = x[-1]
    return h, b
# -- end function

def get_candidate_point(settings, n, k, var_lower, var_upper, h,
                        start_point, tr_radius):
    """Compute the next candidate point of the trust region method.

    Starting from a given point, compute a descent direction and move
    in that direction to find the point with lowest value of the
    linear model, within the radius of the trust region.

    Parameters
    ----------
    settings : :class:`rbfopt_settings.RbfoptSettings`.
        Global and algorithmic settings.

    n : int
        Dimension of the problem, i.e. the size of the space.

    k : int
        Number of interpolation nodes.

    var_lower : 1D numpy.ndarray[float]
        Vector of variable lower bounds.
    
    var_upper : 1D numpy.ndarray[float]
        Vector of variable upper bounds.

    h : 1D numpy.ndarray[float]
        Linear coefficients of the quadratic model.

    start_point : 1D numpy.ndarray[float]
        Starting point for the descent.

    tr_radius : float
        Radius of the trust region.

    Returns
    -------
    (1D numpy.ndarray[float], float, float)
        Next candidate point for the search, the corresponding model
        value difference, and the norm of the gradient at the current
        point.

    """
    assert(isinstance(var_lower, np.ndarray))
    assert(isinstance(var_upper, np.ndarray))
    assert(isinstance(start_point, np.ndarray))
    assert(isinstance(h, np.ndarray))
    assert(len(var_lower)==n)
    assert(len(var_upper)==n)
    assert(len(start_point)==n)
    assert(len(h)==n)
    assert(tr_radius>=0)
    assert(isinstance(settings, RbfoptSettings))
    grad_norm = np.sqrt(np.dot(h, h))
    # If the gradient is essentially zero, there is nothing to improve
    if (grad_norm <= settings.eps_zero):
        return (start_point, 0.0, grad_norm)
    # Determine maximum (smallest) t for line search before we exceed bounds
    max_t = tr_radius/np.sqrt(np.dot(h, h))
    loc = (h > 0) * (start_point >= var_lower + settings.min_dist)
    if (np.any(loc)):
        to_var_lower = (start_point[loc] - var_lower[loc]) / h[loc]
        max_t = min(max_t, np.min(to_var_lower))
    loc = (h < 0) * (start_point <= var_upper - settings.min_dist)
    if (np.any(loc)):
        to_var_upper = (start_point[loc] - var_upper[loc]) / h[loc]
        max_t = min(max_t, np.min(to_var_upper))
    candidate = np.clip(start_point - max_t * h, var_lower, var_upper)
    return (candidate, np.dot(h, start_point - candidate), grad_norm)
# -- end function

def get_integer_candidate(settings, n, k, h, start_point, tr_radius, 
                          candidate, integer_vars):
    """Get integer candidate point from a fractional point.

    Look for integer points around the given fractional point, trying
    to find one with a good value of the quadratic model.

    Parameters
    ----------
    settings : :class:`rbfopt_settings.RbfSettings`.
        Global and algorithmic settings.

    n : int
        Dimension of the problem, i.e. the size of the space.

    k : int
        Number of interpolation nodes.

    h : 1D numpy.ndarray[float]
        Linear coefficients of the model.

    start_point : 1D numpy.ndarray[float]
        Starting point for the descent.

    tr_radius : float
        Radius of the trust region.

    candidate : 1D numpy.ndarray[float]
        Fractional point to being the search.

    integer_vars : 1D numpy.ndarray[int]
        Indices of the integer variables.

    Returns
    -------
    (1D numpy.ndarray[float], float)
        Next candidate point for the search, and the corresponding
        change in model value compared to the given point.
    """ 
    assert(isinstance(candidate, np.ndarray))
    assert(len(candidate) == n)
    assert(isinstance(h, np.ndarray))
    assert(len(h) == n)
    assert(isinstance(integer_vars, np.ndarray))
    assert(isinstance(settings, RbfoptSettings))
    # Compute the rounding down and up
    floor = np.floor(candidate[integer_vars])
    ceil = np.ceil(candidate[integer_vars])
    curr_point = np.copy(candidate)
    curr_point[integer_vars] = np.where(h[integer_vars] >= 0, ceil, floor)
    best_value = np.dot(h, curr_point)
    best_point = np.copy(curr_point)
    for i in range(n * settings.tr_num_integer_candidates):
        # We round each integer variable up or down depending on its
        # fractional value and a uniform random number
        curr_point[integer_vars] = np.where(
            np.random.uniform(size=len(integer_vars)) < 
            candidate[integer_vars] - floor, ceil, floor)
        curr_value = np.dot(h, curr_point) 
        if (ru.distance(curr_point, start_point) <= tr_radius and 
            curr_value < best_value):
            best_value = curr_value
            best_point = np.copy(curr_point)
    return (best_point, np.dot(h, candidate) - best_value)
# -- end function

def update_trust_region_radius(settings, tr_radius, model_obj_diff,
                               real_obj_diff):
    """Update the radius of the trust region.

    Compute the updated trust region radius based on the true
    objective function difference between the old point and the new
    point, and that of the quadratic model. Also, determine if the new
    iterate should be accepted.

    Parameters
    ----------
    settings : :class:`rbfopt_settings.RbfoptSettings`.
        Global and algorithmic settings.

    tr_radius : float
        Current radius of the trust region.

    model_obj_diff : float
        Objective function value of the new point according to the
        linear model.

    real_obj_diff : float
        Real objective function value of the new point.

    Returns
    -------
    (float, bool)
        Updated radius of the trust region, and whether the point
        should be accepted.

    """
    assert(tr_radius >= 0)
    assert(isinstance(settings, RbfoptSettings))
    init_radius = tr_radius
    decrease = (real_obj_diff / model_obj_diff 
                if abs(model_obj_diff) > settings.eps_zero else 0)
    if (decrease <= settings.tr_acceptable_decrease_shrink):
        tr_radius *= 0.5
    elif (decrease >= settings.tr_acceptable_decrease_enlarge):
        tr_radius *= 2
    return (tr_radius, decrease >= settings.tr_acceptable_decrease_move)
# -- end function
