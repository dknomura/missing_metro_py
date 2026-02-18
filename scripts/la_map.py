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
#     display_name: missing-metro-py (3.13.12)
#     language: python
#     name: python3
# ---

# %%
import folium
import requests

FEATURE_LAYER_URL = "https://services3.arcgis.com/NaFf4UaPo3IgQXqn/ArcGIS/rest/services/MTA_Metro_Lines/FeatureServer/0/query?where=1%3D1&objectIds=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&resultType=none&distance=0.0&units=esriSRUnit_Meter&outDistance=&relationParam=&returnGeodetic=false&outFields=*&returnGeometry=true&returnEnvelope=false&featureEncoding=esriDefault&multipatchOption=xyFootprint&maxAllowableOffset=&geometryPrecision=&outSR=&defaultSR=&datumTransformation=&applyVCSProjection=false&returnIdsOnly=false&returnUniqueIdsOnly=false&returnCountOnly=false&returnExtentOnly=false&returnQueryGeometry=false&returnDistinctValues=false&cacheHint=false&collation=&orderByFields=&groupByFieldsForStatistics=&returnAggIds=false&outStatistics=&having=&resultOffset=&resultRecordCount=&returnZ=false&returnM=false&returnTrueCurves=false&returnExceededLimitFeatures=true&quantizationParameters=&sqlFormat=none&f=pgeojson&token="
# FEATURE_LAYER_URL = "https://services3.arcgis.com/NaFf4UaPo3IgQXqn/arcgis/rest/services/minn_county/FeatureServer/0/query?where=1%3D1&objectIds=&time=&geometry=&geometryType=esriGeometryEnvelope&inSR=&spatialRel=esriSpatialRelIntersects&resultType=none&distance=&units=esriSRUnit_Meter&outFields=*&returnGeometry=true&maxAllowableOffset=&geometryPrecision=&outSR=4326&returnIdsOnly=false&returnCountOnly=false&returnExtentOnly=false&returnDistinctValues=false&orderByFields=&groupByFieldsForStatistics=&outStatistics=&resultOffset=&resultRecordCount=&returnZ=false&returnM=false&quantizationParameters=&sqlFormat=none&f=pgeojson&token="

try:
    response = requests.get(FEATURE_LAYER_URL)
    response.raise_for_status()
    feature_data = response.json()
except requests.exceptions.RequestException as e:
    print(f"Error fetching data: {e}")
    feature_data = None

m = folium.Map(location=[-118.314146442073, 34.0617140033952], zoom_start=6)

folium.GeoJson(
    feature_data,
    name="Test Layer",
).add_to(m)

folium.LayerControl().add_to(m)

m


# %%
print("helljo")

# %%
