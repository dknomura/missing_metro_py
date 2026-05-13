# CaliperPy / GISDK Rules

## Source
TransCAD 10.0 GISDK documentation + runtime errors from a live
debugging session. Rules marked [CONFIRMED] were proven by actual
runtime errors. Rules marked [DOCS] come from documentation only.

---

## Connection

[CONFIRMED] After any crash or RPC error (-2147023174), restart the
Python kernel entirely. Calling connect() on a broken session does not
reset the underlying COM object.

```python
# Full reset sequence — only works from a fresh kernel
try: caliperpy.TransCAD.disconnect()
except: pass
import importlib; importlib.reload(caliperpy)
dk = caliperpy.TransCAD.connect(log_file="model.log")
```

[CONFIRMED] Always probe the connection before running anything:
```python
try:
    dk.GetViews(None)
except Exception:
    # connection is dead — reconnect before proceeding
```

---

## API Translation

[CONFIRMED] `GetResults()` on any OO class returns a plain Python
tuple, NOT a GisdkObject with a `.Data` attribute. Index directly:
`raw[0]`, `raw[1]`, etc.

[CONFIRMED] `GetTableStructure()` returns a tuple of tuples. Convert
before modifying:
```python
struct = [list(s) for s in dk.GetTableStructure(vw, {"Include Original": "True"})]
```

[DOCS] GISDK option arrays `{{key, value}}` map to Python dicts
`{"key": value}`. Nested option arrays map to nested dicts.

[DOCS] `CreateMap` options must be list-of-lists, not a dict:
```python
dk.CreateMap("MyMap", [["Scope", scope]])   # correct
dk.CreateMap("MyMap", {"Scope": scope})     # wrong
```

[CONFIRMED] `GetDBInfo(db)` returns `[scope, label, revision]`.
Use index `[0]` for scope. `GetDBScope()` does not exist.

---

## View Management

[CONFIRMED] `OpenTable()` and `AddLayer()` return the ACTUAL view
name TransCAD assigned. Always capture and use this return value.
Never reconstruct a view name from a string — TransCAD deduplicates
by appending `:1`, `:2` etc. when the same name is opened twice.

```python
taz_vw = dk.OpenTable("TAZ", "FFB", [path, None])
# taz_vw may be "TAZ", "TAZ:1", "TAZ:2" — use it, don't assume "TAZ"
```

[CONFIRMED] Open each file exactly once. Pass the view name as a
parameter to every function that needs it. Never call `OpenTable`
inside a helper for a file that might already be open.

[CONFIRMED] Call `dk.SetView(vw)` before any non-OO procedure that
operates on a "current view" — including `ApplyLinearModel`,
`SelectByQuery`, and most `TCB Run Procedure` calls. Omitting it
causes `No current view`.

[CONFIRMED] Viewset strings use `"viewname|setname"` format. A
trailing pipe with no set name means all records:
```python
zone_set = taz_vw + "|"    # correct — all records
zone_set = taz_vw           # wrong — TransCAD treats this as a set name
```

[DOCS] `ModifyTable()` cannot be called on a joined view or any view
that is currently part of a join. Close the join first.

[DOCS] `JoinViews()` field specs are `"viewname.fieldname"` strings.
The view names must be the actual names returned by `OpenTable` /
`AddLayer`, not the names you passed in.

---

## File Handling

[CONFIRMED] Delete `.bin` AND its `.dcb` descriptor before every run.
TransCAD raises `Error creating output file` if the `.bin` exists:
```python
def _delete_if_exists(path):
    for f in [path, path.replace(".bin", ".dcb")]:
        if os.path.exists(f): os.remove(f)
```

[CONFIRMED] Call `close_all_views(dk)` BEFORE `_delete_if_exists()`.
A `PermissionError` on `os.remove` means TransCAD still has the file
locked in an open view:
```python
def close_all_views(dk):
    try:
        names = dk.GetViews(None)[0] or []
        for vw in names:
            try: dk.CloseView(vw)
            except: pass
    except: pass
```

[CONFIRMED] Use `taz.bin` (attribute table) in `DataFile()`, not
`taz.dbd` (geographic file). The geographic file spins up GIS
rendering under COM which can crash TransCAD.

---
[CONFIRMED] Never hardcode matrix core names. Network.Skims names cores after the Minimize field ("Time"), not "Shortest Path". Always read the actual name with GetMatrixCoreNames(matrix)[0] before referencing it.

## Adding / Dropping Fields

[CONFIRMED] `TCB Add Field` macro does not exist. Use `ModifyTable`:
```python
def add_field(dk, vw, name, ftype="Real", width=12, dec=4):
    struct = [list(s) for s in dk.GetTableStructure(vw, {"Include Original": "True"})]
    if any(s[0] == name for s in struct): return
    struct.append([name, ftype, width, dec, False, None, None, None, None, None, None, None])
    dk.ModifyTable(vw, struct)
    # last element None = new field (no original name)
```

[DOCS] To drop fields, pass only the fields you want to KEEP:
```python
def drop_fields(dk, vw, to_drop):
    struct     = [list(s) for s in dk.GetTableStructure(vw, {"Include Original": "True"})]
    new_struct = [s for s in struct if s[0] not in set(to_drop)]
    dk.ModifyTable(vw, new_struct)
```

[CONFIRMED] FillVector does not exist in TransCAD 10 GISDK.

[CONFIRMED] Vector objects returned by GetDataVector have three attributes:
  .dk_server  — the caliperpy Gisdk instance
  .dk_value   — the raw COM handle (pass this where GISDK expects a Vector)
  .assign_expression — used internally for lazy eval; v * scalar returns
                       an Expression, not a Vector. Never use Vector arithmetic.

[CONFIRMED] The only reliable way to write to a view field is:
  dk.SetDataVector(vw + "|", field, vector.dk_value, None)
  where vector was obtained from dk.GetDataVector on the same field.
  You cannot construct a new Vector from a Python list without ArrayToVector,
  and ArrayToVector signature in caliperpy is dk.ArrayToVector(list) — 1 arg.
  Test before relying on it; COM type matching is fragile.

[CONFIRMED] ApplyLinearModel silently no-ops if the dependent field already
contains non-zero values from a prior run. Always call close_all_views(dk)
before open_taz(dk) to get a clean slate. Never reuse a TAZ view across
pipeline runs.

[CONFIRMED] There is no Vector() constructor callable via RunMacro in
TransCAD 10. To zero a field without SetDataVector, drop and re-add it:
    struct = [list(s) for s in dk.GetTableStructure(vw, {"Include Original": "True"})]
    dk.ModifyTable(vw, [s for s in struct if s[0] != fld])
    add_field(dk, vw, fld, "Real", 12, 4)
This is the only confirmed-working zero pattern that avoids Vector type issues.

[CONFIRMED] There is no API to release matrix file handles in TransCAD 10.
"File X.mtx is in use" with no file on disk means a stale in-memory handle
from a prior session. The only fix is to physically close and reopen the
TransCAD application — disconnect/reload/connect in Python alone is
insufficient. Prevention: always use unique output filenames per session
(e.g. timestamp suffix) so TransCAD never reuses a handle.
---

## Non-Existent Functions — Never Use

| Wrong | Correct |
|---|---|
| `dk.GetDBScope(db)` | `dk.GetDBInfo(db)[0]` |
| `dk.RunMacro("G30 Trip Attractions", ...)` | `dk.ApplyLinearModel(opts)` |
| `dk.RunMacro("TCB Add Field", ...)` | `add_field()` via `ModifyTable` |
| `o.GetResults().Data["key"]` | `o.GetResults()[index]` |
| `dk.CreateMap("n", {"Scope": s})` | `dk.CreateMap("n", [["Scope", s]])` |

---

## Confirmed Working Procedure Names

```python
# Direct functions
dk.ApplyLinearModel(opts)

# TCB Run Procedure
dk.RunMacro("TCB Run Procedure", "Linear Evaluation", opts)
dk.RunMacro("TCB Run Procedure", "TCSPMAT", opts)
dk.RunMacro("TCB Run Procedure", "Gravity", opts)
dk.RunMacro("TCB Run Procedure", "Assignment", opts)
dk.RunMacro("TCB Run Procedure", "Intrazonal", opts)

# TCB Run Operation
dk.RunMacro("TCB Run Operation", "Build Highway Network", opts)
dk.RunMacro("TCB Run Operation", "Highway Network Setting", opts)
```

## Confirmed Working OO Classes

```python
dk.CreateObject("Generation.CrossClass", None)
dk.CreateObject("Generation.Balance")
dk.CreateObject("Network.Create")
dk.CreateObject("Network.Settings", {"Network": net_file})
dk.CreateObject("Network.Skims")
dk.CreateObject("Network.Assignment")
dk.CreateObject("Distribution.Gravity")
dk.CreateObject("Distribution.PA2OD")
dk.CreateObject("Distribution.Intrazonal")
```

Note: "Confirmed" means confirmed present in GISDK docs. Not all
have been run to completion in a live session.

---

## Error Lookup

| Error | Cause | Fix |
|---|---|---|
| `Cannot find Gisdk function: X` | Function does not exist | Check docs — may be renamed or OO-only |
| `Cannot find Gisdk macro: X` | Macro name wrong | Use confirmed names above |
| `Cannot find set <viewname>` | Zone Set missing `\|` | Use `vw + "\|"` |
| `Cannot find set <viewname>:1` | View opened twice | Close all views, open once, reuse |
| `No current view` | `SetView` not called | `dk.SetView(vw)` before procedure |
| `bat_pcop, 987` | Wrong option structure | Check Zone Set format and field prefixes |
| `Error creating output file` | `.bin` exists from prior run | Delete `.bin` + `.dcb` first |
| `PermissionError` on delete | TransCAD file lock | `close_all_views(dk)` first |
| `RPC server unavailable` | TransCAD crashed | Restart kernel, disconnect, reconnect |
| `tuple has no attribute 'Data'` | `GetResults()` returns tuple | Index directly: `raw[0]`, `raw[1]` |
| `can only concatenate tuple` | `GetTableStructure` returns tuples | `[list(s) for s in struct]` |
| `Parameter 1 wrong type, Expected String found Array` | Tuple passed where view name string expected | Extract string before passing |
| `transcadtask, 521` | Output file locked from crashed run | `close_all_views` then delete `.bin` + `.dcb` |


# TransCAD Task
Background:
Imagine you are the chief transportation planner in the City of Amarillo Department of Transportation. The city is experiencing fast growth. In the next 10 years, both population and employment in the city are expected to grow by 20%. However, due to environmental regulations, the total Vehicle Miles Traveled (VMT) has to stay the same.
Task 1. 
A.
i.	Describe the current traffic condition in the city, including but not limited to the distribution of population, employment, land use and travel demand (i.e., a summary of each of the four steps of the travel demand model outputs). 
ii.	Show the daily traffic condition on a map and highlight the bottlenecks (i.e., V/C>1). 
iii.	What about hourly traffic conditions and bottlenecks? 
iv.	What’s the totally daily VMT and VHT (Vehicle Hours Traveled)? 

B.
i.	In the No-Build scenario (i.e., no improvement to the current condition and assume it will grow the same way across the area), what will the future traffic condition be? 
ii.	What’s the totally daily VMT and VHT (Vehicle Hours Traveled) in 10 years? 
iii.	Where are the future bottlenecks (daily and hourly)?


C.	Assuming adding more lanes to the highway/street bottlenecks can solve the problems (well, it is a big assumption) and assuming everything else stays the same (for example, no additional travel occurs because of the improvements to the highway network), without running the model, how many more lanes are needed at each bottleneck?

Task 2. 
A.	Put together the flow chart you have drawn for each chapter to create a comprehensive flow chart to cover the entire travel demand modeling process for the city. 

B.	Trace each input file to its original source, as far as you can (hint: the original data source can be Household Travel Survey, Census, ACS, etc.)

C.	Describe briefly but clearly what is included in each input file, procedure, and output file in the flow chart. The goal is for the general public to understand what a travel demand forecasting process is and how it is done.


Task 3. 
A.	Take a close look at the flow chart, then discuss all possible methods (and/or policies) to achieve your ultimate goal (i.e., keep VMT unchanged while population and employment grow by 20% in the next 10 years) and what’s your justifications for doing so? What’s the pros and/or cons of each method? For example, maybe you can change trip production/attraction rates (Step 1. Trip Generation). Can HBW trip production rates be lowered?  If so, how? What are the justifications? 

B.	Now you need to test the sensitivity of model inputs. For each of the four steps, choose at least one factor, change the corresponding input file (directly or indirectly), then run the model, get the results (VMT) and compare against the baseline to find out the sensitivity of this model input.

C.	Now that you have some idea how sensitive the model is to each input you chose, it is time to change multiple input files (at least from three of the four steps that need to be changed) at the same time to see how effective they work together towards your ultimate goal. You may need to try multiple times to achieve your goal.

Deliverables:
A report that clearly summarizes the process of how each of the above tasks (Task 1A, 1B, 1C; Task 2A, 2B, 2C; Task 3A, 3B, 3C) is fulfilled. Use tables, charts, figures, and screenshots to support your work as detailed as necessary. 
The purpose is to provide decision-makers with brief but important project information. Keep in mind that decision-makers are often government officials who need to make decisions based on your technical analyses. However, since they may not necessarily have advanced knowledge about the travel demand modeling, your report needs to provide enough information for them to understand each step of the travel demand modeling and how to change policies to achieve the ultimate goals.
In addition to the report, each of the three team members needs to briefly describe his/her role and contribution to this project. If the contribution is not equivalent among team members, what’s the fair share?
