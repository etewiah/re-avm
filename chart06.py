'''create charts showing results of valgbr.py
INVOCATION
  python chart06.py --data
  python chart06.py FEATURESGROUP-HPS-LOCALITY [--test] [--subset] [--norwalk]
where
  FEAUTURES is one of {s, sw, swp, swpn}
  HPS is one of {all, best1}
  LOCALILTY is one of {census, city, global, zip}
  FHL is FEATURESGROUP-HPS
  --test means to set control.arg.test to True
  --subset means to process 0data-subset, not 0data, the full reduction
  --norwalk means to process 0data-norwalk, not 0data, the full reduction
INPUT FILES
 WORKING/chart01/data.pickle
 WORKING/valavm/FHL/YYYYMM.pickle
INPUT AND OUTPUT FILES (build with --data)
 WORKING/chart06/FHL/0data.pickle         | reduction for everything
 WORKING/chart06/FHL/0data-norwalk.pickle | reduction for just Norwalk (for testing); only if locality == city
 WORKING/chart06/FHL/0data-subset.pickle | random subset of everything (for testing)
OUTPUT FILES
 WORKING/chart06/FHL/0data-report.txt | records retained TODO: Decide whether to keep
 WORKING/chart06/FHL/a.pdf           | range of losses by model (graph)
 WORKING/chart06/FHL/b-YYYYMM.pdf    | HPs with lowest losses
 WORKING/chart06/FHL/b-YYYYMM.txt    | HPs with lowest losses
 WORKING/chart06/FHL/c.pdf           | best model each month
 WORKING/chart06/FHL/d.pdf           | best & 50th best each month
 WORKING/chart06/FHL/e.pdf           | best 50 models each month (was chart07)
 WORKING/chart06/FHL/best.pickle     | dataframe with best choices each month # CHECK

The reduction is a dictionary.
- if LOCALITY is 'global', the type of the reduction is
  dict[validation_month] sd
  where sd is a sorted dictionary with type
  dict[ModelDescription] ModelResults, sorted by increasing ModelResults.mae
- if LOCALITY is 'city', the type of the reduction is
  dict[city_name] dict[validation_month] sd
'''

from __future__ import division

import argparse
import collections
import cPickle as pickle
import glob
import itertools
import math
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pdb
from pprint import pprint
import random
import sys

import arg_type
from AVM import AVM
from Bunch import Bunch
from chart06types import ModelDescription, ModelResults, ColumnDefinitions
from ColumnsTable import ColumnsTable
from columns_contain import columns_contain
import dirutility
import errors
from Logger import Logger
from Month import Month
from Path import Path
from Report import Report
from Timer import Timer
from valavmtypes import ResultKeyEn, ResultKeyGbr, ResultKeyRfr, ResultValue
cc = columns_contain


def trace_unless(condition, message, **kwds):
    'like assert condition, message; but enters debugger if condition fails'
    if condition:
        return
    print '+++++++++++++++'
    for k, v in kwds.iteritems():
        print k, v
    print message
    print '+++++++++++++++'
    pdb.set_trace()


def make_control(argv):
    'return a Bunch'
    print argv
    parser = argparse.ArgumentParser()
    parser.add_argument('fhl', type=arg_type.features_hps_locality)
    parser.add_argument('--data', action='store_true')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--subset', action='store_true')
    parser.add_argument('--norwalk', action='store_true')
    arg = parser.parse_args(argv[1:])  # arg.__dict__ contains the bindings
    arg.base_name = 'chart06'

    # for now, we only know how to process global files
    # local files will probably have a different path in WORKING/valavm/
    # details to be determined
    arg.features, arg.hsheps, arg.locality = arg.fhl.split('-')
    assert arg.locality == 'global' or arg.locality == 'city', arg.fhl
    if arg.norwalk:
        assert arg.locality == 'city', argv

    random_seed = 123
    random.seed(random_seed)

    # assure output directory exists
    dir_working = Path().dir_working()
    dir_out_reduction = dirutility.assure_exists(dir_working + arg.base_name) + '/'
    dir_out = dirutility.assure_exists(dir_out_reduction + arg.fhl) + '/'

    validation_months = (
            '200612',
            '200701', '200702', '200703', '200704', '200705', '200706',
            '200707', '200708', '200709', '200710', '200711',
            )
    validation_months_long = (
            '200512',
            '200601', '200602', '200603', '200604', '200605', '200606',
            '200607', '200608', '200609', '200610', '200611', '200612',
            '200701', '200702', '200703', '200704', '200705', '200706',
            '200707', '200708', '200709', '200710', '200711', '200712',
            '200801', '200802', '200803', '200804', '200805', '200806',
            '200807', '200808', '200809', '200810', '200811', '200812',
            '200901', '200902',
            )
    return Bunch(
        arg=arg,
        column_definitions=ColumnDefinitions(),
        debug=False,
        errors=[],
        exceptions=[],
        path_in_valavm='%svalavm/%s/*.pickle' % (
            dir_working,
            arg.fhl,
            ),
        path_in_chart_01_reduction=dir_working + 'chart01/0data.pickle',
        path_in_data=dir_out + (
            '0data-subset.pickle' if arg.subset else
            '0data-norwalk.pickle' if arg.norwalk else
            '0data.pickle'
        ),
        path_in_interesting_cities=dir_working + 'interesting_cities.txt',
        path_out_a=dir_out + 'a.pdf' if arg.locality == 'global' else dir_out + 'a-%s.pdf',
        path_out_b=dir_out + 'b-%d.txt',
        path_out_cd=dir_out + '%s.txt',
        path_out_c_pdf=dir_out+'c.pdf',
        path_out_b_pdf_subplots=dir_out + 'b.pdf',
        path_out_b_pdf=dir_out + 'b-%d.pdf',
        path_out_d=dir_out + 'd.txt',
        path_out_e_txt=dir_out + 'e-%04d-%6s.txt',
        path_out_e_pdf=dir_out + 'e-%04d.pdf',
        path_out_f=dir_out + 'f-%04d.txt',
        path_out_g=dir_out + 'g.txt',
        path_out_h_template=(
            dir_out + 'h-%03d-%6s.txt' if arg.locality == 'global' else dir_out + 'h-%s-%03d-%6s.txt'
            ),
        path_out_i=dir_out + 'i.txt',
        path_out_data=dir_out + '0data.pickle',
        path_out_data_report=dir_out + '0data-report.txt',
        path_out_data_subset=dir_out + '0data-subset.pickle',
        path_out_data_norwalk=dir_out + '0data-norwalk.pickle',
        path_out_log=dir_out + '0log' + ('-data' if arg.data else '') + '.txt',
        random_seed=random_seed,
        sampling_rate=0.02,
        test=arg.test,
        timer=Timer(),
        validation_months=validation_months,
        validation_months_long=validation_months_long,
    )


def select_and_sort(df, year, month, model):
    'return new df contain sorted observations for specified year, month, model'
    yyyymm = str(year * 100 + month)
    mask = (
        (df.model == model) &
        (df.validation_month == yyyymm)
    )
    subset = df.loc[mask]
    if len(subset) == 0:
        print 'empty subset'
        print year, month, model, sum(df.model == model), sum(df.validation_month == yyyymm)
        pdb.set_trace()
    return subset.sort_values('mae')


def make_chart_a(reduction, median_prices, control):
    'graph range of errors by month by method'
    print 'make_chart_a'

    def make_subplot(validation_month, reduction, relevant_median_prices):
        'mutate the default axes'
        # draw one line for each model family
        for model in ('en', 'gb', 'rf'):
            y = [v.mae
                 for k, v in reduction[validation_month].iteritems()
                 if k.model == model
                 ]
            plt.plot(y, label=model)  # the reduction is sorted by increasing mae
            plt.yticks(size='xx-small')
            if Month(validation_month) not in relevant_median_prices:
                print validation_month
                print relevant_median_prices
                print 'should not happen'
                pdb.set_trace()
            plt.title('yr mnth %s med price %6.0f' % (
                validation_month,
                relevant_median_prices[Month(validation_month)]),
                      loc='right',
                      fontdict={'fontsize': 'xx-small',
                                'style': 'italic',
                                },
                      )
            plt.xticks([])  # no ticks on x axis
        return

    def make_figure(reduction, path_out, city, relevant_median_prices):
        # make and save figure

        # debug: sometimes relevant_median_prices is empty
        if len(relevant_median_prices) == 0:
            print 'no median prices', city
            pdb.set_trace()

        plt.figure()  # new figure
        # plt.suptitle('Loss by Test Period, Tree Max Depth, N Trees')  # overlays the subplots
        axes_number = 0
        validation_months = ('200612', '200701', '200702', '200703', '200704', '200705',
                             '200706', '200707', '200708', '200709', '200710', '200711',
                             )
        row_seq = (1, 2, 3, 4)
        col_seq = (1, 2, 3)
        cities = city is not None
        for row in row_seq:
            for col in col_seq:
                validation_month = validation_months[axes_number]
                if cities:
                    print 'city %s validation_month %s num transactions %d' % (
                        city,
                        validation_month,
                        len(reduction[validation_month]))
                axes_number += 1  # count across rows
                plt.subplot(len(row_seq), len(col_seq), axes_number)  # could be empty, if no transactions in month
                make_subplot(validation_month, reduction, relevant_median_prices)
                # annotate the bottom row only
                if row == 4:
                    if col == 1:
                        plt.xlabel('hp set')
                        plt.ylabel('mae x $1000')
                    if col == 3:
                        plt.legend(loc='best', fontsize=5)

        plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=1.0)
        plt.savefig(path_out)
        plt.close()

    if control.arg.locality == 'global':
        make_figure(reduction, control.path_out_a, None, median_prices)
    elif control.arg.locality == 'city':

        def make_city(city):
            print 'make_city', city
            assert len(reduction[city]) > 0, city  # detect bug found in earlier version
            return make_figure(reduction[city], control.path_out_a % city, city, median_prices[city])

        for city in reduction.keys():
            make_city(city)
    else:
        print 'bad control.arg.locality', control.arg
        pdb.set_trace()
    return


class ChartBReport(object):
    def __init__(self, validation_month, k, column_definitions, test):
        self._report = Report()
        self._header(validation_month, k)
        self._column_definitions = column_definitions
        self._test = test
        cd = self._column_definitions.defs_for_columns(
            'median_absolute_error', 'model', 'n_months_back',
            'max_depth', 'n_estimators', 'max_features',
            'learning_rate',
        )
        self._ct = ColumnsTable(columns=cd, verbose=True)

    def _header(self, validation_month, k):
        def a(line):
            self._report.append(line)

        a('MAE for %d best-performing models and their hyperparameters' % k)
        a('Validation month: %s' % validation_month)
        a(' ')

    def append_detail(self, **kwds):
        # replace NaN with None
        with_spaces = {
            k: (None if self._column_definitions.replace_by_spaces(k, v) else v)
            for k, v in kwds.iteritems()
        }
        self._ct.append_detail(**with_spaces)

    def write(self, path):
        self._ct.append_legend()
        for line in self._ct.iterlines():
            self._report.append(line)
        if self._test:
            self._report.append('**TESTING: DISCARD')
        self._report.write(path)


def make_chart_b(reduction, control, median_price):
    def make_models_maes(validation_month):
        'return model names and MAEs for K best models in the valdation month'
        k = 50  # report on the first k models in the sorted subset
        # ref: http://stackoverflow.com/questions/7971618/python-return-first-n-keyvalue-pairs-from-dict
        first_k_items = itertools.islice(reduction[validation_month].items(), 0, k)
        graphX = []
        graphY = []
        for key, value in first_k_items:
            graphY.append(value.mae)
            graphX.append(key.model)

        return graphX, graphY

    def make_figure():
        'make and write figure'
        plt.figure()  # new figure
        validation_months = control.validation_months
        row_seq = (1, 2, 3, 4)
        col_seq = (1, 2, 3)
        axes_number = 0
        for row in row_seq:
            for col in col_seq:
                validation_month = validation_months[axes_number]
                axes_number += 1  # count across rows
                ax1 = plt.subplot(len(row_seq), len(col_seq), axes_number)
                graphX, graphY = make_models_maes(validation_month)
                patterns = ["", "", "*"]
                # the reduction is sorted by increasing mae
                # Jonathan
                ax1.set_title(
                    'Validation Month: %s' % (validation_month),
                    loc='right',
                    fontdict={'fontsize': 'xx-small', 'style': 'italic'},
                    )
                for i in range(len(graphX)):
                    if graphX[i] == 'gb':
                        plt.bar(i, graphY[i], color='white', edgecolor='black', hatch=patterns[0])
                    elif graphX[i] == 'rf':
                        plt.bar(i, graphY[i], color='black', edgecolor='black', hatch=patterns[1])
                    elif graphX[i] == 'en':
                        plt.bar(i, graphY[i], color='green', edgecolor='black', hatch=patterns[2])
                plt.yticks(size='xx-small')
                plt.xticks([])

                # annotate the bottom row only
                if row == 4:
                    if col == 1:
                        plt.xlabel('Models')
                        plt.ylabel('MAE')
                    if col == 3:
                        plt.legend(loc='best', fontsize=5)

        plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=1.0)
        plt.savefig(control.path_out_b_pdf_subplots)
        plt.close()

    def make_figure2(validation_month):
        '''make and write figure for the validation month
        Part 1:
        for the validation month
        one bar for each of the first 50 best models
        the height of the bar is the MAE in ($)
        Part 2:
        produce a 2-up chart, where the top chart is as in part 1
        and the bottom chart has as y axis the absolute relative error
        '''

        print 'creating figure b', validation_month

        # plt.suptitle('Loss by Test Period, Tree Max Depth, N Trees')  # overlays the subplots
        bar_color = {'gb': 'white', 'rf': 'black', 'en': 'red'}
        models, maes = make_models_maes(validation_month)
        assert len(models) == len(maes)
        assert len(models) > 0
        # the reduction is sorted by increasing mae
        # Jonathan
        fig = plt.figure()
        fig1 = fig.add_subplot(211)

        plt.title(
            'Validation Month: %s' % (validation_month),
            loc='right',
            fontdict={'fontsize': 'large', 'style': 'italic'},
            )
        for i, model in enumerate(models):
            fig1.bar(i, maes[i], color=bar_color[model])
        plt.yticks(size='xx-small')
        plt.xticks([])
        plt.xlabel('Models in order of increasing MAE')
        plt.ylabel('MAE ($)')

        white_patch = mpatches.Patch(
            facecolor='white',
            edgecolor='black',
            lw=1,
            label="Gradient Boosting",
            )
        black_patch = mpatches.Patch(
            facecolor='black',
            edgecolor='black',
            lw=1,
            label="Random Forest",
            )

        plt.legend(handles=[white_patch, black_patch], loc=2)
        plt.ylim(0, 180000)

        fig2 = fig.add_subplot(212)
        for i, model in enumerate(models):
            fig2.bar(i, maes[i]/median_price[Month(validation_month)], color=bar_color[model])

        plt.yticks(size='xx-small')
        plt.xticks([])
        plt.xlabel('Models in order of increasing MAE')
        plt.ylabel('Absolute Relative Error')
        plt.ylim(0, .3)

        white_patch = mpatches.Patch(
            facecolor='white',
            edgecolor='black',
            lw=1,
            label="Gradient Boosting",
            )
        black_patch = mpatches.Patch(
            facecolor='black',
            edgecolor='black',
            lw=1,
            label="Random Forest",
            )

        plt.legend(handles=[white_patch, black_patch], loc=2)
        plt.savefig(control.path_out_b_pdf % int(validation_month))
        plt.close()

    # produce the pdf files
    for validation_month in control.validation_months:  # TODO: validation_month_long
        make_figure2(validation_month)
    make_figure()

    def write_report(year, month):
        validation_month = str(year * 100 + month)
        k = 50  # report on the first k models in the sorted subset
        report = ChartBReport(validation_month, k, control.column_definitions, control.test)
        detail_line_number = 0
        # ref: http://stackoverflow.com/questions/7971618/python-return-first-n-keyvalue-pairs-from-dict
        first_k = itertools.islice(reduction[validation_month].items(), 0, k)
        graphX = []
        graphY = []
        for key, value in first_k:
            report.append_detail(
                median_absolute_error=value.mae,
                model=key.model,
                n_months_back=key.n_months_back,
                max_depth=key.max_depth,
                n_estimators=key.n_estimators,
                max_features=key.max_features,
                learning_rate=key.learning_rate,
            )
            graphX.append(value.mae)
            graphY.append(key.model)
            detail_line_number += 1
            if detail_line_number > k:
                break
        report.write(control.path_out_b % int(validation_month))

    # produce the txt file
    for year in (2006, 2007):
        months = (12,) if year == 2006 else (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
        for month in months:
            write_report(year, month)


class ChartCDReport(object):
    def __init__(self, column_definitions, test):
        self._column_definitions = column_definitions
        self._test = test
        self._report = Report()
        cd = self._column_definitions.defs_for_columns(
            'validation_month', 'rank', 'median_absolute_error',
            'median_price', 'model', 'n_months_back',
            'max_depth', 'n_estimators', 'max_features',
            'learning_rate', 'alpha', 'l1_ratio',
            'units_X', 'units_y',
        )
        self._ct = ColumnsTable(columns=cd, verbose=True)
        self._header()

    def append(self, line):
        self._report.append(line)

    def write(self, path):
        self._ct.append_legend()
        for line in self._ct.iterlines():
            self._report.append(line)
        if self._test:
            self._report.append('** TESTING: DISCARD')
        self._report.write(path)

    def _header(self):
        self._report.append('Median Absolute Error (MAE) by month for best-performing models and their hyperparameters')
        self._report.append(' ')

    def append_detail(self, **kwds):
        with_spaces = {
            k: (None if self._column_definitions.replace_by_spaces(k, v) else v)
            for k, v in kwds.iteritems()
        }
        self._ct.append_detail(**with_spaces)


def make_chart_cd(reduction, median_prices, control, detail_line_indices, report_id):
    r = ChartCDReport(control.column_definitions, control.test)
    my_validation_months = []
    my_price = []
    my_mae = []
    for validation_month in control.validation_months_long:
        median_price = median_prices[Month(validation_month)]

        if validation_month not in reduction:
            control.exceptions.append('reduction is missing month %s' % validation_month)
            continue
        month_result_keys = reduction[validation_month].keys()
        my_validation_months.append(validation_month)
        my_price.append(median_price)
        for detail_line_index in detail_line_indices:
            if detail_line_index >= len(month_result_keys):
                continue  # this can happend when using samples
            try:
                k = month_result_keys[detail_line_index]
            except:
                pdb.set_trace()
            k = month_result_keys[detail_line_index]
            v = reduction[validation_month][k]
            r.append_detail(
                validation_month=validation_month,
                rank=detail_line_index + 1,
                median_absolute_error=v.mae,
                median_price=median_price,
                model=k.model,
                n_months_back=k.n_months_back,
                max_depth=k.max_depth,
                n_estimators=k.n_estimators,
                max_features=k.max_features,
                learning_rate=k.learning_rate,
                alpha=k.alpha,
                l1_ratio=k.l1_ratio,
                units_X=k.units_X[:3],
                units_y=k.units_y[:3],
            )
        my_mae.append(reduction[validation_month][month_result_keys[0]].mae)

    fig = plt.figure()
    fig1 = fig.add_subplot(211)
    fig1.bar(range(len(my_validation_months)), my_mae, color='blue')
    labels = my_validation_months
    plt.xticks([x+.6 for x in range(len(my_validation_months))], labels, rotation=-70, size='xx-small')

    plt.yticks(size='xx-small')
    plt.xlabel('Year-Month')
    plt.ylabel('Median Absolute Error ($)')
    plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=1.0)
    fig2 = fig.add_subplot(212)
    fig2.bar(
        range(len(my_validation_months)),
        [int(m) / int(p) for m, p in zip(my_mae, my_price)],
        color='blue',
        )
    plt.xticks([
        x+.6
        for x in range(len(my_validation_months))
        ],
        labels,
        rotation=-70,
        size='xx-small',
        )

    plt.yticks(size='xx-small')
    plt.xlabel('Year-Month')
    plt.ylabel('Absolute Relative Error')

    plt.tight_layout(pad=0.4, w_pad=0.5, h_pad=1.0)

    plt.savefig(control.path_out_c_pdf)
    plt.close()

    r.write(control.path_out_cd % report_id)
    return


class ChartEReport(object):
    def __init__(self, k, ensemble_weighting, column_definitions, test):
        self._column_definitions = column_definitions
        self._test = test
        self._report = Report()
        self._header(k, ensemble_weighting)
        cd = self._column_definitions.defs_for_columns(
            'validation_month', 'model', 'n_months_back',
            'n_estimators', 'max_features', 'max_depth',
            'learning_rate', 'rank', 'weight',
            'mae_validation', 'mae_query', 'mae_ensemble',
        )
        self._ct = ColumnsTable(columns=cd, verbose=True)

    def write(self, path):
        self._ct.append_legend()
        for line in self._ct.iterlines():
            self._report.append(line)
        if self._test:
            self._report.append('** TESTING: DISCARD')
        self._report.write(path)

    def detail_line(self, **kwds):
        with_spaces = {
            k: (None if self._column_definitions.replace_by_spaces(k, v) else v)
            for k, v in kwds.iteritems()
        }
        self._ct.append_detail(**with_spaces)

    def _header(self, k, ensemble_weighting):
        self._report.append('Performance of Best Models Separately and as an Ensemble')
        self._report.append(' ')
        self._report.append('Considering Best K = %d models' % k)
        self._report.append('Ensemble weighting: %s' % ensemble_weighting)


class ChartHReport(object):
    def __init__(self, k, validation_month, ensemble_weighting, column_definitions, test):
        self._column_definitions = column_definitions
        self._report = Report()
        self._test = test
        self._header(k, validation_month, ensemble_weighting)
        cd = self._column_definitions.defs_for_columns(
            'description',
            'mae_validation',
            'mae_query',
            'mare_validation',
            'mare_query',
        )
        self._ct = ColumnsTable(columns=cd, verbose=True)

    def write(self, path):
        self._ct.append_legend()
        for line in self._ct.iterlines():
            self._report.append(line)
        if self._test:
            self._report.append('** TESTING: DISCARD')
        self._report.write(path)

    def detail_line(self, **kwds):
        with_spaces = {
            k: (None if self._column_definitions.replace_by_spaces(k, v) else v)
            for k, v in kwds.iteritems()
        }
        self._ct.append_detail(**with_spaces)

    def preformatted_line(self, line):
        print line
        self._ct.append_line(line)

    def _header(self, k, validation_month, ensemble_weighting):
        self._report.append('Performance of Best Models Separately and as an Ensemble')
        self._report.append(' ')
        self._report.append('Considering Best K = %d models' % k)
        self._report.append('For validation month %s' % validation_month)
        self._report.append('Ensemble weighting: %s' % ensemble_weighting)


class ChartIReport(object):
    def __init__(self, column_definitions, test):
        self._column_definitions = column_definitions
        self._report = Report()
        self._header()
        self._test = test
        self._appended = []
        cd = self._column_definitions.defs_for_columns(
            'validation_month',
            'k',
            'oracle_less_best',
            'oracle_less_ensemble',
            )
        self._ct = ColumnsTable(columns=cd, verbose=True)

    def write(self, path):
        self._ct.append_legend()
        for line in self._ct.iterlines():
            self._report.append(line)
        for line in self._appended:
            self._report.append(line)
        if self._test:
            self._report.append('** TESTING: DISCARD')
        self._report.write(path)

    def append(self, line):
        self._ct.append_line(line)

    def detail_line(self, **kwds):
        with_spaces = {
            k: (None if self._column_definitions.replace_by_spaces(k, v) else v)
            for k, v in kwds.iteritems()
        }
        self._ct.append_detail(**with_spaces)

    def _header(self):
        self._report.append('Performance of Best and Ensemble Models Relative to the Oracle')
        self._report.append(' ')


class ChartFReport(object):
    def __init__(self, k, ensemble_weighting, column_definitions, test):
        self._column_definitions = column_definitions
        self._test = test
        self._report = Report()
        self._header(k, ensemble_weighting)
        cd = self._column_definitions.defs_for_columns(
            'validation_month',
            'mae_index0',
            'mae_ensemble',
            'mae_best_next_month',
            'median_price',
            'fraction_median_price_next_month_index0',
            'fraction_median_price_next_month_ensemble',
            'fraction_median_price_next_month_best',
        )
        self._ct = ColumnsTable(columns=cd, verbose=True)

    def write(self, path):
        self._ct.append_legend()
        for line in self._ct.iterlines():
            self._report.append(line)
        if self._test:
            self._report.append('** TESTING: DISCARD')
        self._report.write(path)

    def detail_line(self, **kwds):
        with_spaces = {
            k: (None if self._column_definitions.replace_by_spaces(k, v) else v)
            for k, v in kwds.iteritems()
        }
        self._ct.append_detail(**with_spaces)

    def _header(self, k, ensemble_weighting):
        self._report.append('Comparison of Errors of Ensemble and Best Model That Know the Future')
        self._report.append(' ')
        self._report.append('Considering Best K = %d models' % k)
        self._report.append('Ensemble weighting: %s' % ensemble_weighting)


def check_actuals(actuals):
    'each should be the same'
    k = len(actuals)
    assert k > 0, k
    first = actuals[0]
    for other in actuals:
        if collections.Counter(first) != collections.Counter(other):
            print collections.Counter(first), collections.Counter(other)
            pdb.set_trace()


def make_ensemble_predictions(predictions, weights):
    'return vector of predictions: sum w_i pred_i / sum w_i'
    sum_weighted_predictions = np.array(predictions[0])
    sum_weighted_predictions.fill(0.0)
    for index in xrange(len(weights)):
        sum_weighted_predictions = np.add(
            sum_weighted_predictions,
            np.dot(predictions[index], weights[index]))
    sum_weights = np.sum(np.array(weights))
    result = sum_weighted_predictions / sum_weights
    return result


def check_key_order(d):
    keys = d.keys()
    for index, key1_key2 in enumerate(zip(keys, keys[1:])):
        key1, key2 = key1_key2
        # print index, key1, key2
        mae1 = d[key1].mae
        mae2 = d[key2].mae
        trace_unless(mae1 <= mae2, 'should be non increasing',
                     index=index, mae1=mae1, mae2=mae2,
                     )


# return string describing key features of the model
def short_model_description(model_description):
    # build model decsription
    model = model_description.model
    if model == 'gb':
        description = '%s(%d, %d, %s, %d, %3.2f)' % (
            model,
            model_description.n_months_back,
            model_description.n_estimators,
            model_description.max_features,
            model_description.max_depth,
            model_description.learning_rate,
        )
    elif model == 'rf':
        description = '%s(%d, %d, %s, %d)' % (
            model,
            model_description.n_months_back,
            model_description.n_estimators,
            model_description.max_features,
            model_description.max_depth,
        )
    else:
        assert model == 'en', model_description
        description = '%s(%f, %f)' % (
            model,
            model_description.alpha,
            model_description.l1_ratio,
        )
    return description


# write report files for all K values and validation months for the year 2007
def make_chart_hi(reduction, actuals, median_prices, control):
    'return None'
    def make_dispersion_lines(report=None, tag=None, actuals=None, estimates=None):
        # append lines to report

        def quartile_median(low, hi):
            'return median error of actuals s.t. low <= actuals <= hi, return count of number of values in range'
            mask = np.array(np.logical_and(actuals >= low, actuals <= hi), dtype=bool)
            q_actuals = actuals[mask]
            q_estimates = estimates[mask]
            q_abs_errors = np.abs(q_actuals - q_estimates)
            q_median_error = np.median(q_abs_errors)
            q_median_value = np.percentile(q_actuals, 50)
            return q_median_error, q_median_value, sum(mask)

        actuals_quartiles = np.percentile(actuals, (0, 25, 50, 75, 100))

        report.preformatted_line('\nMedian Error by Price Quartile for %s\n' % tag)
        for q in (0, 1, 2, 3):
            q_median_error, q_median_value, count = quartile_median(
                actuals_quartiles[q] + (0 if q == 0 else 1),
                actuals_quartiles[q + 1] - (1 if q == 3 else 0),
            )
            report.preformatted_line('quartile %d  prices %8.0f to %8.0f  N=%d): median price: %8.0f median error: %8.0f error / price: %6.4f' % (
                q + 1,
                actuals_quartiles[q],
                actuals_quartiles[q + 1],
                count,
                q_median_value,
                q_median_error,
                q_median_error / q_median_value,
                ))

    def median_price(month_str):
        return median_prices[Month(month_str)]

    def mae(actuals, predictions):
        'return named tuple'
        e = errors.errors(actuals, predictions)
        mae_index = 1
        return e[mae_index]

    def chart_h(reduction, k, validation_month):
        'return (Report, oracle_less_best, oracle_less_ensemble)'
        print 'chart_h', k, validation_month
        if k == 2 and False:
            pdb.set_trace()
        h = ChartHReport(k, validation_month, 'exp(-MAE/$100000)', control.column_definitions, control.test)
        query_month = Month(validation_month).increment(1).as_str()
        # write results for each of the k best models in the validation month
        cum_weight = None
        eta = 1.0
        weight_scale = 100000.0  # to get weight < 1
        for index in xrange(k):
            # write detail line for this expert
            expert_key = reduction[validation_month].keys()[index]
            expert_results_validation_month = reduction[validation_month][expert_key]
            expert_results_query_month = reduction[query_month][expert_key]
            h.detail_line(
                description='expert ranked %d: %s' % (index + 1, short_model_description(expert_key)),
                mae_validation=expert_results_validation_month.mae,
                mae_query=expert_results_query_month.mae,
                mare_validation=expert_results_validation_month.mae / median_price(validation_month),
                mare_query=expert_results_query_month.mae / median_price(query_month),
                )
            # computing running ensemble model prediction
            weight = math.exp(- eta * expert_results_validation_month.mae / weight_scale)
            assert weight < 1, (eta, expert_results_validation_month.mae, weight_scale)
            incremental_ensemble_predictions_query = weight * expert_results_query_month.predictions
            incremental_ensemble_predictions_validation = weight * expert_results_validation_month.predictions
            if cum_weight is None:
                cum_ensemble_predictions_query = incremental_ensemble_predictions_query
                cum_ensemble_predictions_validation = incremental_ensemble_predictions_validation
                cum_weight = weight
            else:
                cum_ensemble_predictions_query += incremental_ensemble_predictions_query
                cum_ensemble_predictions_validation += incremental_ensemble_predictions_validation
                cum_weight += weight
        # write detail line for the ensemble
        # pdb.set_trace()
        h.detail_line(
            description=' ',
            )
        if k == 10 and validation_month == '200705' and False:
            print k, validation_month
            pdb.set_trace()
        ensemble_predictions_query = cum_ensemble_predictions_query / cum_weight
        ensemble_predictions_validation = cum_ensemble_predictions_validation / cum_weight
        ensemble_errors_query_mae = mae(actuals[query_month], ensemble_predictions_query)
        ensemble_errors_validation_mae = mae(actuals[validation_month], ensemble_predictions_validation)
        h.detail_line(
            description='ensemble of best %d experts' % k,
            mae_validation=ensemble_errors_validation_mae,
            mae_query=ensemble_errors_query_mae,
            mare_validation=ensemble_errors_validation_mae / median_price(validation_month),
            mare_query=ensemble_errors_query_mae / median_price(query_month),
            )
        # write detail line for the oracle's model
        oracle_key = reduction[query_month].keys()[0]
        oracle_results_validation_month = reduction[validation_month][oracle_key]
        oracle_results_query_month = reduction[query_month][oracle_key]
        h.detail_line(
            description='oracle: %s' % short_model_description(oracle_key),
            mae_validation=oracle_results_validation_month.mae,
            mae_query=oracle_results_query_month.mae,
            mare_validation=oracle_results_validation_month.mae / median_price(validation_month),
            mare_query=oracle_results_query_month.mae / median_price(query_month),
            )
        # report differences from oracle
        best_key = reduction[validation_month].keys()[0]
        best_results_query_month = reduction[query_month][best_key]
        mpquery = median_price(query_month)
        oracle_less_best_query_month = oracle_results_query_month.mae - best_results_query_month.mae
        oracle_less_ensemble_query_month = oracle_results_query_month.mae - ensemble_errors_query_mae
        h.detail_line(
            description=' ',
            )
        h.detail_line(
            description='oracle - expert ranked 1',
            mae_query=oracle_less_best_query_month,
            mare_query=oracle_results_query_month.mae / mpquery - best_results_query_month.mae / mpquery,
            )
        h.detail_line(
            description='oracle - ensemble model',
            mae_query=oracle_less_ensemble_query_month,
            mare_query=oracle_results_query_month.mae / mpquery - ensemble_errors_query_mae / mpquery,
            )
        h.detail_line(
            description=' ',
            )
        h.detail_line(
            description='100*(oracle - expert ranked 1)/oracle',
            mae_query=100 * (oracle_less_best_query_month / oracle_results_query_month.mae),
            )
        h.detail_line(
            description='100*(oracle - ensemble model)/oracle',
            mae_query=100 * (oracle_less_ensemble_query_month / oracle_results_query_month.mae),
            )
        # dispersion of errors relative to prices
        make_dispersion_lines(
            report=h,
            tag='ensemble',
            actuals=actuals[query_month],
            estimates=ensemble_predictions_query,
            )
        return h, oracle_less_best_query_month, oracle_less_ensemble_query_month

    def median_value(value_list):
        sum = 0.0
        for value in value_list:
            sum += value
        return sum / len(value_list)

    def make_hi(reduction):
        'return (dict[(k, validation_month)]Report, Report)'
        # make chart h
        hs = {}
        comparison = {}
        for k in all_k_values():
            for validation_month in control.validation_months:
                h, oracle_less_best, oracle_less_ensemble = chart_h(reduction, k, validation_month)
                hs[(k, validation_month)] = h
                comparison[(k, validation_month)] = (oracle_less_best, oracle_less_ensemble)
        # report I is in inverted order relative to chart h grouped_by
        # make chart i part 1
        i = ChartIReport(control.column_definitions, control.test)
        count = 0
        sum_abs_oracle_less_best = 0
        sum_abs_oracle_less_ensemble = 0
        oracle_less_ensemble_by_k = collections.defaultdict(list)
        for validation_month in control.validation_months:
            for k in all_k_values():
                oracle_less_best, oracle_less_ensemble = comparison[(k, validation_month)]
                i.detail_line(
                    validation_month=validation_month,
                    k=k,
                    oracle_less_best=oracle_less_best,
                    oracle_less_ensemble=oracle_less_ensemble,
                )
                oracle_less_ensemble_by_k[k].append(oracle_less_ensemble)
                count += 1
                sum_abs_oracle_less_best += abs(oracle_less_best)
                sum_abs_oracle_less_ensemble += abs(oracle_less_ensemble)

        # make chart i part 2 (TODO: create separate chart)
        i.append(' ')
        i.append('Median (oracle - ensemble)')
        for k in sorted(oracle_less_ensemble_by_k.keys()):
            value_list = oracle_less_ensemble_by_k[k]
            i.detail_line(
                k=k,
                oracle_less_ensemble=median_value(value_list),
                )
        i.append(' ')
        i.append('median absolute oracle less best    : %f' % (sum_abs_oracle_less_best / count))
        i.append('median absolute oracle less ensemble: %f' % (sum_abs_oracle_less_ensemble / count))
        return hs, i

    def city_hi():
        pdb.set_trace()
        for city in reduction.keys():
            city_reduction = reduction[city]
            hs, i = make_hi(city_reduction)
            # write the reports (the order of writing does not matter)
            for key, report in hs.iteritems():
                k, validation_month = key
                report.write(control.path_h_template % (city, k, validation_month))
            i.write(control.path_out_i)
        return

    control.timer.lap('start chart h')
    if control.arg.locality == 'global':
        hs, i = make_hi(reduction)
        # write the reports (the order of writing does not matter)
        for key, report in hs.iteritems():
            k, validation_month = key
            report.write(control.path_out_h_template % (k, validation_month))
        i.write(control.path_out_i)
        return
    elif control.arg.locality == 'city':
        city_hi()
        return
    else:
        print control.arg.locality
        print 'bad locality'
        pdb.set_trace()


def make_charts_efh(k, reduction, actuals, median_price, control):
    '''Write charts e and f, return median-absolute-relative_regret object'''
    def interesting():
        return k == 5

    def trace_if_interesting():
        if interesting():
            print 'k', k
            pdb.set_trace()
            return True
        else:
            return False

    ensemble_weighting = 'exp(-MAE/100000)'
    mae = {}
    debug = False
    my_validation_months = []
    my_ensemble_mae = []
    my_best_mae = []
    my_price = []
    for validation_month in control.validation_months:
        e = ChartEReport(k, ensemble_weighting, control.column_definitions, control.test)
        h = ChartHReport(k, ensemble_weighting, control.column_definitions, control.test)
        if debug:
            print validation_month
            pdb.set_trace()
        query_month = Month(validation_month).increment(1).as_str()
        if query_month not in reduction:
            control.exceptions.append('%s not in reduction (charts ef)' % query_month)
            print control.exception
            continue
        cum_weighted_predictions = None
        cum_weights = 0
        mae_validation = None
        check_key_order(reduction[validation_month])
        # write lines for the k best individual models
        # accumulate info needed to build the ensemble model
        index0_mae = None
        for index, query_month_key in enumerate(reduction[query_month].keys()):
            # print only k rows
            if index >= k:
                break
            print index, query_month_key
            validation_month_value = reduction[validation_month][query_month_key]
            print query_month
            query_month_value = reduction[query_month][query_month_key]
            if mae_validation is not None and False:  # turn off this test for now
                trace_unless(mae_validation <= validation_month_value.mae,
                             'should be non-decreasing',
                             mae_previous=mae_validation,
                             mae_next=validation_month_value.mae,
                             )
            mae_validation = validation_month_value.mae

            mae_query = query_month_value.mae
            if index == 0:
                index0_mae = mae_query
            eta = 1.0
            weight = math.exp(-eta * (mae_validation / 100000.0))
            e.detail_line(
                validation_month=validation_month,
                model=query_month_key.model,
                n_months_back=query_month_key.n_months_back,
                n_estimators=query_month_key.n_estimators,
                max_features=query_month_key.max_features,
                max_depth=query_month_key.max_depth,
                learning_rate=query_month_key.learning_rate,
                rank=index + 1,
                mae_validation=mae_validation,
                weight=weight,
                mae_query=mae_query,
            )

            h.detail_line(
                validation_month=validation_month,
                model_description=short_model_description(query_month_key),
                mae_validation=mae_validation,
                mae_query=mae_query,
            )
            # need the mae of the ensemble
            # need the actuals and predictions? or is this already computed
            predictions_next = query_month_value.predictions
            if cum_weighted_predictions is None:
                cum_weighted_predictions = weight * predictions_next
            else:
                cum_weighted_predictions += weight * predictions_next
            cum_weights += weight
        # write line comparing the best individual model in the next month
        # to the ensemble model
        trace_if_interesting()
        ensemble_predictions = cum_weighted_predictions / cum_weights
        ensemble_rmse, ensemble_mae, ensemble_ci95_low, ensemble_ci95_high = errors.errors(
            actuals[query_month],
            ensemble_predictions,
        )
        best_key = reduction[query_month].keys()[0]
        best_value = reduction[query_month][best_key]
        e.detail_line(
            validation_month=validation_month,
            mae_ensemble=ensemble_mae,
            model=best_key.model,
            n_months_back=best_key.n_months_back,
            n_estimators=best_key.n_estimators,
            max_features=best_key.max_features,
            max_depth=best_key.max_depth,
            learning_rate=best_key.learning_rate,
        )
        h.detail_line(
            validation_month=validation_month,
            model_description='ensemble',
            mae_query=ensemble_mae,
            )
        my_validation_months.append(validation_month)
        my_ensemble_mae.append(ensemble_mae)
        my_best_mae.append(best_value.mae)

        e.write(control.path_out_e_txt % (k, validation_month))
        mae[validation_month] = Bunch(
            index0=index0_mae,
            ensemble=ensemble_mae,
            best_next_month=best_value.mae,
        )

    my_ensemble_mae = []
    my_best_mae = []
    my_price = []
    for month in my_validation_months:
        my_ensemble_mae.append(mae[month].ensemble)
        my_best_mae.append(mae[month].best_next_month)
        my_price.append(median_price[Month(month)])

    width = 0.35

    fig = plt.figure()
    fig1 = fig.add_subplot(211)
    fig1.bar(
        [x+width for x in range(len(my_validation_months))],
        my_best_mae,
        width,
        color='white',
        )
    fig1.bar(
        range(len(my_validation_months)),
        my_ensemble_mae,
        width,
        color='black',
        )

    plt.ylim(0, 180000)

    labels = my_validation_months
    plt.xticks(
        [x+.4 for x in range(len(my_validation_months))],
        labels,
        rotation=-70,
        size='xx-small',
        )

    plt.ylabel('MAE ($)')
    plt.xlabel('Year-Month')

    white_patch = mpatches.Patch(
        facecolor='white',
        edgecolor='black',
        hatch='',
        lw=1,
        label="MAE of Best Model in Validation Month",
        )
    black_patch = mpatches.Patch(
        facecolor='black',
        edgecolor='black',
        hatch='',
        lw=1,
        label="MAE of Ensemble of " + str(k) + " Best Models in Validation Month",
        )
    plt.legend(handles=[white_patch, black_patch], loc=2)

    fig2 = fig.add_subplot(212)

    fig2.bar(
        [x+width for x in range(len(my_validation_months))],
        [int(m) / int(p) for m, p in zip(my_best_mae, my_price)],
        width,
        color='white',
        )
    fig2.bar(
        range(len(my_validation_months)),
        [int(m) / int(p) for m, p in zip(my_ensemble_mae, my_price)],
        width,
        color='black',
        )
    plt.ylim(0, .5)
    labels = my_validation_months
    plt.xticks(
        [x+.4 for x in range(len(my_validation_months))],
        labels,
        rotation=-70,
        size='xx-small',
        )

    plt.ylabel('Absolute Relative Error')
    plt.xlabel('Year-Month')

    white_patch = mpatches.Patch(
        facecolor='white',
        edgecolor='black',
        hatch='',
        lw=1,
        label="ARE of Best Model in Validation Month",
        )
    black_patch = mpatches.Patch(
        facecolor='black',
        edgecolor='black',
        hatch='',
        lw=1,
        label="ARE of Ensemble of " + str(k) + " Best Models in Validation Month",
        )
    plt.legend(handles=[white_patch, black_patch], loc=2)

    plt.tight_layout(pad=0.8, w_pad=0.8, h_pad=1.0)
    plt.savefig(control.path_out_e_pdf % k)

    plt.close()

    f = ChartFReport(k, ensemble_weighting, control.column_definitions, control.test)
    regrets = []
    relative_errors = []
    for validation_month in control.validation_months:
        query_month = Month(validation_month).increment(1).as_str()
        print query_month
        print "need to define best_next_month  --> best_query_month"
        pdb.set_trace()
        query_month_value = reduction[query_month][query_month_key]
        regret = mae[validation_month].ensemble - mae[validation_month].best_next_month
        regrets.append(regret)
        relative_error = regret / median_price[Month(validation_month)]
        relative_errors.append(relative_error)
        median_price_next = median_price[Month(query_month)]
        f.detail_line(
            validation_month=validation_month,
            mae_index0=mae[validation_month].index0,
            mae_ensemble=mae[validation_month].ensemble,
            mae_best_next_month=mae[validation_month].best_next_month,
            median_price=median_price[Month(validation_month)],
            fraction_median_price_next_month_index0=mae[validation_month].index0 / median_price_next,
            fraction_median_price_next_month_ensemble=mae[validation_month].ensemble / median_price_next,
            fraction_median_price_next_month_best=mae[validation_month].best_next_month / median_price_next,
        )
    median_absolute_regret = np.median(np.abs(regrets))
    median_absolute_relative_regret = np.median(np.abs(relative_errors))
    f.write(control.path_out_f % k)
    return median_absolute_regret, median_absolute_relative_regret


class ChartGReport():
    def __init__(self):
        self.report = Report()
        self.format_header = '%4s %7s'
        self.format_detail = '%4d %6.3f%%'
        self._header()

    def detail(self, k, marr):
        self.report.append(
            self.format_detail % (k, marr * 100.0)
        )

    def _header(self):
        self.report.append('Hyperparameter K')
        self.report.append(' ')
        self.report.append(
            self.format_header % ('K', 'MARR')
        )

    def write(self, path):
        self.report.append('Legend:')
        self.report.append('K: number of models in ensemble')
        self.report.append('MARR: Median Absolute Relative Regret')
        self.report.write(path)

    def append(self, line):
        self.report.append(line)


def all_k_values():
    ks = range(1, 31, 1)
    ks.extend([40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200])
    return ks


def make_charts_efgh(reduction, actuals, median_prices, control):
    # chart g uses the regret values that are computed in building chart e
    debug = True
    g = ChartGReport()
    ks = range(1, 31, 1)
    ks.extend([40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200])
    if control.test:
        ks = (1, 5)
    for k in ks:
        median_absolute_relative_regret = make_charts_efh(k, reduction, actuals, median_prices, control)
        if not debug:
            g.detail(k, median_absolute_relative_regret)
    if not debug:
        g.write(control.path_out_g)


def make_charts(reduction, actuals, median_prices, control):
    print 'making charts'

    make_chart_a(reduction, median_prices, control)
    make_chart_hi(reduction, actuals, median_prices, control)
    return  # charts b - g are obselete
    if control.arg.locality == 'city':
        print 'stopping charts after chart a and h, since locality is', control.arg.locality
        return
    make_chart_b(reduction, control, median_prices)

    make_chart_cd(reduction, median_prices, control, (0,), 'c')
    for n_best in (5, 100):
        report_id = 'd-%0d' % n_best
        for validation_month, month_reduction in reduction.iteritems():
            n_reductions_per_month = len(month_reduction)
            break
        detail_lines_d = range(n_best)[:n_reductions_per_month]
        make_chart_cd(reduction, median_prices, control, detail_lines_d, report_id)
    make_charts_efgh(reduction, actuals, median_prices, control)


def extract_yyyymm(path):
    file_name = path.split('/')[-1]
    base, suffix = file_name.split('.')
    yyyymm = base.split('-')[-1]
    return yyyymm


class ReductionIndex(object):
    'reduction DataFrame multiindex object'
    def __init__(self, city, validation_month, model_description):
        self.city = city
        self.validation_month = validation_month
        self.model_description = model_description

    def __hash__(self):
        return hash((self.city, self.validation_month, self.model_description))

    def __repr__(self):
        pattern = 'ReductionIndex(city=%s, validation_month=%s, model_description=%s)'
        return pattern % (self.city, self.validation_month, self.model_description)


class ReductionValue(object):
    'reduction DataFrame value object'
    def __init__(self, mae, model_results, feature_group):
        self.mae = mae
        self.model_results = model_results
        self.feature_group = feature_group

    def __hash__(self):
        return hash((self.mae, self.model_results, self.feature_group))

    def __repr__(self):
        pattern = 'ReductionValue(mae = %f, model_results=%s, feature_group=%s)'
        return pattern % (self.mae, self.model_results, self.feature_group)


def make_data(control):
    '''return the reduction dict'''

    def path_city(path):
        'return city in path to file'
        last = path.split('/')[-1]
        date, city = last.split('.')[0].split('-')
        return city

    def process_records(path):
        ''' return (dict, actuals, counter) for the path where
        dict has type dict[ModelDescription] ModelResult
        '''
        def make_model_description(key):
            is_en = isinstance(key, ResultKeyEn)
            is_gbr = isinstance(key, ResultKeyGbr)
            is_rfr = isinstance(key, ResultKeyRfr)
            is_tree = is_gbr or is_rfr
            result = ModelDescription(
                model='en' if is_en else ('gb' if is_gbr else 'rf'),
                n_months_back=key.n_months_back,
                units_X=key.units_X if is_en else 'natural',
                units_y=key.units_y if is_en else 'natural',
                alpha=key.alpha if is_en else None,
                l1_ratio=key.l1_ratio if is_en else None,
                n_estimators=key.n_estimators if is_tree else None,
                max_features=key.max_features if is_tree else None,
                max_depth=key.max_depth if is_tree else None,
                loss=key.loss if is_gbr else None,
                learning_rate=key.learning_rate if is_gbr else None,
            )
            return result

        def make_model_result(value):
            rmse, mae, low, high = errors.errors(value.actuals, value.predictions)
            result = ModelResults(
                rmse=rmse,
                mae=mae,
                ci95_low=low,
                ci95_high=high,
                predictions=value.predictions,
            )
            return result

        print 'reducing', path
        model = {}
        counter = collections.Counter()
        input_record_number = 0
        actuals = None
        with open(path, 'rb') as f:
            while True:  # process each record in path
                counter['attempted to read'] += 1
                input_record_number += 1
                try:
                    # model[model_key] = error_analysis, for next model result
                    record = pickle.load(f)
                    counter['actually read'] += 1
                    assert isinstance(record, tuple), type(record)
                    assert len(record) == 2, len(record)
                    key, value = record
                    assert len(value) == 2, len(value)
                    # NOTE: importances is not used
                    valavm_result_value, importances = value
                    # verify that actuals is always the same
                    if actuals is not None:
                        assert np.array_equal(actuals, valavm_result_value.actuals)
                    actuals = valavm_result_value.actuals
                    # verify that each model_key occurs at most once in the validation month
                    model_key = make_model_description(key)
                    if model_key in model:
                        print '++++++++++++++++++++++'
                        print path, model_key
                        print 'duplicate model key'
                        pdb.set_trace()
                        print '++++++++++++++++++++++'
                    model[model_key] = make_model_result(valavm_result_value)
                except ValueError as e:
                    counter['ValueError'] += 1
                    if key is not None:
                        print key
                    print 'ignoring ValueError in record %d: %s' % (input_record_number, e)
                except EOFError:
                    counter['EOFError'] += 1
                    print 'found EOFError path in record %d: %s' % (input_record_number, path)
                    print 'continuing'
                    if input_record_number == 1 and False:
                        # with locality == city, a file can be empty
                        control.errors.append('eof record 1; path = %s' % path)
                    break
                except pickle.UnpicklingError as e:
                    counter['UnpicklingError'] += 1
                    print 'cPickle.Unpicklingerror in record %d: %s' % (input_record_number, e)

        return model, actuals, counter

    reduction = collections.defaultdict(dict)
    all_actuals = collections.defaultdict(dict)
    paths = sorted(glob.glob(control.path_in_valavm))
    assert len(paths) > 0, paths
    counters = {}
    for path in paths:
        model, actuals, counter = process_records(path)
        # type(model) is dict[ModelDescription] ModelResults
        # sort models by increasing ModelResults.mae
        sorted_models = collections.OrderedDict(sorted(model.items(), key=lambda t: t[1].mae))
        check_key_order(sorted_models)
        if control.arg.locality == 'global':
            base_name, suffix = path.split('/')[-1].split('.')
            validation_month = base_name
            reduction[validation_month] = sorted_models
            all_actuals[validation_month] = actuals
        elif control.arg.locality == 'city':
            base_name, suffix = path.split('/')[-1].split('.')
            validation_month, city_name = base_name.split('-')
            #  some file systems create all upper case names
            #  some create mixed-case names
            #  we map each to upper case
            city_name_used = city_name.upper()
            reduction[city_name_used][validation_month] = sorted_models
            all_actuals[city_name_used][validation_month] = actuals
        else:
            print 'unexpected locality', control.arg.locality
            pdb.set_trace()
        counters[path] = counter
        if control.test:
            break

    return reduction, all_actuals, counters


def make_subset_global(reduction, fraction):
    'return a random sample of the reduction stratified by validation_month as an ordereddict'
    # use same keys (models) every validation month
    # generate candidate for common keys in the subset
    subset_common_keys = None
    for validation_month, validation_dict in reduction.iteritems():
        if len(validation_dict) == 0:
            print 'zero length validation dict', validation_month
            pdb.set_trace()
        keys = validation_dict.keys()
        n_to_keep = int(len(keys) * fraction)
        subset_common_keys_list = random.sample(keys, n_to_keep)
        subset_common_keys = set(subset_common_keys_list)
        break

    # remove keys from subset_common_keys that are not in each validation_month
    print 'n candidate common keys', len(subset_common_keys)
    for validation_month, validation_dict in reduction.iteritems():
        print 'make_subset', validation_month
        validation_keys = set(validation_dict.keys())
        for key in subset_common_keys:
            if key not in validation_keys:
                print 'not in', validation_month, ': ', key
                subset_common_keys -= set(key)
    print 'n final common keys', len(subset_common_keys)

    # build reduction subset using the actual common keys
    results = {}
    for validation_month, validation_dict in reduction.iteritems():
        d = {
            common_key: validation_dict[common_key]
            for common_key in subset_common_keys
            }
        # sort by MAE, low to high
        od = collections.OrderedDict(sorted(d.items(), key=lambda x: x[1].mae))
        results[validation_month] = od

        return results


def make_subset_city(reduction, path_interesting_cities):
    'return reduction for just the interesting cities'
    result = {}
    if len(reduction) <= 6:
        return reduction
    with open(path_interesting_cities, 'r') as f:
        lines = f.readlines()
        no_newlines = [line.rstrip('\n') for line in lines]
        for interesting_city in no_newlines:
            if interesting_city in reduction:
                result[interesting_city] = reduction[interesting_city]
            else:
                print 'not in reduction', interesting_city
                pdb.set_trace()
    return result


def make_subset(reduction, fraction, locality, interesting_cities):
    'return dict of type type(reduction) but with a randomly chosen subset of size fraction * len(reduction)'
    if locality == 'global':
        return make_subset_global(reduction, fraction)
    elif locality == 'city':
        return make_subset_city(reduction, interesting_cities)
    else:
        print 'bad locality', locality
        pdb.set_trace()


def make_norwalk(reduction):
    'return dict of type(reduction) with with just the norwalk data items'
    pdb.set_trace()
    city = 'NORWALK'
    result = {city: reduction[city]}
    return result


def make_median_price(path, cities):
    'return dict[Month] median_price or dict[city][Month] median_price'
    def median_price(df, month):
        in_month = df.month == month
        result = df[in_month].price.median()
        return result

    with open(path, 'rb') as f:
        df, reduction_control = pickle.load(f)
        all_months = set(df.month)
        if cities:
            all_cities = set(df.city)
            result = collections.defaultdict(dict)
            for city in all_cities:
                in_city = df.city == city
                result[city] = {month: median_price(df[in_city], month) for month in all_months}
        else:
            result = {month: median_price(df, month) for month in all_months}
    return result


class ReportReduction(object):
    def __init__(self, counters):
        self._report = self._make_report(counters)

    def write(self, path):
        self._report.write(path)

    def _make_report(self, counters):
        r = Report()
        r.append('Records retained while reducing input file')
        for path, counter in counters.iteritems():
            r.append(' ')
            r.append('path %s' % path)
            for tag, value in counter.iteritems():
                r.append('%30s: %d' % (tag, value))
        return r


def main(argv):
    print "what"
    control = make_control(argv)
    sys.stdout = Logger(logfile_path=control.path_out_log)
    print control
    lap = control.timer.lap

    if control.arg.data:
        median_price = make_median_price(control.path_in_chart_01_reduction, control.arg.locality == 'city')
        lap('make_median_price')
        reduction, all_actuals, counters = make_data(control)
        if len(control.errors) > 0:
            print 'stopping because of errors'
            for error in control.errors:
                print error
            pdb.set_trace()
        lap('make_data')
        ReportReduction(counters).write(control.path_out_data_report)
        subset = make_subset(reduction, control.sampling_rate, control.arg.locality, control.path_in_interesting_cities)
        lap('make_subset')
        pdb.set_trace()
        norwalk = make_norwalk(reduction) if control.arg.locality == 'city' else None
        # check key order

        def check_validation_month_keys(reduction):
            for validation_month in reduction.keys():
                check_key_order(reduction[validation_month])

        if control.arg.locality == 'global':
            check_validation_month_keys(reduction)
            check_validation_month_keys(subset)
        else:
            for city in reduction.keys():
                check_validation_month_keys(reduction[city])
            for city in subset.keys():
                check_validation_month_keys(subset[city])
        lap('check key order')

        output_all = (reduction, all_actuals, median_price, control)
        output_samples = (subset, all_actuals, median_price, control)
        output_norwalk = (norwalk, all_actuals, median_price, control)
        lap('check key order')
        with open(control.path_out_data, 'wb') as f:
            pickle.dump(output_all, f)
            lap('write all data')
        with open(control.path_out_data_subset, 'wb') as f:
            pickle.dump(output_samples, f)
            lap('write samples')
        if control.arg.locality == 'city':
            with open(control.path_out_data_norwalk, 'wb') as f:
                pickle.dump(output_norwalk, f)
                lap('write norwalk')
    else:
        with open(control.path_in_data, 'rb') as f:
            print 'reading reduction data file'
            reduction, all_actuals, median_price, reduction_control = pickle.load(f)
            lap('read input from %s' % control.path_in_data)

        # check that the reduction dictionaries are ordered by mae
        def check_order_months(d):
            for validation_month, ordered_dict in d.iteritems():
                check_key_order(ordered_dict)

        if control.arg.locality == 'global':
            check_order_months(reduction)
        elif control.arg.locality == 'city':
            for city, month_dict in reduction.iteritems():
                check_order_months(month_dict)

        make_charts(reduction, all_actuals, median_price, control)

    print control
    if control.test:
        print 'DISCARD OUTPUT: test'
    if control.debug:
        print 'DISCARD OUTPUT: debug'
    if control.arg.subset:
        print 'DISCARD OUTPUT: subset'
    if len(control.errors) != 0:
        print 'DISCARD OUTPUT: ERRORS'
        for error in control.errors:
            print error
    if len(control.exceptions) != 0:
        print 'DISCARD OUTPUT; EXCEPTIONS'
        for exception in control.expections:
            print exception
    print 'done'

    return


if __name__ == '__main__':
    if False:
        # avoid pyflakes warnings
        pdb.set_trace()
        pprint()
        pd.DataFrame()
        np.array()
        AVM()
        ResultValue

    main(sys.argv)
