# ---
# jupyter:
#   jupytext:
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
residential_df['Zoning'].value_counts()

# %%
residential_df[residential_df.index < 1000].explore('Zoning')

# %%
