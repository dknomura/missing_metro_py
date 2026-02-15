# missing_metro_py
Using uv, install instructions here https://github.com/astral-sh/uv

## Setup
```bash
# Install dependencies
uv sync
```

Create new notebook and run in VS Code with jupyter extension https://marketplace.visualstudio.com/items?itemName=ms-toolsai.jupyter. 

Jupytext is also used to help with version control, so .ipynb files are not added to git. When you create and run a new notebook a corresponding .py file will be created in ./scripts folder

```bash
# Generate notebook files
jupytext --to ipynb ./scripts/*.py
```