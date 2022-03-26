"""Kullback-Leibler divergence module."""

import abc

import torch
import numpy as np


class Family(abc.ABC):
    """Kullback-Leibler divergence functions switch class."""

    subclasses = {}

    def __init__(self):
        super().__init__()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.subclasses[cls._FAMILY_NAME] = cls

    @abc.abstractmethod
    def kl_div(self):  # pragma: no cover
        pass

    @classmethod
    def create(cls, model):
        if model.family.name not in cls.subclasses:
            raise NotImplementedError("Unsupported family.")

        return cls.subclasses[model.family.name]()


class Gaussian(Family):
    _FAMILY_NAME = "gaussian"

    def __init__(self):
        super().__init__()
        self.has_disp_params = True

    def kl_div(self, y_ast, y_perp):
        """Kullback-Leibler divergence between two Gaussians.

        Args:
            y_ast (torch.tensor): Tensor of reference model posterior draws
            y_perp (torch.tensor): Tensor of restricted model posterior draws

        Returns:
            torch.tensor: Tensor of shape () containing sample KL divergence
        """

        # compute Wasserstein distance as a KL divergence surrogate
        div = torch.mean((y_ast - y_perp) ** 2)
        assert div.shape == (), f"Expected data dimensions {()}, received {div.shape}."
        return div

    def _project_disp_params(self, ref_model, res_model):
        """Analytic projection of the model dispersion parameters.

        Args:
            ref_model (kulprit.ModelData): The reference model
            res_model (kulprit.ModelData): Restricted model on which to project
                the reference dispersion parameters

        Returns:
            torch.tensor: The restricted projections of the dispersion parameters
        """

        def _proj(theta_ast, theta_perp, sigma_ast):
            """Projection method to aid with vectorisation."""

            f = X_ast @ theta_ast
            f_perp = X_perp @ theta_perp
            sigma_perp = torch.sqrt(
                sigma_ast**2 + 1 / ref_model.num_obs * (f - f_perp).T @ (f - f_perp)
            )
            return sigma_perp.numpy()

        # define covariate names
        # todo: find a way of including `Intercept` in `var_names` throughout
        ref_vars = ["Intercept"] + ref_model.var_names
        res_vars = ["Intercept"] + res_model.var_names
        # extract parameter draws from both models
        theta_ast = torch.from_numpy(
            ref_model.inferencedata.posterior.stack(samples=("chain", "draw"))[ref_vars]
            .to_array()
            .values.T
        ).float()
        sigma_ast = torch.from_numpy(
            ref_model.inferencedata.posterior.stack(samples=("chain", "draw"))[
                ref_model.response_name + "_sigma"
            ].values.T
        ).float()
        theta_perp = torch.from_numpy(
            res_model.inferencedata.posterior.stack(samples=("chain", "draw"))[res_vars]
            .to_array()
            .values.T
        ).float()
        X_ast = ref_model.X
        X_perp = res_model.X
        # project the dispersion parameter
        _vec_proj = np.vectorize(
            _proj, signature="(n),(m),()->()", doc="Vectorised `_proj` method"
        )
        sigma_perp = (
            torch.from_numpy(_vec_proj(theta_ast, theta_perp, sigma_ast))
            .reshape(-1)
            .float()
        )
        # assure correct shape
        assert sigma_perp.shape == sigma_ast.shape
        return sigma_perp
