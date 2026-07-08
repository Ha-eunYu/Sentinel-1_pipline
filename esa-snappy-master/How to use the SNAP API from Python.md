# How to use the SNAP API from Python

This page provides an introduction to use the SNAP Java API from Python.


# Introduction

SNAP implementation language is Java and therefore SNAP's "native" API is a Java API. According to the SNAP architecture, the reference [SNAP Java API documentation](http://step.esa.int/main/developers/) of the two SNAP sub-systems SNAP Engine and SNAP Desktop nearly fully applies to use from Python as well.

With the recommended [standard Python](https://www.python.org/) (CPython) approach, it is possible to **call SNAP code from your Python programs/scripts** and to **extend SNAP by plugins written in Python**. Use this approach if

- you require using the Python scientific extension libraries such as [*numpy*](http://www.numpy.org/), *scipy*, *matplotlib*, etc.;
- you already have CPython code and you want to incorporate SNAP functions;
- you plan to implement a fast data processor plugin in Python;
- you do not plan to develop SNAP Desktop user interface extensions;
- you do not require full portability on all platforms;
- your code has (or will have) dependencies on a lot of non-standard libraries.

With the standard Python approach extension of SNAP is currently limited to raster data processor (`Operator`) plugins. You need to use a [standard Python](https://www.python.org/) (CPython) interpreter installed on your computer (SNAP does not include a CPython interpreter.) For the recent SNAP versions, the supported versions are Python 3.6 to 3.10 for SNAP 11 and will be 3.6 to 3.10 for the upcoming SNAP 12, both for 64-bit (Linux + Darwin) and both 32-bit and 64-bit (Windows).

Please note that you must use a 32-bit Python if your SNAP installation is 32-bit and accordingly use a 64-bit Python if your SNAP installation is 64-bit.

# The esa\_`snappy` Plugin

**Note:** The following examples assume that you work with **SNAP 10+ and the new *esa\_snappy *interface**. Differences to the previous *snappy* interface are outlined in the text or in comment lines in the Python code snippets.

For SNAP 10+, *esa\_snappy* is provided as built-in plugin which allows you to access the SNAP Java API from Python.

## Access, Installation and Configuration

For a guideline how to access, install and configure Python for SNAP please see [Configure Python to use the new SNAP-Python (esa\_snappy) interface (SNAP version 10+)](https://senbox.atlassian.net/wiki/spaces/SNAP/pages/2499051521/Configure+Python+to+use+the+new+SNAP-Python+esa+snappy+interface+SNAP+version+10) for the most recent SNAP 10+ versions, or Configure Python to use the SNAP-Python (snappy) interface (SNAP versions \<= 9) for older SNAP versions. A documentation update describing recent changes is in preparation and will be published here along with the release of SNAP 12. 

## Examples of SNAP API usage from Python

The following first example reads some raster data and displays/stores raster data as an RGB image:

```py
from esa_snappy import ProductIO  # package to be imported is now esa_snappy instead of snappy
import numpy as np
import matplotlib.pyplot as plt

p = ProductIO.readProduct('esa_snappy/testdata/MER_FRS_L1B_SUBSET.dim')  # package folder is now esa_snappy instead of snappy
rad13 = p.getBand('radiance_13')
w = rad13.getRasterWidth()
h = rad13.getRasterHeight()
rad13_data = np.zeros(w * h, np.float32)
rad13.readPixels(0, 0, w, h, rad13_data)
p.dispose()
rad13_data.shape = h, w
imgplot = plt.imshow(rad13_data)
imgplot.write_png('radiance_13.png')
```

#### **Data IO**** **

Due to numerous writers implemented in the SNAP Engine reading and writing data in *esa\_snappy* is relatively simple. The general syntax is: 

```py
from esa_snappy import ProductIO  # package to be imported is now esa_snappy instead of snappy

p = ProductIO.readProduct('esa_snappy/testdata/MER_FRS_L1B_SUBSET.dim') # read product  # package folder is now esa_snappy instead of snappy
ProductIO.writeProduct(p, '<your/out/directory>', '<write format>') # write product

```

#### Get and Set

It makes sense to start exploring the capabilities of *esa\_snappy* by reading a product and try out the methods and fields it contains. Calling get on an object in *esa\_snappy* (e.g. `p.getRasterHeight()`) returns either an Integer or String value or an object. Upon the latter, you can again normally call get again. This might again return an object with fields to return.  
In the other direction, you may also set fields. For instance, if you called get and received a String value, you may set the same field of this object with a String.

```py
rad13 = p.getBand('radiance_13')
rad13.setBandName('just_a_test')
```

Sometimes you might only be interested in “copying” a field from one object to another, let’s say from a source band to a target band. Then you may simply call get and set in one line without interacting with the return of get:

```py
target_band = target_product.getBand('some_output_band_based_on_rad13')
target_band.setNoDataValue(rad13.getNoDataValue()) # no data value from the source Band object rad13
```

Often, *esa\_snappy* returns Integers (e.g. p.getSceneRasterWidth()) or Strings (e.g. p.getName()):

```py
name = p.getName()
width = p.getSceneRasterWidth()
band_names = p.getBandNames()
```

However, you might sometimes walk into Java objects that appear foreign to a Python user. These can e.g. be objects such as the return of:

```py
p.getBandNames()
>>>[Ljava.lang.String;(objectRef=0x00000000391DEAE8)
```

In this case, you simply convert this to a Python list by calling:

```py
bands = list(p.getBandNames())
bands
>>> ['Oa01_reflectance', 'Oa02_reflectance', 'Oa03_reflectance', 'Oa04_reflectance']
type(bands)
>>> <class 'list'>
```

In other cases, using str()converts a Java String to a Python String. For instance, you might be interested in the ‘autogrouping’ of the product. It defines how the bands are grouped in the product. The return of:

```py
p.getAutoGrouping() 
>>> org.esa.snap.core.datamodel.Product$AutoGrouping(objectRef=0x00000000391DEAC8) 
```

This can be easily converted to a Python String:

```py
autogrouping = str(p.getAutoGrouping())
autogrouping
>>> 'Oa*_reflectance:Oa*_reflectance_err:A865:ADG:CHL:IWV:KD490:PAR:T865:TSM:atmospheric_temperature_profile:lambda0:FWHM:solar_flux'
type(autogrouping)
>>> <class 'str'>
```

You may set the value by:

```py
p.setAutoGrouping('<a String correctly formatted to be recognized as autogrouping>')
```

  

#### **Processing in *esa\_snappy***

Snappy generally offers to ways how to process data:

**Option A** is suited when you aim at using only SNAP Engine Operators.

**Option B** is suited when you aim at doing custom computations for which you need to read data into Python numpy arrays.

Both options can, of course, occur in one workflow.

****Option A: Process a product using a SNAP Engine Operator and write the target product ****

SNAP Operators are available in snappy via `GPF.createProduct()`. Its first parameter is a String denoting the name of the Operator as denoted in the Engine and available via GPT. If you have added GPT to your environment variables, you may call GPT from cmd in order to check out the available Operators, their description and parameters. In snappy, we provide the parameters through the second parameter of `GPF.createProduct()`. This parameter is a Java Hashmap, an object that is equivalent to a Python dictionary. The parameters must be named exactly with the String parameter name provided in GPT.

```py
# 1. Imports

from esa_snappy import ProductIO  # package to be imported is now esa_snappy instead of snappy
from esa_snappy import GPF
from esa_snappy import Hashmap

# 2. Fill parameter Hashmap

parameters = Hashmap()
parameters.put('targetResolution', '10')
parameters.put('referenceBand', 'B4')

# 3. Call Operator

operator_name = 'Resample'
target_product = GPF.createProduct(operator_name, parameters, p)

# 4. Write Product
# Write target Product with ProductIO:

write_format = 'BEAM-DIMAP' # in this case write as BEAM-DIMAP
ProductIO.writeProduct(target_product , <'your/out/directory'>, write_format)

# Alternative solution: Computations are faster when using GPF to write the product instead of ProductIO:
incremental = false # most writer don't support the incremental writing mode (update exsiting file), except BEAM-DIMAP.
GPF.writeProduct(target_product , File(<'your/out/directory'>), write_format, incremental, ProgressMonitor.NULL)

```

Instead of the NULL progress monitor, you can use a different monitor if you like to receive progress messages on the command line.

```py
def createProgressMonitor():
    PWPM = jpy.get_type('com.bc.ceres.core.PrintWriterProgressMonitor')
    JavaSystem = jpy.get_type('java.lang.System')
    monitor = PWPM(JavaSystem.out)
    return monitor

pm = createProgressMonitor() 
GPF.writeProduct(target_product , File(<'your/out/directory'>), write_format, incremental, pm)
```

  

In this way, Python can be used to extend SNAP by new raster data processor plugins, i.e. *operators*. As said, operators can be executed from the command-line, or invoked from the SNAP Desktop GUI, and be used as nodes in processing XML graphs.A more comprehensive guideline how to set up such plugins can be found at [What to consider when writing an Operator in Python](https://senbox.atlassian.net/wiki/spaces/SNAP/pages/42041346/What+to+consider+when+writing+an+Operator+in+Python).

  

**Option B: Process a product using custom data computations in Python**

Using an implemented Operator might not be enough in cases where you aim to implement your own computation. The methods `readPixels()` and `writePixels()` help you to retrieve the necessary for the computation and save the result. We recommend to completely set up your target product in your script before computation starts. As in the examples above, p is still our source Product.

```py
# 1. Imports

import esa_snappy  # package to be imported is now esa_snappy instead of snappy
from esa_snappy import ProductUtils

width = p.getSceneRasterWidth() # often the target product dimensions are the same as the source product dimensions
height = p.getSceneRasterHeight()
target_product = esa_snappy.Product('My target product', 'The type of my target product', width, height)

# 2. Optional: Copy or set meta information

ProductUtils.copyMetadata(p, target_product)

# It is also possible to target specific fields. Just one example:
target_product.setDescription('Product containing very valuable output bands')

# 3. Set product writer
# Set the writer with the write_format defined above (here: 'BEAM-DIMAP'):

target_product.setProductWriter(ProductIO.getProductWriter(write_format))

# 4. Add and configure target Bands
# Now, you could copy bands form the source product if you are interested in writing them to the target product as well. Check out ProductUtils.copyBand() regarding this task.
# Before starting our computations, we must create the computed bands of our target Product:

band_name = 'an_output_band_name'
target_band = target_product.addBand(band_name, snappy.ProductData.TYPE_FLOAT32)

# further configure the created band:
nodata_value = p.getBand(<'source_band_name'>).getNoDataValue()
target_band.setNoDataValue(nodata_value)
target_band.setNoDataValueUsed(True)
target_band.setWavelength(425.0)

# You could set values of other fields, some might be important for creating an output suiting your expectations.

# 5. Write header
# All the structure and meta information we just added to the target_product are still in memory. Hence, we must write its header before writing data. The single argument of writeHeader() is 
# the absolute path to the expected product without file extension. 
# The last String of this path is the target Product name as it is being written.

target_product.writeHeader(<'your/out/directory/product_name'>)

```

The target Product is ready for data to be written to it. Check out the [esa\_snappy examples](https://github.com/senbox-org/esa-snappy/tree/master/src/main/resources/esa_snappy/esa_snappy/examples) in order to know how to use `readPixels()` and `writePixels()` for reading data tiles, rows, columns or single pixels into numpy arrays and write them from output arrays into the respective band of the target Product. These same examples are also provided in the *esa\_snappy* installation directory (see below).

It is worth to note that the order of the parameters width and height is switched from what Python users are familiar with from packages like numpy.  
After having created the target product we could now adjust its metadata, e.g. by copying it from the source product using ProductUtils. This is an optional step.

  

**Further code examples**

More example code of how to use the SNAP API in Python can be found in `<esa_snappy-dir>/examples`. There is also a directory `<esa_snappy-dir>/testdata` with a single EO test data product (`*.dim`) in it which you can pass as argument to the various examples. Please try

`$ cd <esa_snappy-dir>/examples $ <python-exe> snappy_ndvi.py ../testdata/MER_FRS_L1B_SUBSET.dim`

  

**Import of Java API classes**
Note that the one and only reference for the SNAP Python API is the [SNAP Java API documentation](http://step.esa.int/main/developers/). All Java classes from the API can be "imported" by the [jpy Java-Python bridge](https://github.com/jpy-consortium/jpy)  which is implicitely used by *esa\_snappy*. For example: `ProductIOPlugInManager = esa_snappy.jpy.get_type('org.esa.snap.framework.dataio.ProductIOPlugInManager')``plugins = ProductIOPlugInManager.getInstance().getAllReaderPlugIns()` However, the most frequently used Java API classes are already imported by default and do not require another explicit call of `get_type(..)`: 

#### *Frequently used classes & interfaces from JRE*

- `String = jpy.get_type('java.lang.String')`
- `File = jpy.get_type('java.io.File')`
- `Point = jpy.get_type('java.awt.Point')`
- `Rectangle = jpy.get_type('java.awt.Rectangle')`
- `Arrays = jpy.get_type('java.util.Arrays')`
- `Collections = jpy.get_type('java.util.Collections')`
- `List = jpy.get_type('java.util.List')`
- `Map = jpy.get_type('java.util.Map')`
- `Set = jpy.get_type('java.util.Set')`
- `ArrayList = jpy.get_type('java.util.ArrayList')`
- `HashMap = jpy.get_type('java.util.HashMap')`
- `HashSet = jpy.get_type('java.util.HashSet')`

#### *Frequently used classes & interfaces from SNAP Engine*

*Product tree & associates:*

- `Product = jpy.get_type('org.esa.snap.core.datamodel.Product')`
- `VectorDataNode = jpy.get_type('org.esa.snap.core.datamodel.VectorDataNode')`
- `RasterDataNode = jpy.get_type('org.esa.snap.core.datamodel.RasterDataNode')`
- `TiePointGrid = jpy.get_type('org.esa.snap.core.datamodel.TiePointGrid')`
- `AbstractBand = jpy.get_type('org.esa.snap.core.datamodel.AbstractBand')`
- `Band = jpy.get_type('org.esa.snap.core.datamodel.Band')`
- `VirtualBand = jpy.get_type('org.esa.snap.core.datamodel.VirtualBand')`
- `Mask = jpy.get_type('org.esa.snap.core.datamodel.Mask')`
- `GeneralFilterBand = jpy.get_type('org.esa.snap.core.datamodel.GeneralFilterBand')`
- `ConvolutionFilterBand = jpy.get_type('org.esa.snap.core.datamodel.ConvolutionFilterBand')`

*Product tree associates:*

- `ProductData = jpy.get_type('org.esa.snap.core.datamodel.ProductData')`
- `GeoCoding = jpy.get_type('org.esa.snap.core.datamodel.GeoCoding')`
- `TiePointGeoCoding = jpy.get_type('org.esa.snap.core.datamodel.TiePointGeoCoding')`
- `PixelGeoCoding = jpy.get_type('org.esa.snap.core.datamodel.PixelGeoCoding')`
- `PixelGeoCoding2 = jpy.get_type('org.esa.snap.core.datamodel.PixelGeoCoding2')`
- `CrsGeoCoding = jpy.get_type('org.esa.snap.core.datamodel.CrsGeoCoding')`
- `GeoPos = jpy.get_type('org.esa.snap.core.datamodel.GeoPos')`
- `PixelPos = jpy.get_type('org.esa.snap.core.datamodel.PixelPos')`
- `FlagCoding = jpy.get_type('org.esa.snap.core.datamodel.FlagCoding')`
- `ProductNodeGroup = jpy.get_type('org.esa.snap.core.datamodel.ProductNodeGroup')`

*Graph Processing Framework:*

- `GPF = jpy.get_type('org.esa.snap.core.gpf.GPF')`
- `Operator = jpy.get_type('org.esa.snap.core.gpf.Operator')`
- `Tile = jpy.get_type('org.esa.snap.core.gpf.Tile')`

*Utilities:*

- `EngineConfig = jpy.get_type('org.esa.snap.runtime.EngineConfig')`
- `Engine = jpy.get_type('org.esa.snap.runtime.Engine')`
- `SystemUtils = jpy.get_type('org.esa.snap.core.util.SystemUtils')`
- `ProductIO = jpy.get_type('org.esa.snap.core.dataio.ProductIO')`
- `ProductUtils = jpy.get_type('org.esa.snap.core.util.ProductUtils')`
- `GeoUtils = jpy.get_type('org.esa.snap.core.util.GeoUtils')`
- `ProgressMonitor = jpy.get_type('com.bc.ceres.core.ProgressMonitor')`
- `PlainFeatureFactory = jpy.get_type('org.esa.snap.core.datamodel.PlainFeatureFactory')`
- `FeatureUtils = jpy.get_type('org.esa.snap.core.util.FeatureUtils')`

*GeoTools:*

- `DefaultGeographicCRS = jpy.get_type('org.geotools.referencing.crs.DefaultGeographicCRS')`
- `ListFeatureCollection = jpy.get_type('org.geotools.data.collection.ListFeatureCollection')`
- `SimpleFeatureBuilder = jpy.get_type('org.geotools.feature.simple.SimpleFeatureBuilder')`

*JTS:*

- `Geometry = jpy.get_type('org.locationtech.jts.geom.Geometry')`
- `WKTReader = jpy.get_type('org.locationtech.jts.io.WKTReader')`
