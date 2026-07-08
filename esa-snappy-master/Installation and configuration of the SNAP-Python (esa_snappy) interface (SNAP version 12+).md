# Installation and configuration of the SNAP\-Python \(esa\_snappy\) interface \(SNAP version 12\+\)

### The SNAP-Python interface *esa\_snappy*

The Python support in SNAP is basically realized by three components, which in combination form the *esa\_snappy* interface:

- A Java module for the configuration of the SNAP - Python interaction. 
- The Java-Python bridge *jpy* that enables calls from Python into a Java virtual machine.  
  and, at the same time, the other way round. This bridge is implemented by the  
  [jpy Project](https://deephaven.io/core/docs/how-to-guides/use-jpy/) and is independent of esa\_snappy.
- A Python package which consists of two parts:
    - the first part provides the integration of *jpy* and configuration and initialization of the Java-Python bridge for usage with SNAP. In SNAP 12+, this part has been updated for using the latest available jpy libraries and now supports Python versions up to 3.13. 
    - the second part (new with SNAP 12) provides extended support for using SNAP functionalities from Python, e.g. running chains of SNAP GPT operators from xml graphs. This part was formerly hosted as *SNAPISTA* by  [Terradue](https://www.terradue.com/) and has now been integrated into the *esa\_snappy* Python package.

The *esa\_snappy* interface has been implemented as a dedicated SNAP module. As for the other SNAP modules, all corresponding source code is available from [Github](https://github.com/senbox-org/esa-snappy). 

### Installation and configuration

The steps required for the installation and configuration of *esa\_snappy* are as follows:

- as first step, make sure that Python has been installed. As said, in SNAP 12+, esa\_snappy now supports Python versions up to **3.13**. In return, the minimum supported version has been raised to **3.9**. Support for lower versions has been dropped because some packages internally used by SNAPISTA are not available in older Python versions.

#### *Selection of the Python distribution*

- **Anaconda/Miniconda**: Python distributions from [Anaconda](https://docs.anaconda.com/anaconda/install/) or [Miniconda](https://docs.anaconda.com/miniconda/install) come with user-friendly installers for all platforms. With these distributions, installation, configuration and usage of the SNAP-Python interface turned out to work smoothly for all supported Python versions. Thus, we***recommend***using Python distributions from Anaconda or Miniconda.
- **‘python.org’**: Python distributions from [python.org](https://www.python.org/) are also available for all platforms. However, binary installers are only provided for Windows and MacOS, whereas on Linux an installation from source is required. Therefore, the installation on Windows and MacOS works smoothly and is a *reasonable alternative* to an Anaconda/Miniconda distribution, just depending on personal preference. On Linux, however, the installation from source is a multi-step procedure, more inconvenient for users and thus not recommended as first choice.  
- **System-wide Python installations**: On the given platform, a system-wide Python installation might be already available. It is ***not recommended*** to use that for the installation, configuration and usage of the SNAP-Python interface. This approach might work, but also may lead into a various issues, in particular related to missing permissions for the installation/configuration steps described below. Also, it must be ensured that *pip *is installed  and works properly, as *pip* is needed to download and install the *esa\_snappy* Python package, see below. (For the Python distributions from Anaconda/Miniconda and [python.org](http://python.org) this is not an issue, as pip is already shipped with them.)

#### *Installation of the Java module for the configuration of the SNAP - Python interaction* 

The *esa\_snappy* plugin is one of the ‘internal’ SNAP plugins which are automatically installed during the SNAP installation. Thus, **no further user action** is required. (A technical restriction in SNAP 11 regarding this part has been solved and is no longer present in SNAP 12+.)

#### *Installation of the esa\_snappy Python package and configuration during SNAP installation* 

During the SNAP installation, a dedicated screen for the Python configuration will appear. Follow the instructions given there. Note that at the end of the installation SNAP Desktop must once be opened (by default this is automatically done) to finally complete and activate the Python configuration.

**New in SNAP 12**: As part of this step, the *esa\_snappy* Python package (configuration + SNAPISTA) mentioned above is automatically downloaded from the [PyPI Package Index](https://pypi.org/project/esa-snappy/) and installed in the ‘site-packages’ folder of your Python installation. This is done by an internal call of pip and may take a little moment. After successful installation, a confirmation dialog appears and the SNAP installation can be continued.

#### *Installation of the esa\_snappy Python package and configuration from the command line* 

If *esa\_snappy *has not been installed and configured during the SNAP installation, this can also be done at a later stage from the command line. Two steps are necessary. Open a command line window (shell, terminal window on Unixes, `cmd` on Windows) at the `bin` folder of the SNAP installation directory:

- Download and installation of the esa\_snappy Python package in the ‘site-packages’ folder of your Python installation:  
`$ </path/to/python-exe> -m pip install esa-snappy`


Here, the path to the Python executable is:

`$ </path/to/python-install-dir>/bin/python`   # Linux/MacOS

`$ </path/to/python-install-dir>/python.exe`   # Windows

In case a Python virtual environment is being used, it would be instead:

`$ </path/to/python-virtual-environment>/bin/python`   # Linux/MacOS

`$ </path/to/python-virtual-environment>/python.exe`   # Windows 

The Python executable can also be identified by typing in a command line window:

`$ which python`   # Linux/MacOS

`$ where python`   # Windows 

 (Note that this might fail if several Python installations exist on the machine, or a Python environment is active which differs from the one to be used with *esa-snappy*. In ideal case, this should be avoided.)


After successful installation, you should see a folder like e.g.:

`$ /home/user_x/miniconda_312/lib/python3.12/site-packages/esa_snappy`   # Linux/MacOS

`$ C:\Users\user_x\miniconda_312\Lib\site-packages\esa_snappy`    # Windows

The installation in the ‘site-packages’ folder ensures that the ‘esa\_snappy’ packages is directly available as any other package in the Python installation. No further *sys.path.append(…) *is required to use *esa\_snappy* in your Python code.

If you are running a system on which you are unsure about the location of your ‘site-packages' folder, you can retrieve it from the following Python command:

`$ </path/to/python-exe> -c "import sysconfig; print(sysconfig.get_paths()['purelib'])"`

- Configuration for SNAP:  
`$ snappy-conf </path/to/python-exe>`

This step executes the script `snappyutil.py` in the *esa\_snappy *installation folder, which unpacks the appropriate jpy tools and binaries, and generates/updates required configuration files. 

When you see as output something like below, the configuration was successful:

The `snappy-conf` command might hang when finished and does not return to the prompt. In this case press CTRL + C and answer the question if you want to abort with no ('n').

#### *Testing esa\_snappy* 

For a quick test of the *esa\_snappy installation*, do  
`$ </path/to/python-exe>`(start your Python interpreter)

Then try the following code:

|  |
| --- |
| `import esa_snappy from esa_snappy import ProductIO` |

No esa\_snappy specific error messages should appear from these statements. (You may see various info and warning messages though, which come from SNAP itself and can usually be ignored at this point.)

#### *Testing SNAPISTA* 

For a quick test of the *SNAPISTA *integration, do again  
`$ </path/to/python-exe>`(start your Python interpreter)

Then try the following code:

|  |
| --- |
| `import esa_snappy import snapista from snapista import Operator, OperatorParams, Graph` |

Again, no *esa\_snappy *specific error messages should appear from these statements. 

#### *Using esa\_snappy and SNAPISTA* 

To get started and to get a deeper knowledge on using *esa\_snappy *and the SNAPISTA integration, there are the following resources:

- Information on how to use the SNAP API from Python can be found here.
- Various example Python scripts which explicitly use the *esa\_snappy* package can be found in `<site-packages-dir>/esa_snappy/examples`
- To get started with SNAPISTA, please refer to the original SNAPISTA [Getting started](https://snap-contrib.github.io/snapista/gettingstarted) page.
- Print versions of example Python notebooks are available which demonstrate how to use SNAPISTA classes [Operator](https://snap-contrib.github.io/snapista/examples/operator), [Graph](https://snap-contrib.github.io/snapista/examples/graph), [BandMaths](https://snap-contrib.github.io/snapista/examples/bandmaths), [Binning](https://snap-contrib.github.io/snapista/examples/binning), and a graph for [SAR calibration](https://snap-contrib.github.io/snapista/examples/sar-calibration).
- In the folder `<site-packages-dir>/esa_snappy/snapista/demo`, two simple, but fully functional notebook example implementations can be found. They use input data from the subfolder`data`, results are also written in there. (Detailed information on how to work with Jupyter notebooks can be found e.g. [here](https://docs.jupyter.org/en/latest/).). 
- A tutorial ‘Earth Observation Processing with SNAP in Python Environments’ has been generated as Jupyter notebook and was demonstrated at ESA Living Planet Symposium 2025. This tutorial contains a dedicated section on SNAPISTA, supplemented by a detailed workflow example. These notebooks are available from the [SNAP-LPS25](https://github.com/bcdev/snap-lps25/tree/main/notebooks/working-area) repository.
- Another set of Jupyter notebooks which use *esa\_snappy* and SNAPISTA in workflows for land and water applications is available from the *esa\_snappy* module hosted on [Github](https://github.com/senbox-org/esa-snappy/tree/master/src/main/resources/jupyter_notebooks). See the [Readme](https://github.com/senbox-org/esa-snappy/blob/master/src/main/resources/jupyter_notebooks/README.md) there for more details.

(Note: The ‘Introduction’ and ‘Installation’ sections of the [original SNAPISTA documentation](https://snap-contrib.github.io/snapista/) are outdated in various aspects and do not match the usage with SNAP 12+ as described in this document.)

#### *Changing the configuration* 

If needed, it is possible any time to switch the configuration to a different Python installation. From the command line, just repeat the two steps above for the other Python:

`$ </path/to/other/python-exe> -m pip install esa-snappy`

`$ snappy-conf </path/to/other/python-exe>`

If, for whatever reason, you do not want to have the *esa\_snappy* package installed in your Python ‘site-packages’ folder, you can also specify a different location. In this case, do from the command line:

`$ </path/to/python-exe> -m pip install --target </path/to/other/location> esa-snappy`

`$ snappy-conf </path/to/python-exe>` `</path/to/other/location>`

Note that in this case you would have to add *sys.path.append(*`</path/to/other/location>`*) *in your  code to make Python know this additional package path..

#### *Changing memory settings*

In your *esa\_snappy* installation folder you can find a configuration file named *esa\_snappy.ini*. In this file you can specify how much memory *esa\_snappy* can use. If needed, just change the entry *java\_max\_mem* to an appropriate value. This value indicates how much of your RAM *esa\_snappy *can use. A recommended value is 70%-80% of the available RAM in your system.

#### *Known issues and pitfalls* 

In SNAP 12, it was tried to eliminate all potential issues with *esa\_snappy *reported earlier for previous SNAP versions. However, this section will be updated frequently, in line with problem reports which will possibly be received from SNAP 12+ users. 

#### *Troubleshooting* 

In case of problems with the steps described above, there are the follwowing options which may help:

- check the outputs in the logfile `snappyutil.log` which can be found in the *esa\_snappy* installation folder
- check the outputs in the SNAP log file `messages.log`. This can be found in

Windows: `<user home dir>\.snap\var\log`, or in `<user home dir>\AppData\Roaming\SNAP\var\log`

Linux/MacOS: `<user home dir>/.snap/system/var/log`

- check the [SNAP forum](https://forum.step.esa.int/) for entries related to SNAP-Python and *esa\_snappy*. If you can’t find any help or hints, feel free to report your specific problem by yourself. You will usually get support in reasonable response time.
