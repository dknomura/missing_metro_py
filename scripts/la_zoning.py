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
import geopandas

parcels_df = geopandas.read_file(
    r"C:\Users\default.LAPTOP-SGE9GHN4\Downloads\LACounty_Parcels\LACounty_Parcels.gdb"
)
parcels_df

# %%
parcels_df["UseType"].unique()

# %%
residential_df = parcels_df[parcels_df["UseType"] == "Residential"]

residential_df

# %%
residential_df.columns.values.tolist()

# %%
residential_df["UseDescription"].unique().tolist()

# %%
