# National Agriculture Imagery Program (NAIP) Data Dictionary

The Data Dictionaries are a set of information describing the contents, format, and structure of elements for EarthExplorer products.

## Acquisition Date

Field Definition: The year, month, and day the image was acquired.

Format: YYYY/MM/DD

- YYYY = Year
- MM = Month
- DD = Day

## Agency

Field Definition: NAIP is administered by the United States Department of Agriculture (USDA).

## Coordinates - Decimal Degrees

Field Definition: The latitude and longitude are provided in decimal degrees for the following fields:

- Scene Center Latitude and Longitude
- Northeast (NE) Corner Latitude and Longitude
- Northwest (NW) Corner Latitude and Longitude
- Southeast (SE) Corner Latitude and Longitude
- Southwest (SW) Corner Latitude and Longitude

Latitude Format Decimal Degrees: -90.000 through 90.000

Longitude Format Decimal Degrees: -180.000 through 180.000

Number of decimal places will vary by dataset – check collection in EE.

## Coordinates - Degrees, Minutes, Seconds

Field Definition: The latitude and longitude are provided in degrees, minutes, and seconds for the following fields:

- Scene Center Latitude and Longitude
- Northeast (NE) Corner Latitude and Longitude
- Northwest (NW) Corner Latitude and Longitude
- Southeast (SE) Corner Latitude and Longitude
- Southwest (SW) Corner Latitude and Longitude

Longitude Format: DDDMMSS.SSH

- DDD = Degree(s) with a range of 0 through 180
- MM = Minute(s) with a range of 0 through 59
- SS.SS = Second(s) with a range of 0 through 59.99
- H = Hemisphere with E for east and W for west

Latitude Format: DDMMSS.SSH

- DD = Degree(s) with a range of 0 through 90
- MM = Minutes(s) with a range of 0 through 59
- SS.SS = Second(s) with a range of 0 through 59.99
- H = Hemisphere with N for north and S for south

## Date Entered

Field Definition: The date when an image appears in inventory.

## Datum

Field Definition: Datum used to map the image.

- NAD83 = North American Datum 1983
- WGS84 = World Geodetic System 1984

## Entity ID

Field Definition: The naming convention of each file is based on image parameters.

Format: S_DDdddQQ_qq_ZZ_R_YYYYMMDD_yyyymmdd

- S = Sensor Type
- DDddd = SE Reference point of 1 Degree Block (Latitude = DD, Longitude = ddd)
- QQ = Quad location (range 1 -64)
- qq = Quadrant indicator (NE, NW, SE, SW)
- ZZ = UTM Zone*
- R = Resolution in meters
- YYYYMMDD = Acquisition date (year, month, day)
- yyyymmdd = Date NAIP JPG2000 data was created (year, month, day)

*Note: JPG files created in 2013 or later use the UTM zone associated with the uncompressed data available through USDA-FSA-APFO.

Example: M_3211418_NW_11_1_20120423_20120627

## Map Projection

Field Definition: The map projection used to portray the surface of the earth on a flat surface.

- UTM
- WGS 1984 Web Mercator Auxiliary Sphere

## Number of Bands

Field Definition: The number of spectral bands contained in the image.

## Project Name

Field Definition: A unique name given to a set of images that identifies the project.

Format: YYYYMM_STATE_NAIP_1X0000M_UTM_SSSS

- YYYYMM = Acquisition year,and month
- STATE = State
- NAIP = Dataset
- 1X0000 = Resolution where X represents a decimal point
- M = Units (meters)
- UTM = Projection
- SSSS = Sensor Type

Example: 201207_RHODE_ISLAND_NAIP_1X0000M_UTM_CNIR

## Projection Zone

Field Definition: The zone associated with the map projection.

- UTM Zone
- NA = Not Applicable

## Resolution

Field Definition: The distance on the ground represented by one pixel.

## Sensor

Field Definition: The type of camera used to acquire the imagery.

## Sensor Type

Field Definition: The type of imagery acquired by the sensor.

- CNIR = Color Near Infrared (CNIR)
- CLR = Natural Color (CLR)
- CIR = Color Infrared (CIR)

## State

Field Definition: The State contained in the product. NAIP imagery is acquired in the continental U.S.

## Units

Field Definition: The unit of measurement associated with the resolution.

- Meters

## Vendor

Field Definition: The organization or company that acquired the imagery. If a vendor is not listed in the original metadata, credit is given to the USDA’s Farm Service Agency (FSA) Aerial Photography Field Office (APFO).

## JP2000 Available

Field Definition: The format of imagery available.

- Yes = Results return GeoTIFF and JPG2000 images (Default)
- No = Results only return GeoTIFF images
