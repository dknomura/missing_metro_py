# missing_metro_py
Using uv, install instructions [in repo](https://github.com/astral-sh/uv)

## Setup

```bash
# Install dependencies
uv sync
```

## Development
Create new notebook and run in VS Code with [jupyter extension](https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter). 

Jupytext is also used to help with version control, so .ipynb files are not added to git. When you create and run a new notebook a corresponding .py file will be created in ./scripts folder

```bash
# Generate notebook files
jupytext --to ipynb ./scripts/*.py
```

Unable to install ArcGIS py library, so getting the features from ArcGIS will be done with http client (requests)
1. Create a new item in [ArcGIS Online My Content](https://pomona.maps.arcgis.com/home/content.html?sortField=modified&sortOrder=desc&view=table#my)
2. Zip and upload your file DB (shapefile, gdb, csv, etc)
3. Make it a feature layer
4. Share and make it public
5. Open the layer URL, which should start with https://services3.arcgis.com/...
6. Select the layer
7. Scroll down and click Support Operations => query
8. Input "1=1" into where field, input "*" into out fields field, and change the format to GEOJSON

If the notebook and .py file are not syncing, then use the [Jupytext VSCode Extension](https://marketplace.visualstudio.com/items?itemName=caenrigen.jupytext-sync) command to "Pair via Jupytext"

Sometimes the map will not show in the notebook and there will be message in the notbook to Trust the notebook to show the map. Just use the command palette to "Manage Workspace Trust" and then turn the trust settings off/on.

## Setting up ArcGIS API py library 
WIP: Currently not working, so follow the steps for using the requests lib

The arcgis lib needs the Visual Studio Build Tools, 
1. go to https://visualstudio.microsoft.com/downloads/ 
2. Scroll to Tools for Visual Studio 
3. Download "Build Tools for Visual Studio 2026"
4. Initiate installation and Select "Desktop Development with C++" 

