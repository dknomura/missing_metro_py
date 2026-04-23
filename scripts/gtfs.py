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
import folium
import requests
import geopandas as gpd
import pandas as pd
# %%
# CITY_BOUNDARIES_URL = "https://services3.arcgis.com/NaFf4UaPo3IgQXqn/ArcGIS/rest/services/California_Cities_and_Identifiers_Blue_Version_view_1826470044727749789/FeatureServer/0/query?where=1%3D1&objectIds=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&resultType=none&distance=0.0&units=esriSRUnit_Meter&outDistance=&relationParam=&returnGeodetic=false&outFields=*&returnGeometry=true&returnCentroid=false&returnEnvelope=false&featureEncoding=esriDefault&multipatchOption=xyFootprint&maxAllowableOffset=&geometryPrecision=&outSR=&defaultSR=&datumTransformation=&applyVCSProjection=false&returnIdsOnly=false&returnUniqueIdsOnly=false&returnCountOnly=false&returnExtentOnly=false&returnQueryGeometry=false&returnDistinctValues=false&cacheHint=false&collation=&orderByFields=&groupByFieldsForStatistics=&returnAggIds=false&outStatistics=&having=&resultOffset=&resultRecordCount=&returnZ=false&returnM=false&returnTrueCurves=false&returnExceededLimitFeatures=true&quantizationParameters=&sqlFormat=none&f=pgeojson&token="
CITY_BOUNDARIES_URL = "California_Cities_and_Identifiers_Blue_Version_view_1826470044727749789.geojson"
# %%
city_boundaries_gdf = gpd.read_file(CITY_BOUNDARIES_URL)
# %%
city_boundaries_gdf['CDTFA_COUNTY'].unique()
# %%
target_counties = ['Los Angeles County', 'Orange County', 'San Francisco County', 'Alameda County', 'Santa Clara County', 'San Mateo County', 'Sacramento County', 'San Diego County']
select_boundaries_gdf = city_boundaries_gdf[city_boundaries_gdf['CDTFA_COUNTY'].isin(target_counties)]
select_boundaries_gdf['CDTFA_COUNTY'].unique()
# %%
# city_boundaries = requests.get(CITY_BOUNDARIES_URL)
# city_boundaries.raise_for_status()
if select_boundaries_gdf.crs != 'epsg:4326':
    select_boundaries_gdf = select_boundaries_gdf.to_crs(epsg=4326)

m = folium.Map(location=[34.0617140033952, -118.314146442073], tiles="CartoDB Positron", zoom_start=10)
# folium.GeoJson(select_boundaries_gdf).add_to(m)
# %%
folium.GeoJson(
    select_boundaries_gdf,
    name="Cities",
    tooltip=folium.GeoJsonTooltip(fields=["CDTFA_CITY"], aliases=["City Name:"]),
).add_to(m)
m
#

# %%

prestops_gdf = gpd.read_file("California_Transit_Stops.geojson", driver="GeoJSON")
prestops_gdf['n_arrivals'] = prestops_gdf['n_arrivals'].astype(int)



# %%
Tier_1 = prestops_gdf[((prestops_gdf['routetypes'].str.contains("2")) & (prestops_gdf['n_arrivals']>=72)) | (prestops_gdf['routetypes'].str.contains("1"))]
Tier_2 = prestops_gdf[((prestops_gdf['routetypes'].str.contains("2")) & ((prestops_gdf['n_arrivals']<72) & (prestops_gdf['n_arrivals']>=48))) | (prestops_gdf['routetypes'].str.contains("0"))]
Tier_1['Tier'] = 1
Tier_2['Tier'] = 2
stops_df = pd.concat([Tier_1, Tier_2])
stops_df

# %%
list(zip(stops_df.geometry.y, stops_df.geometry.x))
# %%

unique_values = stops_df['route_ids_served'].str.split(', ').explode().unique()
unique_values
# %%
for route_id in unique_values:
    filtered_df = stops_df[stops_df['route_ids_served'].str.contains(route_id)]
    folium.PolyLine(
        locations=list(zip(filtered_df.geometry.y, filtered_df.geometry.x)),
        tooltip=folium.GeoJsonTooltip(fields=["route_ids_served"], aliases=["Route:"]),
        ).add_to(m)
m
# %%
folium.Marker(
    locations=list(zip(stops_df.geometry.y, stops_df.geometry.x)),
        tooltip=folium.GeoJsonTooltip(fields=["stop_name"], aliases=["Stop:"]),
        ).add_to(m)
m


# %%
for index, row in stops_df.iterrows():
    if not pd.isna(row.geometry.y) and not pd.isna(row.geometry.x):
        folium.Marker( 
            location=[row.geometry.y, row.geometry.x],
            popup=row['stop_name']
            ).add_to(m)
m


# %%
