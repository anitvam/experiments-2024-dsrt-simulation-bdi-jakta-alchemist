import numpy as np
import xarray as xr
import re
from pathlib import Path
import collections

def distance(val, ref):
    return abs(ref - val)
vectDistance = np.vectorize(distance)

def cmap_xmap(function, cmap):
    """ Applies function, on the indices of colormap cmap. Beware, function
    should map the [0, 1] segment to itself, or you are in for surprises.

    See also cmap_xmap.
    """
    cdict = cmap._segmentdata
    function_to_map = lambda x : (function(x[0]), x[1], x[2])
    for key in ('red','green','blue'):
        cdict[key] = map(function_to_map, cdict[key])
#        cdict[key].sort()
#        assert (cdict[key][0]<0 or cdict[key][-1]>1), "Resulting indices extend out of the [0, 1] segment."
    return matplotlib.colors.LinearSegmentedColormap('colormap',cdict,1024)

def getClosest(sortedMatrix, column, val):
    while len(sortedMatrix) > 3:
        half = int(len(sortedMatrix) / 2)
        sortedMatrix = sortedMatrix[-half - 1:] if sortedMatrix[half, column] < val else sortedMatrix[: half + 1]
    if len(sortedMatrix) == 1:
        result = sortedMatrix[0].copy()
        result[column] = val
        return result
    else:
        safecopy = sortedMatrix.copy()
        safecopy[:, column] = vectDistance(safecopy[:, column], val)
        minidx = np.argmin(safecopy[:, column])
        safecopy = safecopy[minidx, :].A1
        safecopy[column] = val
        return safecopy

def convert(column, samples, matrix):
    return np.matrix([getClosest(matrix, column, t) for t in samples])

def valueOrEmptySet(k, d):
    return (d[k] if isinstance(d[k], set) else {d[k]}) if k in d else set()

def mergeDicts(d1, d2):
    """
    Creates a new dictionary whose keys are the union of the keys of two
    dictionaries, and whose values are the union of values.

    Parameters
    ----------
    d1: dict
        dictionary whose values are sets
    d2: dict
        dictionary whose values are sets

    Returns
    -------
    dict
        A dict whose keys are the union of the keys of two dictionaries,
    and whose values are the union of values

    """
    res = {}
    for k in d1.keys() | d2.keys():
        res[k] = valueOrEmptySet(k, d1) | valueOrEmptySet(k, d2)
    return res

def extractCoordinates(filename):
    """
    Scans the header of an Alchemist file in search of the variables.

    Parameters
    ----------
    filename : str
        path to the target file
    mergewith : dict
        a dictionary whose dimensions will be merged with the returned one

    Returns
    -------
    dict
        A dictionary whose keys are strings (coordinate name) and values are
        lists (set of variable values)

    """
    with open(filename, 'r') as file:
#        regex = re.compile(' (?P<varName>[a-zA-Z._-]+) = (?P<varValue>[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?),?')
        regex = r"(?P<varName>[a-zA-Z._-]+) = (?P<varValue>[^,]*),?"
        dataBegin = r"\d"
        is_float = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
        for line in file:
            match = re.findall(regex, line.replace('Infinity', '1e30000'))
            if match:
                return {
                    var : float(value) if re.match(is_float, value)
                        else bool(re.match(r".*?true.*?", value.lower())) if re.match(r".*?(true|false).*?", value.lower())
                        else value
                    for var, value in match
                }
            elif re.match(dataBegin, line[0]):
                return {}

def extractVariableNames(filename):
    """
    Gets the variable names from the Alchemist data files header.

    Parameters
    ----------
    filename : str
        path to the target file

    Returns
    -------
    list of list
        A matrix with the values of the csv file

    """
    with open(filename, 'r') as file:
        dataBegin = re.compile('\d')
        lastHeaderLine = ''
        for line in file:
            if dataBegin.match(line[0]):
                break
            else:
                lastHeaderLine = line
        if lastHeaderLine:
            regex = re.compile(' (?P<varName>\S+)')
            return regex.findall(lastHeaderLine)
        return []

def openCsv(path):
    """
    Converts an Alchemist export file into a list of lists representing the matrix of values.

    Parameters
    ----------
    path : str
        path to the target file

    Returns
    -------
    list of list
        A matrix with the values of the csv file

    """
    regex = re.compile('\d')
    with open(path, 'r') as file:
        lines = filter(lambda x: regex.match(x[0]), file.readlines())
        return [[float(x) for x in line.split()] for line in lines]

def beautifyValue(v):
    """
    Converts an object to a better version for printing, in particular:
        - if the object converts to float, then its float value is used
        - if the object can be rounded to int, then the int value is preferred

    Parameters
    ----------
    v : object
        the object to try to beautify

    Returns
    -------
    object or float or int
        the beautified value
    """
    try:
        v = float(v)
        if v.is_integer():
            return int(v)
        return v
    except:
        return v

if __name__ == '__main__':
    # CONFIGURE SCRIPT
    # Where to find Alchemist data files
    directory = 'data'
    # Where to save charts
    output_directory = 'charts'
    # How to name the summary of the processed data
    pickleOutput = 'data_summary'
    # Experiment prefixes: one per experiment (root of the file name)
    experiments = ['1-exported-data', '2-exported-data', '3-exported-data']
    floatPrecision = '{: 0.3f}'
    # Number of time samples
    timeSamples = 100
    # time management
    minTime = 0
    maxTime = 1500
    timeColumnName = 'time'
    logarithmicTime = False
    # One or more variables are considered random and "flattened"
    seedVars = ['seed']
    # Label mapping
    class Measure:
        def __init__(self, description, unit = None):
            self.__description = description
            self.__unit = unit
        def description(self):
            return self.__description
        def unit(self):
            return '' if self.__unit is None else f'({self.__unit})'
        def derivative(self, new_description = None, new_unit = None):
            def cleanMathMode(s):
                return s[1:-1] if s[0] == '$' and s[-1] == '$' else s
            def deriveString(s):
                return r'$d ' + cleanMathMode(s) + r'/{dt}$'
            def deriveUnit(s):
                return f'${cleanMathMode(s)}' + '/{s}$' if s else None
            result = Measure(
                new_description if new_description else deriveString(self.__description),
                new_unit if new_unit else deriveUnit(self.__unit),
            )
            return result
        def __str__(self):
            return f'{self.description()} {self.unit()}'

    centrality_label = 'H_a(x)'
    def expected(x):
        return r'\mathbf{E}[' + x + ']'
    def stdev_of(x):
        return r'\sigma{}[' + x + ']'
    def mse(x):
        return 'MSE[' + x + ']'
    def cardinality(x):
        return r'\|' + x + r'\|'

    labels = {
        'nodeCount': Measure(r'$n$', 'nodes'),
        'harmonicCentrality[Mean]': Measure(f'${expected("H(x)")}$'),
        'meanNeighbors': Measure(f'${expected(cardinality("N"))}$', 'nodes'),
        'speed': Measure(r'$\|\vec{v}\|$', r'$m/s$'),
        'msqer@harmonicCentrality[Max]': Measure(r'$\max{(' + mse(centrality_label) + ')}$'),
        'msqer@harmonicCentrality[Min]': Measure(r'$\min{(' + mse(centrality_label) + ')}$'),
        'msqer@harmonicCentrality[Mean]': Measure(f'${expected(mse(centrality_label))}$'),
        'msqer@harmonicCentrality[StandardDeviation]': Measure(f'${stdev_of(mse(centrality_label))}$'),
        'org:protelis:tutorial:distanceTo[max]': Measure(r'$m$', 'max distance'),
        'org:protelis:tutorial:distanceTo[mean]': Measure(r'$m$', 'mean distance'),
        'org:protelis:tutorial:distanceTo[min]': Measure(r'$m$', ',min distance'),
    }
    def derivativeOrMeasure(variable_name):
        if variable_name.endswith('dt'):
            return labels.get(variable_name[:-2], Measure(variable_name)).derivative()
        return Measure(variable_name)
    def label_for(variable_name):
        return labels.get(variable_name, derivativeOrMeasure(variable_name)).description()
    def unit_for(variable_name):
        return str(labels.get(variable_name, derivativeOrMeasure(variable_name)))

    # Setup libraries
    np.set_printoptions(formatter={'float': floatPrecision.format})
    # Read the last time the data was processed, reprocess only if new data exists, otherwise just load
    import pickle
    import os
    if os.path.exists(directory):
        newestFileTime = max([os.path.getmtime(directory + '/' + file) for file in os.listdir(directory)], default=0.0)
        try:
            lastTimeProcessed = pickle.load(open('timeprocessed', 'rb'))
        except:
            lastTimeProcessed = -1
        shouldRecompute = not os.path.exists(".skip_data_process") and newestFileTime != lastTimeProcessed
        if not shouldRecompute:
            try:
                means = pickle.load(open(pickleOutput + '_mean', 'rb'))
                stdevs = pickle.load(open(pickleOutput + '_std', 'rb'))
            except:
                shouldRecompute = True
        if shouldRecompute:
            timefun = np.logspace if logarithmicTime else np.linspace
            means = {}
            stdevs = {}
            for experiment in experiments:
                # Collect all files for the experiment of interest
                import fnmatch
                allfiles = filter(lambda file: fnmatch.fnmatch(file, experiment + '_*.csv'), os.listdir(directory))
                allfiles = [directory + '/' + name for name in allfiles]

                allfiles.sort()
                # From the file name, extract the independent variables
                dimensions = {}
                for file in allfiles:
                    dimensions = mergeDicts(dimensions, extractCoordinates(file))
                dimensions = {k: sorted(v) for k, v in dimensions.items()}
                # Add time to the independent variables
                dimensions[timeColumnName] = range(0, timeSamples)
                # Compute the matrix shape
                shape = tuple(len(v) for k, v in dimensions.items())
                # Prepare the Dataset
                dataset = xr.Dataset()
                for k, v in dimensions.items():
                    dataset.coords[k] = v
                if len(allfiles) == 0:
                    print("WARNING: No data for experiment " + experiment)
                    means[experiment] = dataset
                    stdevs[experiment] = xr.Dataset()
                else:
                    varNames = extractVariableNames(allfiles[0])
                    for v in varNames:
                        if v != timeColumnName:
                            novals = np.ndarray(shape)
                            novals.fill(float('nan'))
                            dataset[v] = (dimensions.keys(), novals)
                    # Compute maximum and minimum time, create the resample
                    timeColumn = varNames.index(timeColumnName)
                    allData = { file: np.matrix(openCsv(file)) for file in allfiles }
                    computeMin = minTime is None
                    computeMax = maxTime is None
                    if computeMax:
                        maxTime = float('-inf')
                        for data in allData.values():
                            maxTime = max(maxTime, data[-1, timeColumn])
                    if computeMin:
                        minTime = float('inf')
                        for data in allData.values():
                            minTime = min(minTime, data[0, timeColumn])
                    timeline = timefun(minTime, maxTime, timeSamples)
                    # Resample
                    for file in allData:
    #                    print(file)
                        allData[file] = convert(timeColumn, timeline, allData[file])
                    # Populate the dataset
                    for file, data in allData.items():
                        dataset[timeColumnName] = timeline
                        for idx, v in enumerate(varNames):
                            if v != timeColumnName:
                                darray = dataset[v]
                                experimentVars = extractCoordinates(file)
                                darray.loc[experimentVars] = data[:, idx].A1
                    # Fold the dataset along the seed variables, producing the mean and stdev datasets
                    mergingVariables = [seed for seed in seedVars if seed in dataset.coords]
                    means[experiment] = dataset.mean(dim = mergingVariables, skipna=True)
                    stdevs[experiment] = dataset.std(dim = mergingVariables, skipna=True)
            # Save the datasets
            pickle.dump(means, open(pickleOutput + '_mean', 'wb'), protocol=-1)
            pickle.dump(stdevs, open(pickleOutput + '_std', 'wb'), protocol=-1)
            pickle.dump(newestFileTime, open('timeprocessed', 'wb'))
    else:
        means = { experiment: xr.Dataset() for experiment in experiments }
        stdevs = { experiment: xr.Dataset() for experiment in experiments }

    # QUICK CHARTING

    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.cm as cmx
    matplotlib.rcParams.update({'axes.titlesize': 12})
    matplotlib.rcParams.update({'axes.labelsize': 10})

    def make_line_chart(
        xdata,
        ydata,
        title=None,
        ylabel=None,
        xlabel=None,
        colors=None,
        linewidth=1,
        error_alpha=0.2,
        figure_size=(6, 4)
    ):
        fig = plt.figure(figsize = figure_size)
        ax = fig.add_subplot(1, 1, 1)
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
#        ax.set_ylim(0)
#        ax.set_xlim(min(xdata), max(xdata))
        index = 0
        for (label, (data, error)) in ydata.items():
#            print(f'plotting {data}\nagainst {xdata}')
            lines = ax.plot(xdata, data, label=label, color=colors(index / (len(ydata) - 1)) if colors else None, linewidth=linewidth)
            index += 1
            if error is not None:
                last_color = lines[-1].get_color()
                ax.fill_between(
                    xdata,
                    data+error,
                    data-error,
                    facecolor=last_color,
                    alpha=error_alpha,
                )
        return (fig, ax)
    def generate_all_charts(means, errors = None, basedir=''):
        viable_coords = { coord for coord in means.coords if means[coord].size > 1 }
        for comparison_variable in viable_coords - {timeColumnName}:
            mergeable_variables = viable_coords - {timeColumnName, comparison_variable}
            for current_coordinate in mergeable_variables:
                merge_variables = mergeable_variables - { current_coordinate }
                merge_data_view = means.mean(dim = merge_variables, skipna = True)
                merge_error_view = errors.mean(dim = merge_variables, skipna = True)
                for current_coordinate_value in merge_data_view[current_coordinate].values:
                    beautified_value = beautifyValue(current_coordinate_value)
                    for current_metric in merge_data_view.data_vars:
                        title = f'{label_for(current_metric)} for diverse {label_for(comparison_variable)} when {label_for(current_coordinate)}={beautified_value}'
                        for withErrors in [True, False]:
                            fig, ax = make_line_chart(
                                title = title,
                                xdata = merge_data_view[timeColumnName],
                                xlabel = unit_for(timeColumnName),
                                ylabel = unit_for(current_metric),
                                ydata = {
                                    beautifyValue(label): (
                                        merge_data_view.sel(selector)[current_metric],
                                        merge_error_view.sel(selector)[current_metric] if withErrors else 0
                                    )
                                    for label in merge_data_view[comparison_variable].values
                                    for selector in [{comparison_variable: label, current_coordinate: current_coordinate_value}]
                                },
                            )
                            ax.set_xlim(minTime, maxTime)
                            ax.legend()
                            fig.tight_layout()
                            by_time_output_directory = f'{output_directory}/{basedir}/{comparison_variable}'
                            print(by_time_output_directory)
                            Path(by_time_output_directory).mkdir(parents=True, exist_ok=True)
                            figname = f'{comparison_variable}_{current_metric}_{current_coordinate}_{beautified_value}{"_err" if withErrors else ""}'
                            for symbol in r".[]\/@:":
                                figname = figname.replace(symbol, '_')
                            fig.savefig(f'{by_time_output_directory}/{figname}.pdf')
                            plt.close(fig)

    for experiment in experiments:
        current_experiment_means = means[experiment]
        current_experiment_errors = stdevs[experiment]
        #generate_all_charts(current_experiment_means, current_experiment_errors, basedir = f'{experiment}/all')

# Custom charting
    def custom_subplot(ax, ds, errors, evaluatingColumn, selected_variance, algorithm, color_value):
        evaluatingValues = ds.coords[evaluatingColumn].values
        viridis = plt.colormaps['viridis']
        for idx, x in enumerate(selected_variance):
            dataset = ds.sel(variance=x).to_dataframe()
            errorsDataset = errors.sel(variance=x).to_dataframe()
            sigmaMinus = dataset["error"] - errorsDataset["error"]
            sigmaPlus = dataset["error"] + errorsDataset["error"]
            ax[idx].plot(ds[timeColumnName], dataset['error'], label=algorithm, color=viridis(color_value), linewidth=2.0)
            ax[idx].fill_between(ds[timeColumnName], sigmaMinus, sigmaPlus, color=viridis(color_value), alpha=0.2)
            ax[idx].set_xlabel('Time ($ s $)')
            ax[idx].set_ylim(0, 1900)
            #ax[idx].set_ylabel('Squared Distance Error ($ m^2 $)')
            ax[idx].set_title(f'Relative Drift $ (\\tau) $ = {x}')
            ax[idx].legend()
            ax[idx].margins(x=0)
            
    def baseline_subplot(ax, ds, errors, algorithm, color):
        for i in range(len(ax)):
            ds_df = ds.to_dataframe()
            err_df = errors.to_dataframe()
            sigmaMinus = ds_df["error"] - err_df["error"]
            sigmaPlus = ds_df["error"] + err_df["error"]
            ax[i].plot(ds[timeColumnName], ds_df['error'], label=algorithm, color=color, linestyle='dashed', linewidth=2.0)
            ax[i].fill_between(ds[timeColumnName], sigmaMinus, sigmaPlus, color=color, alpha=0.2)
            ax[i].legend()
            ax[i].margins(x=0)
            
    from matplotlib.gridspec import SubplotSpec
    def create_subtitle(fig: plt.Figure, grid: SubplotSpec, title: str):
        "Sign sets of subplots with title"
        row = fig.add_subplot(grid)
        # the '\n' is important
        row.set_title(f'{title}\n', fontweight='semibold')
        # hide subplot
        row.set_frame_on(False)
        row.axis('off')
                    

    def error_over_time_charts_flattened(means, errors):
        evaluatingColumn = "variance"
        selected_frequencies = [1.0, 2.0]
        selected_variance = [ 0.0, 0.5, 0.7 ]
        fig, axes = plt.subplots(1, len(selected_variance), figsize=(18, 3), sharey=False, layout="constrained")
        #grid = plt.GridSpec(len(selected_frequencies), len(selected_variance))
        axes[0].set_ylabel('Squared Distance Error ($ m^2 $)')
        
        #fig.suptitle('Errors over time', fontweight='bold')
        #create_subtitle(fig, grid[idf, ::], f'Agent Frequency = {f}')            

        custom_subplot(axes, means["1-exported-data"].sel(agentFrequency=1.0), errors["1-exported-data"].sel(agentFrequency=1.0), evaluatingColumn, selected_variance, 'ACLP@1Hz', 0.1)
        custom_subplot(axes, means["1-exported-data"].sel(agentFrequency=2.0), errors["1-exported-data"].sel(agentFrequency=2.0), evaluatingColumn, selected_variance, 'ACLP@2Hz', 0.3)
        custom_subplot(axes, means["2-exported-data"].sel(agentFrequency=1.0), errors["2-exported-data"].sel(agentFrequency=1.0), evaluatingColumn, selected_variance, "ACLI@1Hz", 0.7)
        custom_subplot(axes, means["2-exported-data"].sel(agentFrequency=2.0), errors["2-exported-data"].sel(agentFrequency=2.0), evaluatingColumn, selected_variance, "ACLI@2Hz", 0.9)
        baseline_subplot(axes, means["3-exported-data"], errors["3-exported-data"], "AMA@1Hz", 'k')

        fig.tight_layout()
        Path(f'{output_directory}').mkdir(parents=True, exist_ok=True)
        fig.savefig(f'{output_directory}/error_over_time_flattened.pdf')
   
    def variance_subplot(data, err, ax, values, algorithm, color):
        viridis = plt.colormaps['viridis']
        for idx, x in enumerate(values):
            dataset = data.sel(agentFrequency=x).to_dataframe()
            errorsDataset = err.sel(agentFrequency=x).to_dataframe()
            sigmaMinus = dataset["error"] - errorsDataset["error"]
            sigmaPlus = dataset["error"] + errorsDataset["error"]
            ax[idx].plot(data["variance"], dataset['error'], label=f'{algorithm}@{int(x)}Hz', color=viridis(color), linewidth=2.0)
            ax[idx].fill_between(data['variance'], sigmaMinus, sigmaPlus, color=viridis(color), alpha=0.2)
            ax[idx].set_xlabel('Relative Drift ($ \\tau $)')
            ax[idx].legend()
            ax[idx].set_ylim(200, 1400)
            ax[idx].margins(x=0)
            
    def variance_baseline_subplot(x, err, ax, values, algorithm, color):
        for i in range(len(ax)):
            ds_df = x.to_dataframe()
            err_df = err.to_dataframe()
            sigmaMinus = ds_df["error"] - err_df["error"]
            sigmaPlus = ds_df["error"] + err_df["error"]
            ax[i].axhline(ds_df['error'].item(), label=algorithm, color=color, linestyle='dashed', linewidth=2.0)
            ax[i].fill_between(values, sigmaMinus, sigmaPlus, color=color, alpha=0.2)
            ax[i].legend()

    def error_over_variance(means, stdevs):
        experiments = ["1-exported-data", "2-exported-data", "3-exported-data"]
        colors = ["0.8", "0.2", "k"]
        # selected_frequencies = means["1-exported-data"]['agentFrequency']
        selected_frequencies = [1.0, 2.0, 4.0]
        selected_variance = means["1-exported-data"]['variance']
        fig, axes = plt.subplots(1, len(selected_frequencies), figsize=(18, 3), sharey=False, layout="constrained")
        axes[0].set_ylabel('Squared Distance Error ($ m^2 $)')
        variance_subplot(means['1-exported-data'].mean(dim='time'), stdevs['1-exported-data'].mean(dim='time'), axes, selected_frequencies, 'ACLP', 0.1)
        variance_subplot(means["2-exported-data"].mean(dim='time'), stdevs["2-exported-data"].mean(dim="time"), axes, selected_frequencies, 'ACLI', 0.7)
        variance_baseline_subplot(means["3-exported-data"].mean(dim='time'), stdevs["3-exported-data"].mean(dim='time'), axes, selected_variance, "AMA@1Hz", 'k')
        fig.tight_layout()
        Path(f'{output_directory}').mkdir(parents=True, exist_ok=True)
        fig.savefig(f'{output_directory}/error_over_variances.pdf')

    # Create plots

    error_over_time_charts_flattened(means, stdevs)
    error_over_variance(means, stdevs)
