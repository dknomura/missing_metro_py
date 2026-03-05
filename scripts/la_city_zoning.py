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
zoning_df['CATEGORY'].value_counts()

# %%
residential_df = zoning_df[zoning_df['CATEGORY'].str.contains('Residential')]

residential_df

# %%
residential_df['Zoning']

# %%
residential_df[residential_df.index < 1000].explore('Zoning')

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
import pandas as pd
residential_df[pd.to_numeric(residential_df['density_limit'], errors='coerce').isnull()]['Zoning'].value_counts()


# %%
residential_df = residential_df.to_crs(epsg=4326)
residential_df.to_file('..\data\la_city_zoning.json', driver='GeoJSON')

