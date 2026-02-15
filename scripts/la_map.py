# ---
# jupyter:
#   jupytext:
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

m = folium.Map(location=[45.5236, -122.6750], zoom_start=13) # Creates a map object
folium.Marker(location=[45.5236, -122.6750], popup="Portland").add_to(m) # Adds a marker

m
# %%
print('helljo')

# %%
