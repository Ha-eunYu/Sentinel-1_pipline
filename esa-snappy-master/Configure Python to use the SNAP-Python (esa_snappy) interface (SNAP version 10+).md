# Configure Python to use the SNAP\-Python \(esa\_snappy\) interface \(SNAP version 10\+\)



### Access to the *esa\_snappy *plugin

The esa\_snappy plugin has been implemented as a dedicated SNAP module. As for the other SNAP modules, the corresponding source code is available from [Github](https://github.com/senbox-org/esa-snappy) .

### Installation of the *esa\_snappy *plugin

The *esa\_snappy* plugin is one of the ‘internal’ SNAP plugins which are automatically installed during the SNAP installation. Thus, no further user action is required. 

**Note:** Due to a technical restriction in the installation procedure of the latest SNAP version 11, the  *esa\_snappy* plugin is not automatically installed. Instead, in SNAP 11 it must be installed like an external plugin via the Plugin Manager in SNAP Desktop:

- Open the Plugin Manager in SNAP Desktop (Tools → Plugins in the main menu bar)
- Select tab ‘Available Plugins’. Among others, the plugin ‘ESA SNAPPY’ appears in the list
- Select ‘ESA SNAPPY’, click ‘Install’, and follow the installation steps as described in the dialogs.
- After restart of SNAP Desktop, ‘ESA SNAPPY’ will be visible in the list of installed plugins.

### Configuration of *esa\_snappy *from the Command Line

With the *esa\_snappy* plugin being installed, open a command line window (shell, terminal window on Unixes, `cmd` on Windows) at the `bin` folder of the SNAP installation directory. Now type

Unix/MacOS:  
`$ ./snappy-conf <python-exe>`

Windows*:*

`$ snappy-conf <python-exe>`

This will generate the Python module *esa\_snappy* configured for the current SNAP installation and your Python interpreter `<python-exe>` into the* *`.snap/snap-python`directory of the user home directory. The parameter `<python-exe>` must be the full path to the Python interpreter executable which you want to use with SNAP. For Windows users, we recommend that the path to the Python interpreter executable should **NOT** contain empty spaces (such as in ‘C:\\Program Files\\…’). The configuration of *esa\_snappy* via GUI during SNAP installation (see below) does not work in this case. Moreover, Python distributions such as Miniconda do not recommend this either because of potential problems. 

Supported Python versions are currently 2.7, 3.3 to 3.10, we recommend to use a fairly recent version. For the next SNAP major release it is planned to support Python versions up to 3.12. 

If you want the *esa\_snappy *module to be placed somewhere else use:

Unix/MacOS:  
`$ ./snappy-conf <python-exe> <esa_snappy-dir>`

Windows*:*

`$ snappy-conf <python-exe> <esa_snappy-dir>`

For example, `<esa_snappy-dir>` could be the ..\\Lib\\site-packages folder of your Python installation. In this case, *esa\_snappy* would be already on your Python path (no further *sys.path.append* … required).

When you see as output something like below, the configuration was successful:

|  |
| --- |
| The command might hang when finished and does not return to the prompt. In this case press CTRL + C and answer the question if you want to abort with no ('n'). |

#### *Known issues and pitfalls*

##### *Configuration fails with empty stack trace*

This issue has been observed while trying to configure *esa\_snappy *on Windows as described above. The output of *snappy-conf* may look like this:

`Configuring ESA SNAP-Python interface...`

`Configuration failed!`

`Error: Python configuration error`

`Full stack trace:`

The reason for this could be that you have permanent environment variables PYTHONHOME and PYTHONPATH set and pointing to a Python installation different to the one which you are trying to use with *esa\_snappy*. If not ultimately needed, we recommend not to use PYTHONHOME and PYTHONPATH. 

The same kind of error (empty stack trace) has been observed by Windows users who installed SNAP 10 in a folder which contains empty spaces (such as in ‘C:\\Program Files\\…’). This issue has been fixed with *esa\_snappy *module update 10.0.1. 

In any case of an empty stack trace, Windows users should have a look at the log files in

 `<user home>\AppData\Roaming\SNAP\var\log`

which may contain further helpful information.

##### *Configuration failed with exit code 30*

This error has been occasionally observed during the *esa\_snappy* installation and Python  
configuration on Linux. Here, the environment variable LD\_LIBRARY\_PATH is likely not set  
correctly, and thus the shared library for the JVM cannot be found. This can be solved by  
performing the following steps:

- `` `locate libjvm.so` ``
- Output is, say, `` `/path/to/libjvm.so` ``
- `` `export LD_LIBRARY_PATH=/path/to/:${LD_LIBRARY_PATH}` ``
- Re-try the installation

##### *Cannot open shared object*

After a successful *esa\_snappy* installation and Python configuration, you might get an error  
similar to

`` `ImportError: libjvm.so: cannot open shared object file: No such file or directory` ``

when doing `` `import jpy` `` within your Python script. Again, the shared library for the JVM cannot be found. This might happen if the LD\_LIBRARY\_PATH has previously been set correctly, but was changed or not set permanently. In this case, set the LD\_LIBRARY\_PATH as described above and restart your Python script.

##### *Configuration on MacOS ARM platforms*

The configuration of *esa\_snappy* may fail on certain MacOS platforms with ARM architecture. The reason is that, depending on the operating system, specific shared libraries for the JVM are not yet available or not suitable. Users who are affected should report their problem in the SNAP forum. In certain cases, a workaround might be found.

### Configuration of *esa\_snappy *during SNAP installation

During the SNAP installation, a dedicated screen for the Python configuration will appear. Follow the instructions given there. Note that at the end of the installation SNAP Desktop must once be opened (by default this is automatically done) to finally activate the Python configuration.

**Note:** This option is not available in the latest SNAP version 11, as the *esa\_snappy* plugin has not yet been installed at this stage (see above). As a SNAP 11 user, please configure *esa\_snappy* from the command line as described above.

### Configuration of *esa\_snappy *from GUI

The option to configure *esa\_snappy *from a graphical interface in SNAP Desktop will be provided in a future SNAP release.

### Testing esa\_snappy

To test *esa\_snappy*,

`$ cd <esa_snappy-dir>`  
`$ <python-exe>`(start your Python interpreter)

Then try the following code:

|  |
| --- |
| `from esa_snappy import ProductIO p = ProductIO.readProduct('esa_snappy/testdata/MER_FRS_L1B_SUBSET.dim') list(p.getBandNames()) ` |

This approach only works if the current working directory is in the `<esa_snappy-dir>`. To generally make use of snappy you need to do one of the following configuration steps.

### Usage of *esa\_snappy *from Python

To effectively use the SNAP Python API from Python, the *esa\_snappy *module must be detectable by your Python interpreter. There are a number of ways to achieve this. 

- To make `esa_snappy`permanently accessible, you could install it into your Python installation. On the command line (shell, terminal window on Unixes, `cmd` on Windows), type

`$ cd <esa-snappy-dir>/esa_snappy`  
`$ <python-exe> setup.py install`This might require root privileges on Unix systems and results in a esa\_*snappy* folder in `usr/local/lib/python/dist-packages/`

- If you encounter any problems with this approach, you can also try to copy the `<esa-snappy-dir>/esa_snappy` directory directly into the site-packages directory of your Python installation.
- Or you could also temporarily or permanently set your `PYTHONPATH` environment variable:

`export PYTHONPATH=$PYTHONPATH:<esa-snappy-dir>`(on Unix OS)  
`set PYTHONPATH=%PYTHONPATH%;<esa-snappy-dir>`    (on Windows OS)

- Finally, you could also append `<esa-snappy-dir>` to the `sys.path` variable in your Python code before importing `esa_snappy`:

|  |
| --- |
| `import sys sys.path.append('<esa-snappy-dir>') # or sys.path.insert(1, '<esa-snappy-dir>') import esa_snappy` |

- In case you seek for a generic solution without needing to set \<snappy-dir\> you may automatically find snappy through the 'USERPROFILE' environment variable. Note that this solution requires esa\_snappy to be located at the value of 'USERPROFILE':

|  |
| --- |
| `import os esa_snappy_envar = 'USERPROFILE' envs = os.environ if not esa_snappy_envar in envs.keys(): 	raise Exception('Can’t find esa_snappy') else: 	esa_snappy_dir = os.path.join(envs.get(esa_snappy_envar), '.snap', 'snap-python') sys.path.append(esa_snappy_dir) import snappy` |


#### Change the Memory Settings

Within `<esa-snappy-dir>/esa_snappy` a file named `esa_snappy.ini` is located. Here you can change how much memory esa\_snappy can use.

Change the line from

\# java\_max\_mem: 8G

to e.g.

`java_max_mem: 10G`

This means that esa\_snappy can use 10GB of your RAM. A recommended value is 70%-80% of the available RAM in your system.
