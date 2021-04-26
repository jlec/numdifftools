"""
Created on 28. aug. 2015

@author: pab
"""
from __future__ import division, print_function
import warnings
import numpy as np
from scipy import linalg
from scipy.ndimage.filters import convolve1d

EPS = np.finfo(float).eps
_EPS = EPS
_TINY = np.finfo(float).tiny
_HUGE = np.finfo(float).max


def _assert(cond, msg):
    if not cond:
        raise ValueError(msg)


def convolve(sequence, rule, **kwds):
    """Wrapper around scipy.ndimage.convolve1d that allows complex input."""
    dtype = np.result_type(float, np.ravel(sequence)[0])
    seq = np.asarray(sequence, dtype=dtype)
    if np.iscomplexobj(seq):
        return (convolve1d(seq.real, rule, **kwds) + 1j * convolve1d(seq.imag, rule, **kwds))
    return convolve1d(seq, rule, **kwds)


class Dea(object):
    """
    Extrapolate a slowly convergent sequence using repeated Shanks transformations.

    Notes
    -----
    DEA attempts to extrapolate nonlinearly by Shanks transformations to a better
    estimate of the sequence's limiting value, thus improving the rate of convergence.
    The epsilon algorithm of P. Wynn, see [1]_, is used to perform the
    non-linear Shanks transformations. The routine is a translation of the
    DQELG function found in the QUADPACK fortran library, see [2]_.

    List of major variables:

    LIMEXP:  scalar integer
        The maximum number of elements the epsilon table data can contain.
        The epsilon table is stored in the first (LIMEXP+2) entries of EPSTAB.
    EPSTAB: real vector or size (LIMEXP+2+3)
        The first LIMEXP+2 elements contains the two lower diagonals of the triangular
        epsilon table. The elements are numbered starting at the right-hand corner of the
       triangle.
    E0,E1,E2,E3:  real scalars
        The 4 elements on which the computation of a new element in the epsilon table is based.
    NRES:  scalar integer
        Number of extrapolation results actually generated by the epsilon algorithm in prior
        calls to the routine.
    NEWELM: scalar integer
        Number of elements to be computed in the new diagonal of the epsilon table.
        The condensed epsilon table is computed. Only those elements needed for the
        computation of the next diagonal are preserved.
    RES: real scalar
        New element in the new diagonal of the epsilon table.
    ERROR: real scalar
        An estimate of the absolute error of RES. The routine decides whether RESULT=RES or
        RESULT=SVALUE by comparing ERROR with abserr from the previous call.
    RES3LA: real vector of size 3
        Contains at most the last 3 results.

    Reference
    ---------
    ..  [1] Wynn, P. (1956)
            "On a Device for Computing the em(Sn) Transformation",
            Mathematical Tables and Other Aids to Computation, 10, 91-96.
    ..  [2] R. Piessens, E. De Doncker-Kapenga and C. W. Uberhuber (1983),
            "QUADPACK: a subroutine package for automatic integration",
            Springer, ISBN: 3-540-12553-1, 1983.

    """
    def __init__(self, limexp=50):
        self.limexp = limexp
        self._n = 0
        self._nres = 0

    @property
    def limexp(self):
        return self._limexp

    @limexp.setter
    def limexp(self, limexp):
        n = 2 * (limexp // 2) + 1
        _assert(n >= 3, 'LIMEXP IS LESS THAN 3')
        self.epstab = np.zeros(n + 5)
        self._limexp = n

    def _dea(self,  epstab, n):

        res3la = epstab[-3:]
        nres = self._nres

        abserr = _HUGE
        result = epstab[n]
        # if(n.lt.3) go to 100
        limexp = self.limexp
        epstab[n+2] = epstab[n]
        newelm = n // 2
        epstab[n] = _HUGE
        old_n = n
        k1 = n
        all_converged = False
        for i in range(newelm):  # do 40 i = 1,newelm
            res = epstab[k1+2]
            e0 = epstab[k1-2]
            e1 = epstab[k1-1]
            e2 = res
            delta2 = e2 - e1
            delta3 = e1 - e0
            err2 = abs(delta2)
            err3 = abs(delta3)
            e1abs = abs(e1)
            tol2 = max(abs(e2), e1abs) * _EPS
            tol3 = max(e1abs, abs(e0)) * _EPS
            all_converged = not (err2 > tol2 or err3 > tol3)
            if all_converged:
                #      if e0, e1 and e2 are equal to within machine
                #      accuracy, convergence is assumed.
                #      result = e2
                #      abserr = abs(e1-e0) + abs(e2-e1)

                result = res
                abserr = err2 + err3

                # ***jump out of do-loop
                # go to 100
                break
            e3 = epstab[k1]
            epstab[k1] = e1
            delta1 = e1-e3
            err1 = abs(delta1)
            tol1 = max(e1abs, abs(e3)) * _EPS

            #      if two elements are very close to each other, omit
            #      a part of the table by adjusting the value of n

            any_converged = err1 <= tol1 or err2 <= tol2 or err3 <= tol3
            if not any_converged:  # go to 20
                ss = 1.0 / delta1 + 1.0 / delta2 - 1.0 / delta3
                epsinf = abs(ss*e1)

            #      test to detect irregular behaviour in the table, and
            #      eventually omit a part of the table adjusting the value
            #      of n.
                any_converged = epsinf <= 1e-4

            if any_converged:
                n = 2*i
                # ***jump out of do-loop
                # go to 50
                break

            #      compute a new element and eventually adjust
            #      the value of result.
            res = e1 + 1.0/ss
            epstab[k1] = res
            k1 = k1 - 2
            error = err2 + abs(res-e2) + err3
            if error > abserr:
                # go to 40
                continue
            abserr = error
            result = res
            # 40 continue

        # 50
        if not all_converged:
            #      shift the table.
            if (n == limexp-1):
                n = limexp - 2  # 2*(limexp//2) - 1
            self._shift_table(epstab, n, newelm, old_n)
            if nres > 1:
                abserr = np.abs(result - res3la[:nres]).sum()

            self._update_res3la(res3la, result, nres)
        # 100
        abserr = max(abserr, 5.0*_EPS*abs(result))
        self._nres += 1
        return result, abserr, n

    @staticmethod
    def _shift_table(epstab, n, newelm, old_n):
        i_0 = old_n % 2  # 1 if ((old_n // 2) * 2 == old_n - 1) else 0
        i_n = 2 * newelm + 2
        epstab[i_0:i_n:2] = epstab[i_0 + 2:i_n + 2:2]

        if old_n != n:
            i_n = old_n - n
            epstab[:n + 1] = epstab[i_n:i_n + n + 1]
        return epstab

    @staticmethod
    def _update_res3la(res3la, result, nres):
        if nres > 2:
            res3la[:2] = res3la[1:]
            res3la[2] = result
        else:
            res3la[nres] = result

    def __call__(self, s_value):

        epstab = self.epstab

        result = s_value
        n = self._n

        epstab[n] = s_value
        if n == 0:
            abserr = abs(result)
        elif n == 1:
            abserr = 6.0 * abs(result - epstab[0])
        else:
            result, abserr, n = self._dea(epstab, n)
        n += 1
        self._n = n

        return result, abserr


class EpsAlg(object):

    """
    Extrapolate a slowly convergent sequence using Shanks transformation.

    Notes
    -----
    The iterated Shanks transformation is computed using the Wynn
    epsilon algorithm (see equation 4.3-10a to 4.3-10c given on page 25 in [1]_).


    References
    ----------
    ..  [1] E. J. Weniger (1989)
            "Nonlinear sequence transformations for the acceleration of
            convergence and the summation of divergent series"
            Computer Physics Reports Vol. 10, 189 - 371
            http://arxiv.org/abs/math/0306302v1
    """

    def __init__(self):
        self.epstab = []

    def __call__(self, s_n):

        epstab = self.epstab
        n = len(epstab)
        epstab.append(s_n)
        if n == 0:
            estlim = s_n
        else:
            aux2 = 0.0
            for i in range(n, 0, -1):
                aux1 = aux2
                aux2 = epstab[i - 1]
                delta = epstab[i] - aux2
                if np.abs(delta) <= 1.0e-60:
                    epstab[i - 1] = 1.0e+60
                else:
                    epstab[i - 1] = aux1 + 1.0 / delta
            estlim = epstab[n % 2]

        return estlim


def richardson_demo():
    """
    >>> from numdifftools.extrapolation import richardson_demo
    >>> richardson_demo()
    NO. PANELS      TRAP. APPROX          APPROX W/R            abserr
        1           0.78539816            0.78539816            0.21460184
        2           0.94805945            1.11072073            0.11072073
        4           0.98711580            0.99798929            0.00201071
        8           0.99678517            0.99988201            0.00011799
       16           0.99919668            0.99999274            0.00000726
       32           0.99979919            0.99999955            0.00000045
       64           0.99994980            0.99999997            0.00000003
      128           0.99998745            1.00000000            0.00000000
      256           0.99999686            1.00000000            0.00000000
      512           0.99999922            1.00000000            0.00000000
    """

    def linfun(i):
        return np.linspace(0, np.pi / 2., 2 ** i + 1)

    n = 10
    e_i = []
    h = []

    print('NO. PANELS      TRAP. APPROX          APPROX W/R            abserr')
    txt = '{0:5d} {1:20.8f}  {2:20.8f}  {3:20.8f}'
    for k in np.arange(n):
        x = linfun(k)
        val = np.trapz(np.sin(x), x)
        h.append(x[1])
        e_i.append(val)
        vale, _err0, _step = Richardson(step=1, order=1)(np.array(e_i), np.array(h))

        err = np.abs(1.0 - vale)
        print(txt.format(len(x) - 1, val, vale[-1], err[-1]))


def epsalg_demo():
    """
    >>> from numdifftools.extrapolation import epsalg_demo
    >>> epsalg_demo()
    NO. PANELS      TRAP. APPROX          APPROX W/EA           abserr
        1           0.78539816            0.78539816            0.21460184
        2           0.94805945            0.94805945            0.05194055
        4           0.98711580            0.99945672            0.00054328
        8           0.99678517            0.99996674            0.00003326
       16           0.99919668            0.99999988            0.00000012
       32           0.99979919            1.00000000            0.00000000
       64           0.99994980            1.00000000            0.00000000
      128           0.99998745            1.00000000            0.00000000
      256           0.99999686            1.00000000            0.00000000
      512           0.99999922            1.00000000            0.00000000
    """

    def linfun(i):
        return np.linspace(0, np.pi / 2., 2 ** i + 1)

    dea = EpsAlg()
    print('NO. PANELS      TRAP. APPROX          APPROX W/EA           abserr')
    txt = '{0:5d} {1:20.8f}  {2:20.8f}  {3:20.8f}'
    for k in np.arange(10):
        x = linfun(k)
        val = np.trapz(np.sin(x), x)
        vale = dea(val)
        err = np.abs(1.0 - vale)
        print(txt.format(len(x) - 1, val, vale, err))


def dea_demo():
    """
    >>> from numdifftools.extrapolation import dea_demo
    >>> dea_demo()
    NO. PANELS      TRAP. APPROX          APPROX W/EA           abserr
        1           0.78539816            0.78539816            0.78539816
        2           0.94805945            0.94805945            0.97596771
        4           0.98711580            0.99945672            0.21405856
        8           0.99678517            0.99996674            0.05190729
       16           0.99919668            0.99999988            0.00057629
       32           0.99979919            1.00000000            0.00057665
       64           0.99994980            1.00000000            0.00003338
      128           0.99998745            1.00000000            0.00000012
      256           0.99999686            1.00000000            0.00000000
      512           0.99999922            1.00000000            0.00000000
     1024           0.99999980            1.00000000            0.00000000
     2048           0.99999995            1.00000000            0.00000000
    """

    def linfun(i):
        return np.linspace(0, np.pi / 2., 2 ** i + 1)

    dea = Dea(limexp=6)
    print('NO. PANELS      TRAP. APPROX          APPROX W/EA           abserr')
    txt = '{0:5d} {1:20.8f}  {2:20.8f}  {3:20.8f}'
    vals = []
    num_panels = []
    for k in np.arange(12):
        x = linfun(k)
        val = np.trapz(np.sin(x), x)
        vals.append(val)
        num_panels.append(len(x) - 1)
    for k, val in zip(num_panels, vals):
        vale, err = dea(val)
        print(txt.format(k, val, vale, err))


def max_abs(a, b):
    """Returns element-wise maximum of absulute value of array elements"""
    return np.maximum(np.abs(a), np.abs(b))


def dea3(v0, v1, v2, symmetric=False):
    """
    Extrapolate a slowly convergent sequence using Shanks transformations.

    Parameters
    ----------
    v0, v1, v2 : array-like
        3 values of a convergent sequence to extrapolate

    Returns
    -------
    result : array-like
        extrapolated value
    abserr : array-like
        absolute error estimate

    Notes
    -----
    DEA3 attempts to extrapolate nonlinearly by Shanks transformations to a
    better estimate of the sequence's limiting value based on only three values.
    The epsilon algorithm of P. Wynn, see [1]_, is used to perform the
    non-linear Shanks transformations. The routine is a vectorized translation
    of the DQELG function found in the QUADPACK fortran library for LIMEXP=3, see [2]_.

    Examples
    --------
    # integrate sin(x) from 0 to pi/2

    >>> import numpy as np
    >>> import numdifftools as nd
    >>> Ei= np.zeros(3)
    >>> linfun = lambda i : np.linspace(0, np.pi/2., 2**(i+5)+1)
    >>> for k in np.arange(3):
    ...    x = linfun(k)
    ...    Ei[k] = np.trapz(np.sin(x),x)
    >>> [En, err] = nd.dea3(Ei[0], Ei[1], Ei[2])
    >>> truErr = np.abs(En-1.)
    >>> np.all(truErr < err)
    True
    >>> np.allclose(En, 1)
    True
    >>> np.all(np.abs(Ei-1)<1e-3)
    True

    See also
    --------
    Dea

    References
    ----------
    ..  [1] Wynn, P. (1956)
            "On a Device for Computing the em(Sn) Transformation",
            Mathematical Tables and Other Aids to Computation, 10, 91-96.
    ..  [2] R. Piessens, E. De Doncker-Kapenga and C. W. Uberhuber (1983),
            "QUADPACK: a subroutine package for automatic integration",
            Springer, ISBN: 3-540-12553-1, 1983.
    """
    e_0, e_1, e_2 = np.atleast_1d(v0, v1, v2)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # ignore division by zero and overflow
        delta2, delta1 = e_2 - e_1, e_1 - e_0
        err2, err1 = np.abs(delta2), np.abs(delta1)
        tol2, tol1 = max_abs(e_2, e_1) * _EPS, max_abs(e_1, e_0) * _EPS
        delta1[err1 < _TINY] = _TINY
        delta2[err2 < _TINY] = _TINY  # avoid division by zero and overflow
        sss = 1.0 / delta2 - 1.0 / delta1 + _TINY
        smalle2 = abs(sss * e_1) <= 1.0e-4
        converged = (err1 <= tol1) | (err2 <= tol2) | smalle2
        result = np.where(converged, e_2 * 1.0, e_1 + 1.0 / sss)
    abserr = err1 + err2 + np.where(converged, tol2 * 10, np.abs(result - e_2))
    if symmetric and len(result) > 1:
        return result[:-1], abserr[1:]
    return result, abserr


class Richardson(object):

    """
    Extrapolates as sequence with Richardsons method

    Notes
    -----
    Suppose you have series expansion that goes like this

    L = f(h) + a0 * h^p_0 + a1 * h^p_1+ a2 * h^p_2 + ...

    where p_i = order + step * i  and f(h) -> L as h -> 0, but f(0) != L.

    If we evaluate the right hand side for different stepsizes h
    we can fit a polynomial to that sequence of approximations.
    This is exactly what this class does.

    Examples
    --------
    >>> import numpy as np
    >>> import numdifftools as nd
    >>> n = 3
    >>> Ei = np.zeros((n,1))
    >>> h = np.zeros((n,1))
    >>> linfun = lambda i : np.linspace(0, np.pi/2., 2**(i+5)+1)
    >>> for k in np.arange(n):
    ...    x = linfun(k)
    ...    h[k] = x[1]
    ...    Ei[k] = np.trapz(np.sin(x),x)
    >>> En, err, step = nd.Richardson(step=1, order=1)(Ei, h)
    >>> truErr = np.abs(En-1.)
    >>> np.all(truErr < err)
    True
    >>> np.all(np.abs(Ei-1)<1e-3)
    True
    >>> np.allclose(En, 1)
    True
    """

    def __init__(self, step_ratio=2.0, step=1, order=1, num_terms=2):
        self.num_terms = num_terms
        self.order = order
        self.step = step
        self.step_ratio = step_ratio

    @staticmethod
    def _r_matrix(step_ratio, step, num_terms, order):

        i, j = np.ogrid[0:num_terms + 1, 0:num_terms]
        dtype = np.result_type(step_ratio, step, float)
        r_mat = np.ones((num_terms + 1, num_terms + 1), dtype=dtype)
        r_mat[:, 1:] = (1.0 / step_ratio) ** (i * (step * j + order))
        return r_mat

    def rule(self, sequence_length=None):
        if sequence_length is None:
            sequence_length = self.num_terms + 1
        num_terms = min(self.num_terms, sequence_length - 1)
        if num_terms > 0:
            r_mat = self._r_matrix(self.step_ratio, self.step, num_terms, self.order)
            return linalg.pinv(r_mat)[0]
        return np.ones((1,))

    @staticmethod
    def _estimate_error(new_sequence, old_sequence, steps, rule):
        m = new_sequence.shape[0]
        m_old = old_sequence.shape[0]
        cov1 = np.sum(rule ** 2)  # 1 spare dof
        fact = np.maximum(12.7062047361747 * np.sqrt(cov1), EPS * 10.)
        if m_old < 2:
            return (np.abs(new_sequence) * EPS + steps) * fact
        if m < 2:
            delta = np.diff(old_sequence, axis=0)
            tol = max_abs(old_sequence[:-1], old_sequence[1:]) * fact
            err = np.abs(delta)
            converged = err <= tol
            abserr = (err[-m:] +
                      np.where(converged[-m:], tol[-m:] * 10,
                               abs(new_sequence - old_sequence[-m:]) * fact))
            return abserr
#         if m_old>2:
#             res, abserr = dea3(old_sequence[:-2], old_sequence[1:-1],
#                               old_sequence[2:] )
#             return abserr[-m:] * fact
        err = np.abs(np.diff(new_sequence, axis=0)) * fact
        tol = max_abs(new_sequence[1:], new_sequence[:-1]) * EPS * fact
        converged = err <= tol
        abserr = err + np.where(converged, tol * 10,
                                abs(new_sequence[:-1] -
                                    old_sequence[-m + 1:]) * fact)
        return abserr

    def extrapolate(self, sequence, steps):
        return self.__call__(sequence, steps)

    def __call__(self, sequence, steps):
        ne = sequence.shape[0]
        rule = self.rule(ne)
        nr = rule.size - 1
        m = ne - nr
        mm = min(ne, m + 1)
        new_sequence = convolve(sequence, rule[::-1], axis=0, origin=nr // 2)
        abserr = self._estimate_error(new_sequence[:mm], sequence, steps, rule)
        return new_sequence[:m], abserr[:m], steps[:m]


if __name__ == '__main__':
    from numdifftools.testing import test_docstrings
    test_docstrings(__file__)
