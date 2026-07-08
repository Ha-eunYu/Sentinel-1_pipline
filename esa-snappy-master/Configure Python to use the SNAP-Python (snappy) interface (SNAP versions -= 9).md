# Configure Python to use the SNAP\-Python \(snappy\) interface \(SNAP versions <= 9\)

  

It is suggested to use either Python 3.5 or 3.6. For higher Python version it needs a manual build of jpy ([Readme](https://github.com/jpy-consortium/jpy#readme)).

The easiest way to configure your Python installation for the usage SNAP-Python (snappy) interface is to do it during the installation of SNAP. Within the installer you can simply activate a checkbox and select the path to the python executable.

  


But it is also not a big deal to do it later manually if you might have forgotten it or if you want to configure another Python installation for snappy. Open the command line at the `bin` folder of the SNAP installation directory. On Windows you can simply choose 'SNAP Command-Line' from the Start menu.  
Now type

`$ cd <snap-install-dir>/bin`

Unix:  
`$ ./snappy-conf <python-exe>`

Windows*:*

*`$ snappy-conf <python-exe>`*

  

This will generate the Python module **`snappy`** configured for the current SNAP installation and your Python interpreter `<python-exe>` into the* *`.snap/snap-python`directory of the user home directory. The parameter `<python-exe>` must be the full path to the Python interpreter executable which you want to use with SNAP (supported versions are  2.7, 3.3 to 3.6).  If you want the snappy module to be placed somewhere else use:

Unix:  
`$ ./snappy-conf <python-exe> <snappy-dir>`

Windows*:*

*`$ snappy-conf <python-exe> <snappy-dir>`*

  

Next you can call the tool with the path to the python executable and optionally you can specify a directory where the snappy folder should be created.

When seeing result below the configuration was successful.


The command might hang when finished and does not return to the prompt. In this case press CTRL + C and answer the question if you want to abort with no ('n').

  

To test snappy,

`$ cd <snappy-dir> $ <python-exe>`(start your Python interpreter)

Then try the following code:

```py
from snappy import ProductIO
p = ProductIO.readProduct('snappy/testdata/MER_FRS_L1B_SUBSET.dim')
list(p.getBandNames())
```

This approach only works if the current working directory is in the `<snappy-dir>`. To generally make use of snappy you need to do one of the following configuration steps.

### Configure Python

To effectively use the SNAP Python API from Python, the `snappy` module must be detectable by your Python interpreter. There are a number of ways to achieve this. 

- To make `snappy`permanently accessible, you could install it into your Python installation. On the command line (shell, terminal window on Unixes, `cmd` on Windows), type

`$ cd <snappy-dir>/snappy $ <python-exe> setup.py install`This might require root privileges on Unix systems and results in a *snappy* folder in *`usr/local/lib/python/dist-packages/`*

- If you encounter any problems with this approach, you can also try to copy the `<snappy-dir>/snappy` directory directly into the site-packages directory of your Python installation.
- Or you could also temporarily or permanently set your `PYTHONPATH` environment variable:

`export PYTHONPATH=$PYTHONPATH:<snappy-dir>`(on Unix OS)`set PYTHONPATH=%PYTHONPATH%;<snappy-dir>`    (on Windows OS)

- Finally, you could also append `<snappy-dir>` to the `sys.path` variable in your Python code before importing `snappy`:

```py
import sys
sys.path.append('<snappy-dir>') # or sys.path.insert(1, '<snappy-dir>')
import snappy
```

- In case you seek for a generic solution without needing to set \<snappy-dir\> you may automatically find snappy through the 'USERPROFILE' environment variable. Note that this solution requires snappy to be located at the value of 'USERPROFILE':

```py
import os
snappy_envar = 'USERPROFILE'
envs = os.environ
if not snappy_envar in envs.keys():
	raise Exception('Can’t find snappy')
else:
	snappy_dir = os.path.join(envs.get(snappy_envar), '.snap', 'snap-python')
sys.path.append(snappy_dir)
import snappy
```

  

#### Change the Memory Settings

Within `<snappy-dir>` a file named `snappy.ini` is located. here you can change how much memory snappy can use.

Change the line from

\# java\_max\_mem: 4G

to e.g.

`java_max_mem: 6G`

This means that snappy can use 6GB of your RAM. A recommended value is 70%-80% of the available RAM in your system.
