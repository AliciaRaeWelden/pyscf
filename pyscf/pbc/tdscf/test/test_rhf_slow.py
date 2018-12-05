from pyscf.pbc.gto import Cell
from pyscf.pbc.scf import RHF
from pyscf.pbc.tdscf import TDHF
from pyscf.pbc.tdscf.rhf_slow import PhysERI, PhysERI4, PhysERI8, build_matrix, eig, kernel

import unittest
from numpy import testing
import numpy


def retrieve_m(model, **kwargs):
    vind, hdiag = model.gen_vind(model._scf, **kwargs)
    size = model.init_guess(model._scf, 1).shape[1]
    return vind(numpy.eye(size)).T


def unphase(v1, v2, threshold=1e-5):
    v1, v2 = numpy.asarray(v1).reshape(len(v1), -1), numpy.asarray(v2).reshape((len(v2), -1))
    g1 = abs(v1) > threshold
    g2 = abs(v2) > threshold
    g12 = numpy.logical_and(g1, g2)
    if numpy.any(g12.sum(axis=1) == 0):
        raise ValueError("Cannot find an anchor for the rotation")
    a = tuple(numpy.where(i)[0][0] for i in g12)
    for v in (v1, v2):
        anc = v[numpy.arange(len(v)), a]
        v /= (anc / abs(anc))[:, numpy.newaxis]
    return v1, v2


class DiamondTestGamma(unittest.TestCase):
    """Compare this (rhf_slow) vs reference."""
    @classmethod
    def setUpClass(cls):
        cls.cell = cell = Cell()
        # Lift some degeneracies
        cell.atom = '''
        C 0.000000000000   0.000000000000   0.000000000000
        C 1.67   1.68   1.69
        '''
        cell.basis = {'C': [[0, (0.8, 1.0)],
                            [1, (1.0, 1.0)]]}
        # cell.basis = 'gth-dzvp'
        cell.pseudo = 'gth-pade'
        cell.a = '''
        0.000000000, 3.370137329, 3.370137329
        3.370137329, 0.000000000, 3.370137329
        3.370137329, 3.370137329, 0.000000000'''
        cell.unit = 'B'
        cell.verbose = 5
        cell.build()

        cls.model_rhf = model_rhf = RHF(cell)
        model_rhf.kernel()

        cls.td_model_rhf = td_model_rhf = TDHF(model_rhf)
        td_model_rhf.nroots = 5
        td_model_rhf.kernel()

        cls.ref_m_rhf = retrieve_m(td_model_rhf)

    @classmethod
    def tearDownClass(cls):
        # These are here to remove temporary files
        del cls.td_model_rhf
        del cls.model_rhf
        del cls.cell

    def test_eri(self):
        """Tests all ERI implementations: with and without symmetries."""
        for eri in (PhysERI, PhysERI4, PhysERI8):
            e = eri(self.model_rhf)
            m = build_matrix(e)

            try:
                testing.assert_allclose(self.ref_m_rhf, m, atol=1e-14)
                vals, vecs = eig(m, nroots=self.td_model_rhf.nroots)
                testing.assert_allclose(vals, self.td_model_rhf.e, atol=1e-5)
            except Exception:
                print("When testing {} the following exception occurred:".format(eri))
                raise

    def test_eig_kernel(self):
        """Tests default eig kernel behavior."""
        vals, vecs = kernel(self.model_rhf, driver='eig', nroots=self.td_model_rhf.nroots)
        testing.assert_allclose(vals, self.td_model_rhf.e, atol=1e-5)
        testing.assert_allclose(*unphase(vecs, self.td_model_rhf.xy), atol=1e-2)
