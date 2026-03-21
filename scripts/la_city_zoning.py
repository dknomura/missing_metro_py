# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
#   kernelspec:
#     display_name: missing-metro-py (3.11.14)
#     language: python
#     name: python3
# ---

# %%
import geopandas as gpd

zoning_df = gpd.read_file('../data/Zoning.kml', driver="KML")

zoning_df

# %%

residential_df = zoning_df
residential_df

# %%
residential_df['density_limit']= residential_df['Zoning'].case_when([
    (residential_df['Zoning'].str.contains('RD1.5'), 43560/1500),
    (residential_df['Zoning'].str.contains('RD2'), 43560/2000),
    (residential_df['Zoning'].str.contains('RD3'), 43560/3000),
    (residential_df['Zoning'].str.contains('RD4'), 43560/4000),
    (residential_df['Zoning'].str.contains('RD5'), 43560/5000),
    (residential_df['Zoning'].str.contains('RD6'), 43560/6000),
    (residential_df['Zoning'].str.contains('RMP'), 43560/20000),
    (residential_df['Zoning'].str.contains('R3'), 43560/800),
    (residential_df['Zoning'].str.contains('RAS3'), 43560/800),
    (residential_df['Zoning'].str.contains('R4'), 43560/400),
    (residential_df['Zoning'].str.contains('RAS4'), 43560/400),
    (residential_df['Zoning'].str.contains('R5'), 43560/200),
    (residential_df['Zoning'].str.contains('RE40'), 43560/40000),
    (residential_df['Zoning'].str.contains('RE20'), 43560/20000),
    (residential_df['Zoning'].str.contains('RE15'), 43560/15000),
    (residential_df['Zoning'].str.contains('RE11'), 43560/11000),
    (residential_df['Zoning'].str.contains('RE9'), 43560/9000),
    (residential_df['Zoning'].str.contains('RS'), 43560/7500),
    (residential_df['Zoning'].str.contains('R1'), 43560/5000),
    (residential_df['Zoning'].str.contains('RU'), 43560/3500),
    (residential_df['Zoning'].str.contains('RZ2.5'), 43560/2500),
    (residential_df['Zoning'].str.contains('RZ3'), 43560/3000),
    (residential_df['Zoning'].str.contains('RZ4'), 43560/4000),
    (residential_df['Zoning'].str.contains('RW1'), 43560/2300),
    (residential_df['Zoning'].str.contains('R2'), 43560/2500),
    (residential_df['Zoning'].str.contains('RW2'), 43560/1150)
])
residential_df


# %%
import requests
import geopandas as gpd
from shapely.geometry import Point
import pandas as pd

# Load station data
STATION_LAYER_URL = "https://services3.arcgis.com/NaFf4UaPo3IgQXqn/ArcGIS/rest/services/Metro_Rail_Lines_Stops/FeatureServer/0/query?where=1%3D1&objectIds=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&resultType=none&distance=0.0&units=esriSRUnit_Meter&outDistance=&relationParam=&returnGeodetic=false&outFields=*&returnGeometry=true&featureEncoding=esriDefault&multipatchOption=xyFootprint&maxAllowableOffset=&geometryPrecision=&outSR=&defaultSR=&datumTransformation=&applyVCSProjection=false&returnIdsOnly=false&returnUniqueIdsOnly=false&returnCountOnly=false&returnExtentOnly=false&returnQueryGeometry=false&returnDistinctValues=false&cacheHint=false&collation=&orderByFields=&groupByFieldsForStatistics=&returnAggIds=false&outStatistics=&having=&resultOffset=&resultRecordCount=&returnZ=false&returnM=false&returnTrueCurves=false&returnExceededLimitFeatures=true&quantizationParameters=&sqlFormat=none&f=pgeojson&token="
stations_gdf = gpd.read_file(STATION_LAYER_URL)



# %%
# Create quarter-mile buffer around stations
# Convert to a projected CRS for accurate distance calculations (feet)
def trim_around_stations(buffer_distance:int) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:

    stations_projected = stations_gdf.to_crs(epsg=2229)  # NAD83 / California zone 5 (feet)
    buffer = stations_projected.buffer(buffer_distance)  

    # Convert buffer back to WGS84 for intersection with zoning data
    buffer_df = gpd.GeoDataFrame(geometry=buffer, crs='EPSG:2229').to_crs(epsg=4326)

    # Filter residential parcels to only include those within the buffer
    # First ensure residential_df is in the same CRS as the buffer
    temp_residential_df:gpd.GeoDataFrame
    temp_residential_df = residential_df.to_crs(epsg=4326)
        

    # Perform spatial intersection to get only parcels within buffer
    residential_in_buffer = gpd.sjoin(temp_residential_df, buffer_df, how='inner', predicate='intersects')
    trim_df = gpd.overlay(residential_in_buffer,buffer_df, how='intersection')
    print(f"Total residential parcels: {len(temp_residential_df)}")
    print(f"Residential parcels within {buffer_distance} feet of stations: {len(residential_in_buffer)}")
    return buffer_df, trim_df

# %%
buffer_200ft_df, trim_200ft_df=trim_around_stations(200)
trim_200ft_df.explore('Zoning')

# %%
buffer_halfmile_df, trim_halfmile_df=trim_around_stations(2640)
trim_halfmile_df.explore('Zoning')

# %%
buffer_qtrmile_df, trim_qtrmile_df=trim_around_stations(1320)
trim_qtrmile_df.explore('Zoning')

# %%
halfmile_donut = gpd.overlay(trim_halfmile_df, buffer_qtrmile_df, how='difference')
halfmile_donut.explore('Zoning')

# %%
qtrmile_donut = gpd.overlay(trim_qtrmile_df, buffer_200ft_df, how='difference')
qtrmile_donut.explore('Zoning')

# %%
trim_200ft_df['dwelling_units_new']= 140*trim_200ft_df.to_crs(epsg=2229).area/43560

qtrmile_donut['dwelling_units_new']= 100*qtrmile_donut.to_crs(epsg=2229).area/43560

halfmile_donut['dwelling_units_new']= 80*halfmile_donut.to_crs(epsg=2229).area/43560

{"200 feet":sum(trim_200ft_df['dwelling_units_new']), "Quarter mile":sum(qtrmile_donut['dwelling_units_new']),"Half mile":sum(halfmile_donut['dwelling_units_new'])}

# %%
residential_around_metro = pd.concat([trim_200ft_df,qtrmile_donut, halfmile_donut])
residential_around_metro['density_limit']=pd.to_numeric(residential_around_metro['density_limit'], errors='coerce').fillna(0)
residential_around_metro['dwelling_units_current']= residential_around_metro['density_limit']*residential_around_metro.to_crs(epsg=2229).area/43560
residential_around_metro


# %%
residential_around_metro = residential_around_metro.to_crs(epsg=4326)
residential_around_metro.to_file('..\data\zoning_around_metro.json', driver='GeoJSON')
