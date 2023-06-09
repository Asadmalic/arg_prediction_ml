
import os
import warnings
import random
import importlib
from typing import Union, Callable, List

import numpy as np
import pandas as pd

from ai4water import Model
import matplotlib.pyplot as plt
from SALib.plotting.hdmr import plot
import easy_mpl as ep
from ai4water.datasets import busan_beach
from ai4water.postprocessing._sa import morris_plots

from sklearn.model_selection import KFold


def read_data(file_name, inputs= None, target='ecoli',
              power_transform_target=True):

    fpath = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", file_name)
    df = pd.read_excel(fpath, index_col="Date_Time2")
    df.index = pd.to_datetime(df.index)

    default_inputs = ['wat_temp_c', 'tide_cm', 'sal_psu', 'pcp_mm', 'wind_speed_mps', 'air_p_hpa',
    'rel_hum']

    default_targets = [col for col in df.columns if col not in default_inputs]

    if inputs is None:
        inputs = default_inputs

    if not isinstance(target, list):
        if isinstance(target, str):
            target = [target]
    elif isinstance(target, list):
        pass
    else:
        target = default_targets

    assert isinstance(target, list)

    df = df[inputs + target]

    if power_transform_target:
        df[target] = np.power(10, df[target].values)

    return df


def make_whole_data(target,
                    reindex=True,
                    version='new',
                    remove_humidity=True,
                    power_transform_target=True,
                    ):
    data1 = busan_beach(inputs=['wat_temp_c', 'tide_cm', 'sal_psu', 'pcp_mm', 'wind_speed_mps',
                                'air_p_hpa', 'rel_hum'], target=target)

    assert version in ['new', 'old']

    if version == 'new':
        data2 = read_data(target=target, file_name="KarachiData_new.xlsx",
                          power_transform_target=power_transform_target)
        data3 = read_data(target=target, file_name="BalochistanData_new.xlsx",
                          power_transform_target=power_transform_target)
    else:
        data2 = read_data(target=target, file_name="KarachiData_old.xlsx",
                          power_transform_target=power_transform_target)
        data3 = read_data(target=target, file_name="BalochistanData_old.xlsx",
                          power_transform_target=power_transform_target)

    data= pd.concat([data1, data2, data3])

    data['pcp_mm'] = data['pcp_mm'].interpolate()

    if reindex:
        data = data.reset_index()
        # remove the "index" column which is inserted when we reset_index
        data.pop("index")

    if remove_humidity:
        data.pop("rel_hum")

    return data

def get_fitted_model():

    model = MyModel(
        model={
            "CatBoostRegressor": {
                "iterations": 500,
                "learning_rate": 0.49999999999999994,
                "l2_leaf_reg": 0.5,
                "model_size_reg": 3.1912231399066187,
                "rsm": 0.8001459176683743,
                "border_count": 1032,
                "feature_border_type": "UniformAndQuantiles",
                "logging_level": "Silent",
                "random_seed": 891
            }
        },
        x_transformation=[
            {
                "method": "quantile",
                "features": [
                    "wat_temp_c"
                ]
            },
            {
                "method": "robust",
                "features": [
                    "tide_cm"
                ]
            },
            {
                "method": "log",
                "features": [
                    "sal_psu"
                ],
                "treat_negatives": True,
                "replace_zeros": True
            },
            {
                "method": "sqrt",
                "features": [
                    "pcp_mm"
                ],
                "treat_negatives": True
            },
            {
                "method": "scale",
                "features": [
                    "wind_speed_mps"
                ]
            },
            {
                "method": "quantile",
                "features": [
                    "air_p_hpa"
                ]
            }
        ],
        y_transformation=[
            {
                "method": "log",
                "features": [
                    "aac_coppml"
                ],
                "treat_negatives": True,
                "replace_zeros": True
            }
        ],
        seed=891,
        input_features=[
            "wat_temp_c",
            "tide_cm",
            "sal_psu",
            "pcp_mm",
            "wind_speed_mps",
            "air_p_hpa"
        ],
        output_features=[
            "aac_coppml"
        ],
    )

    # %%
    train_df = pd.read_csv("../train_aac_rand.csv", index_col="Unnamed: 0")
    train_x, train_y = train_df.iloc[:, 0:-1], train_df.iloc[:, -1]

    print(train_x.shape, train_y.shape)

    _ = model.fit(x=train_x.values, y=train_y.values)

    return model


def sobol_plots(si, show=False, path:str=None):
    total, first, second = si.to_df()

    plt.close('all')
    bar_plot(total)
    if path:
        plt.savefig(os.path.join(path, "total"), bbox_inches="tight")
    if show:
        plt.show()

    plt.close('all')
    bar_plot(first)
    if path:
        plt.savefig(os.path.join(path, "first_order"), bbox_inches="tight")
    if show:
        plt.show()

    fig, ax = plt.subplots(figsize=(16, 6))
    bar_plot(second, ax=ax)
    if path:
        plt.savefig(os.path.join(path, "first_order"), bbox_inches="tight")
    if show:
        plt.show()

    return


def bar_plot(sis_df:pd.DataFrame, sort=True, conf_col = "_conf", **kwargs):

    conf_cols = sis_df.columns.str.contains(conf_col)

    sis = sis_df.loc[:, ~conf_cols].values
    confs = sis_df.loc[:, conf_cols].values
    names = sis_df.index

    if isinstance(names[0], tuple):
        names = np.array([str(i) for i in names])

    if len(sis) == sis.size:
        confs = confs.reshape(-1, )
        sis = sis.reshape(-1,)
    else:
        raise ValueError

    if sort:
        sort_idx = np.argsort(sis)
        confs = confs[sort_idx]
        sis = sis[sort_idx]
        names = names[sort_idx]

    label = sis_df.columns[~conf_cols][0]

    ax = ep.bar_chart(sis, names, orient="v", sort=sort, rotation=90, show=False,
                   label=label, **kwargs)
    if sort:
        ax.legend(loc="upper left")
    else:
        ax.legend(loc="best")

    ax.errorbar(np.arange(len(sis)), sis, yerr=confs, fmt=".", color="black")
    return ax



def sensitivity_plots(analyzer, si, path=None, show=False):

    if analyzer == "morris":
        morris_plots(si, path=path, show=show)

    elif analyzer in ["sobol"]:
        sobol_plots(si, show, path)

    elif analyzer == "hdmr":

        plt.close('all')
        plot(si)
        if path:
            plt.savefig(os.path.join(path, "hdmr"), bbox_inches="tight")

    elif analyzer in ["pawn"]:
        plt.close('all')
        si_df = si.to_df()
        bar_plot(si_df[["CV", "median"]], conf_col="median")
        if path:
            plt.savefig(os.path.join(path, "pawn_cv"), bbox_inches="tight")
        if show:
            plt.show()

    elif analyzer == "fast":
        plt.close('all')
        si_df = si.to_df()
        bar_plot(si_df[["S1", "S1_conf"]])
        if path:
            plt.savefig(os.path.join(path, "fast_s1"), bbox_inches="tight")
        if show:
            plt.show()

        plt.close('all')
        bar_plot(si_df[["ST", "ST_conf"]])
        if path:
            plt.savefig(os.path.join(path, "fast_s1"), bbox_inches="tight")
        if show:
            plt.show()


    elif analyzer == "delta":
        plt.close('all')
        si_df = si.to_df()
        bar_plot(si_df[["delta", "delta_conf"]])
        if path:
            plt.savefig(os.path.join(path, "fast_s1"), bbox_inches="tight")
        if show:
            plt.show()

        plt.close('all')
        bar_plot(si_df[["S1", "S1_conf"]])
        if path:
            plt.savefig(os.path.join(path, "fast_s1"), bbox_inches="tight")
        if show:
            plt.show()

    elif analyzer == "rbd_fast":
        plt.close('all')
        si_df = si.to_df()
        bar_plot(si_df[["S1", "S1_conf"]])
        if path:
            plt.savefig(os.path.join(path, "rbd_fast_s1"), bbox_inches="tight")
        if show:
            plt.show()
    return


class MyModel(Model):

    def sensitivity_analysis(
            self,
            data=None,
            bounds=None,
            sampler="morris",
            analyzer: Union[str, list] = "sobol",
            sampler_kwds: dict = None,
            analyzer_kwds: dict = None,
            save_plots: bool = True,
            names: List[str] = None
    ) -> dict:
        """performs sensitivity analysis of the model w.r.t input features in data.
        The model and its hyperprameters remain fixed while the input data is changed.
        Parameters
        ----------
        data :
            data which will be used to get the bounds/limits of input features. If given,
            it must be 2d numpy array. It should be remembered that the given data
            is not used during sensitivity analysis. But new synthetic data is prepared
            on which sensitivity analysis is performed.
        bounds : list,
            alternative to data
        sampler : str, optional
            any sampler_ from SALib library. For example ``morris``, ``fast_sampler``,
            ``ff``, ``finite_diff``, ``latin``, ``saltelli``, ``sobol_sequence``
        analyzer : str, optional
            any analyzer_ from SALib lirary. For example ``sobol``, ``dgsm``, ``fast``
            ``ff``, ``hdmr``, ``morris``, ``pawn``, ``rbd_fast``. You can also choose
            more than one analyzer. This is useful when you want to compare results
            of more than one analyzers. It should be noted that having more than
            one analyzers does not increases computation time except for ``hdmr``
            and ``delta`` analyzers. The ``hdmr`` and ``delta`` analyzers ane computation
            heavy. For example
            >>> analyzer = ["morris", "sobol", "rbd_fast"]
        sampler_kwds : dict
            keyword arguments for sampler
        analyzer_kwds : dict
            keyword arguments for analyzer
        save_plots : bool, optional
        names : list, optional
            names of input features. If not given, names of input features will be used.
        Returns
        -------
        dict :
            a dictionary whose keys are names of analyzers and values and sensitivity
            results for that analyzer.
        Examples
        --------
        >>> from ai4water import Model
        >>> from ai4water.datasets import busan_beach
        >>> df = busan_beach()
        >>> input_features=df.columns.tolist()[0:-1]
        >>> output_features = df.columns.tolist()[-1:]
        ... # build the model
        >>> model=Model(model="RandomForestRegressor",
        >>>     input_features=input_features,
        >>>     output_features=output_features)
        ... # train the model
        >>> model.fit(data=df)
        .. # perform sensitivity analysis
        >>> si = model.sensitivity_analysis(data=df[input_features].values,
        >>>                    sampler="morris", analyzer=["morris", "sobol"],
        >>>                        sampler_kwds={'N': 100})
        .. _sampler:
            https://salib.readthedocs.io/en/latest/api/SALib.sample.html
        .. _analyzer:
            https://salib.readthedocs.io/en/latest/api/SALib.analyze.html
        """
        try:
            import SALib
        except (ImportError, ModuleNotFoundError):
            warnings.warn("""
            You must have SALib library installed in order to perform sensitivity analysis.
            Please install it using 'pip install SALib' and make sure that it is importable
            """)
            return {}

        #from ai4water.postprocessing._sa import sensitivity_analysis, sensitivity_plots
        #from ai4water.postprocessing._sa import _make_predict_func

        if data is not None:
            if not isinstance(data, np.ndarray):
                assert isinstance(data, pd.DataFrame)
                data = data.values
            x = data

            # calculate bounds
            assert isinstance(x, np.ndarray)
            bounds = []
            for feat in range(x.shape[1]):
                bound = [np.min(x[:, feat]), np.max(x[:, feat])]
                bounds.append(bound)
        else:
            assert bounds is not None
            assert isinstance(bounds, list)
            assert all([isinstance(bound, list) for bound in bounds])

        analyzer_kwds = analyzer_kwds or {}

        if self.lookback > 1:
            if self.category == "DL":
                func = _make_predict_func(self, verbose=0)
            else:
                func = _make_predict_func(self)
        else:
            func = self.predict

        results = sensitivity_analysis(
            sampler,
            analyzer,
            func,
            bounds=bounds,
            sampler_kwds=sampler_kwds,
            analyzer_kwds=analyzer_kwds,
            names=names or self.input_features
        )

        if save_plots:
            for _analyzer, result in results.items():
                res_df = result.to_df()
                if isinstance(res_df, list):
                    for idx, res in enumerate(res_df):
                        fname = os.path.join(self.path, f"{_analyzer}_{idx}_results.csv")
                        res.to_csv(fname)
                else:
                    res_df.to_csv(os.path.join(self.path, f"{_analyzer}_results.csv"))

                sensitivity_plots(_analyzer, result, self.path)

        return results


def sensitivity_analysis(
        sampler: str,
        analyzer: Union[str, list],
        func: Callable,
        bounds: list,
        sampler_kwds: dict = None,
        analyzer_kwds: dict = None,
        names: list = None,
        **kwargs
) -> dict:
    """
    Parameters
    ----------
    sampler :
    analyzer :
    func :
    bounds :
    sampler_kwds :
    analyzer_kwds :
    names :
    **kwargs :
    """
    sampler = importlib.import_module(f"SALib.sample.{sampler}")

    if names is None:
        names = [f"Feat{i}" for i in range(len(bounds))]

    # Define the model inputs
    problem = {
        'num_vars': len(bounds),
        'names': names,
        'bounds': bounds
    }

    sampler_kwds = sampler_kwds or {'N': 100}

    param_values = sampler.sample(problem=problem, **sampler_kwds)
    print("total samples:", len(param_values))

    y = func(x=param_values, **kwargs)

    y = np.array(y)

    assert np.size(y) == len(y), f"output must be 1 dimensional"
    y = y.reshape(-1, )

    results = {}
    if isinstance(analyzer, list):
        for _analyzer in analyzer:
            print(f"Analyzing with {_analyzer}")
            results[_analyzer] = analyze(_analyzer, param_values, y, problem, analyzer_kwds)
    else:
        assert isinstance(analyzer, str)
        results[analyzer] = analyze(analyzer, param_values, y, problem, analyzer_kwds)

    return results


def analyze(analyzer, param_values, y, problem, analyzer_kwds):
    _analyzer = importlib.import_module(f"SALib.analyze.{analyzer}")
    analyzer_kwds = analyzer_kwds or {}

    if analyzer in ["hdmr",
                    "morris",
                    "dgsm",
                    "ff",
                    "pawn",
                    "rbd_fast", "delta",
                    ] and 'X' not in analyzer_kwds:
        analyzer_kwds['X'] = param_values

    Si = _analyzer.analyze(problem=problem, Y=y, **analyzer_kwds)

    if 'X' in analyzer_kwds:
        analyzer_kwds.pop('X')

    return Si


def _make_predict_func(model, **kwargs):

    from ai4water.preprocessing import DataSet

    lookback = model.config["ts_args"]['lookback']

    def func(x):
        x = pd.DataFrame(x, columns=model.input_features)

        ds = DataSet(data=x,
                     ts_args=model.config["ts_args"],
                     input_features=model.input_features,
                     train_fraction=1.0,
                     val_fraction=0.0,
                     verbosity=0)

        x, _ = ds.training_data()
        p = model.predict(x=x, **kwargs)

        return np.concatenate([p, np.zeros((lookback-1, 1))])

    return func


def plot_convergence(
        results: dict,
        method: str,
        item: str, sub_method: str = '',
        xlabel_kws = None,
        ylabel_kws = None,
        xticklabel_kws = None,
        yticklabel_kws = None,
        leg_kws = None,
        labels=None,
        figsize=(14, 8)
):
    random.seed(313)

    _n = list(results.keys())[0]
    meth = list(results[_n].keys())[0]
    names = results[_n][meth]["names"]

    markers = ["--o", "--*", "--.", "--^"]

    convergence = {n: [] for n in names}

    for n, result in results.items():
        method_si = result[method]
        method_si_df = method_si.to_df()

        if method == "sobol":
            total, first, second = method_si_df
            if sub_method == "first":
                method_si_df = first
            elif sub_method == "second":
                method_si_df = second
            else:
                method_si_df = total

        for feature in convergence.keys():
            val = method_si_df.loc[feature, item]

            convergence[feature].append(val)

    fig, ax = plt.subplots(figsize=figsize)

    for idx, (key, val) in enumerate(convergence.items()):
        marker = random.choice(markers)
        if labels is None:
            label = key
        else:
            label = labels[idx]
        ax = ep.plot(val, marker, label=label, show=False, ax=ax)

    leg_kws = leg_kws or {"fontsize": 14}
    ax.legend(loc=(1.01, 0.01), **leg_kws)

    ylabel_kws = ylabel_kws or {'fontsize': 14}
    ax.set_ylabel(item, **ylabel_kws)
    xlabel_kws = xlabel_kws or {'fontsize':14}
    ax.set_xlabel("Number of Model Evaluations", **xlabel_kws)
    ax.set_title(f"Convergence of {method} Sensitivity Analysis {sub_method}", fontsize=14)

    xticklabels = list(results.keys())
    ax.set_xticks(np.arange(len(xticklabels)))
    xticklabel_kws = xticklabel_kws or {'fontsize': 12}
    ax.set_xticklabels(xticklabels, **xticklabel_kws)

    #yticklabel_kws = yticklabel_kws or {'fontsize': 12}
    #ax.set_yticklabels(ax.get_yticklabels(), **yticklabel_kws)

    return ax


def confidenc_interval(model, X_train, y_train, X_test, alpha,
                    n_splits=5):
    def generate_results_dataset(preds, ci):
        df = pd.DataFrame()
        df['prediction'] = preds
        if ci >= 0:
            df['upper'] = preds + ci
            df['lower'] = preds - ci
        else:
            df['upper'] = preds - ci
            df['lower'] = preds + ci

        return df

    model.fit(X_train, y_train)
    residuals = y_train - model.predict(X_train)
    ci = np.quantile(residuals, 1 - alpha)
    preds = model.predict(X_test)
    df = generate_results_dataset(preds.reshape(-1, ), ci)

    kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
    res = []
    estimators = []
    for train_index, test_index in kf.split(X_train):
        X_train_, X_test_ = X_train[train_index], X_train[test_index]
        y_train_, y_test_ = y_train[train_index], y_train[test_index]

        model.fit(X_train_, y_train_)
        estimators.append(model)
        _pred = model.predict(X_test_)
        res.extend(list(y_test_ - _pred.reshape(-1, )))

    y_pred_multi = np.column_stack([e.predict(X_test) for e in estimators])

    ci = np.quantile(res, 1 - alpha)
    top = []
    bottom = []
    for i in range(y_pred_multi.shape[0]):
        if ci > 0:
            top.append(np.quantile(y_pred_multi[i] + ci, 1 - alpha))
            bottom.append(np.quantile(y_pred_multi[i] - ci, 1 - alpha))
        else:
            top.append(np.quantile(y_pred_multi[i] - ci, 1 - alpha))
            bottom.append(np.quantile(y_pred_multi[i] + ci, 1 - alpha))

    preds = np.median(y_pred_multi, axis=1)
    df = pd.DataFrame()
    df['pred'] = preds
    df['upper'] = top
    df['lower'] = bottom

    fig, ax = plt.subplots(figsize=(6, 3))
    ax.fill_between(np.arange(len(df)), df['upper'], df['lower'], alpha=0.5, color='C1')
    p1 = ax.plot(df['pred'], color="C1", label="Prediction")
    p2 = ax.fill(np.NaN, np.NaN, color="C1", alpha=0.5)
    percent = int((1 - alpha) * 100)
    ax.legend([(p2[0], p1[0]), ], [f'{percent}% Confidence Interval'],
              fontsize=12)
    ax.set_xlabel("Test Samples", fontsize=12)
    ax.set_ylabel(model.output_features[0], fontsize=12)
    fpath = os.path.join(model.path, f"{percent}_interval_")
    plt.savefig(fpath, dpi=300, bbox_inches="tight")
    plt.show()

    return
