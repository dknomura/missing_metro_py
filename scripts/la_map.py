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

FEATURE_LAYER_URL = "https://services3.arcgis.com/NaFf4UaPo3IgQXqn/arcgis/rest/services/minn_county/FeatureServer/0/query?where=1%3D1&objectIds=&time=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&resultType=none&distance=&units=esriSRUnit_Meter&outFields=*&returnGeometry=true&maxAllowableOffset=&geometryPrecision=&outSR=4326&returnIdsOnly=false&returnCountOnly=false&returnExtentOnly=false&returnDistinctValues=false&orderByFields=&groupByFieldsForStatistics=&outStatistics=&resultOffset=&resultRecordCount=&returnZ=false&returnM=false&quantizationParameters=&sqlFormat=none&f=pgeojson&token="

try:
    response = requests.get(FEATURE_LAYER_URL)
    response.raise_for_status()
    feature_data = response.json()
except requests.exceptions.RequestException as e:
    print(f"Error fetching data: {e}")
    feature_data = None

m = folium.Map(location=[46.7296, -94.6859], zoom_start=6)

folium.GeoJson(
    feature_data,
    name="Test Layer",
).add_to(m)

folium.LayerControl().add_to(m)

m


# %%
print("helljo")

# %%
