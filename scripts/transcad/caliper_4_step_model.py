import os

import pandas as pd
import caliperpy
from transcad.constants import MODEL_DIR
from transcad.caliper_helpers import _delete_if_exists, add_field


def run_cross_classification(
        dk: caliperpy.Gisdk,
        taz_vw:       str  = None,
        output_file:  str  = "Script_Productions.bin",
        taz_bin:      str  = "taz.bin",
        rates_table:  str  = "PRATES.BIN",
        rates_fields_by_purpose: dict = None,
        segment_by_classification: dict = None):   
    """
    Trip productions via cross-classification.
    taz_vw must be passed — it is opened once in open_taz() and reused.
    """
    if rates_fields_by_purpose is None:
        rates_fields_by_purpose = {
            "HBW_P":       "R_HBW_P",
            "HBNW_P":      "R_HBNW_P",
            "NHB_P":       "R_NHB_P",
            "TRUCKTAXI_P": "R_TRUCKTAXI_P",
        }
    if segment_by_classification is None:
        segment_by_classification = {"HH": ["HHSize", "INC"]}

    output_path = os.path.join(MODEL_DIR, output_file)
    _delete_if_exists(output_path)

    o = dk.CreateObject("Generation.CrossClass", None)
    o.RatesTable = os.path.join(MODEL_DIR, rates_table)
    o.DataFile({"FileName": os.path.join(MODEL_DIR, taz_bin)})
    o.OutputFile = output_path

    for purpose, rate_field in rates_fields_by_purpose.items():
        o.AddRate({"RateField": rate_field, "Purpose": purpose})
    for seg_name, class_fields in segment_by_classification.items():
        o.AddSegment({"Name": seg_name, "ClassifyBy": class_fields})

    ok = o.Run()
    if not ok:
        raise RuntimeError("Generation.CrossClass failed.")

    prod_vw = dk.OpenTable("Productions", "FFB", [output_path, None])
    print(f"  Productions → {output_path}")
    print(f"  Productions view: '{prod_vw}'")
    return output_path, prod_vw


def apply_special_generators(dk, prod_bin: str, taz_vw: str):
    print("\n--- Step 1A2: Special Generators ---")

    sp_map = {
        "SP_HBW":       "HBW_P",
        "SP_HBNW":      "HBNW_P",
        "SP_NHB":       "NHB_P",
        "SP_TRUCKTAXI": "TRUCKTAXI_P",
    }

    for sp_field, prod_field in sp_map.items():
        sp_vals   = dk.VectorToArray(dk.GetDataVector(taz_vw + "|", sp_field,   None))
        prod_vals = dk.VectorToArray(dk.GetDataVector(prod_bin + "|", prod_field, None))

        new_vals = [
            sp if (sp is not None and sp > 0) else p
            for sp, p in zip(sp_vals, prod_vals)
        ]
        replaced = sum(1 for sp in sp_vals if sp is not None and sp > 0)
        print(f"  {prod_field}: replaced {replaced} zones with SP values")

        dk.SetView("Productions")
        dk.SetDataVector("Productions" + "|", prod_field, dk.ArrayToVector(new_vals), None)

    print("  Special generators applied.")


def _rezero_field(dk, taz_vw, fld):
    """Drop and re-add a field to guarantee null/zero values."""
    struct = [list(s) for s in dk.GetTableStructure(
                  taz_vw, {"Include Original": "True"})]
    new_struct = [s for s in struct if s[0] != fld]
    dk.ModifyTable(taz_vw, new_struct)
    add_field(dk, taz_vw, fld, "Real", 12, 4)


def run_attractions(dk: caliperpy.Gisdk, taz_vw: str):
    print("\n--- Step 1B: Trip Attractions ---")
    dk.SetView(taz_vw)

    field_names, _ = dk.GetFields(taz_vw, "All")

    def find_field(candidates):
        for c in candidates:
            if c in field_names:
                return c
        raise ValueError(f"None of {candidates} found in TAZ fields: {field_names}")

    hh_f  = find_field(["HH",      "HOUSEHOLDS", "HHS"])
    ret_f = find_field(["RETAIL",  "RET_EMP",    "RETEMP"])
    bas_f = find_field(["BASIC",   "BASIC_EMP",  "BASEMP"])
    svc_f = find_field(["SERVICE", "SERV_EMP",   "SVCEMP"])
    print(f"  Using: {hh_f}, {ret_f}, {bas_f}, {svc_f}")

    for fld in ["HBW_A", "HBNW_A", "NHB_A", "TRUCKTAXI_A"]:
        _rezero_field(dk, taz_vw, fld)

    independents = [f"{taz_vw}.{f}" for f in [hh_f, ret_f, bas_f, svc_f]]
    zone_set     = taz_vw + "|"

    purposes = {
        "HBW_A":       [0, 0.1033, 1.2321, 1.3089, 1.2341],
        "HBNW_A":      [0, 0.6775, 7.4483, 0.4073, 1.2355],
        "NHB_A":       [0, 0.3951, 6.2293, 0.7082, 1.5902],
        "TRUCKTAXI_A": [0, 0.1130, 0.4209, 0.4967, 0.6361],
    }

    for dep_field, coeffs in purposes.items():
        print(f"  Computing {dep_field} ...")
        dk.ApplyLinearModel({
            "Input":  {"Zone Set":     zone_set},
            "Global": {"Method":       "R",
                       "Coefficients": coeffs,
                       "Output to Report File": 0},
            "Field":  {"Dependent":    f"{taz_vw}.{dep_field}",
                       "Independents": independents},
        })
        v = dk.VectorToArray(dk.GetDataVector(taz_vw + "|", dep_field, None))
        non_null = [x for x in v if x is not None]
        print(f"    {dep_field}: n_nonzero={len(non_null)}  sum={sum(non_null):,.1f}")

    print("  Attractions done.")

def apply_special_attractions(dk, taz_vw: str):
    print("\n--- Step 1B2: Special Attractions ---")

    sa_map = {
        "SA_HBW":       "HBW_A",
        "SA_HBNW":      "HBNW_A",
        "SA_NHB":       "NHB_A",
        "SA_TRUCKTAXI": "TRUCKTAXI_A",
    }

    for sa_field, attr_field in sa_map.items():
        sa_vals   = dk.VectorToArray(dk.GetDataVector(taz_vw + "|", sa_field,   None))
        attr_vals = dk.VectorToArray(dk.GetDataVector(taz_vw + "|", attr_field, None))
        new_vals  = [
            sa if (sa is not None and sa > 0) else a
            for sa, a in zip(sa_vals, attr_vals)
        ]
        replaced = sum(1 for sa in sa_vals if sa is not None and sa > 0)
        dk.SetView(taz_vw)
        dk.SetDataVector(taz_vw + "|", attr_field, dk.ArrayToVector(new_vals), None)
        
        # Verify the write stuck
        check = dk.VectorToArray(dk.GetDataVector(taz_vw + "|", attr_field, None))
        print(f"  {attr_field}: replaced {replaced} zones  sum before={sum(x for x in attr_vals if x):,.0f}  sum after={sum(x for x in check if x):,.0f}")

    print("  Special attractions applied.")


def run_balancing(dk: caliperpy.Gisdk, taz_vw: str, prod_vw: str,
                  output_file: str = "Script_PA.bin",
                  hold_method="HoldProductions") -> str:
    """
    Balance P and A using Generation.Balance.
    Joins taz_vw (_A fields) and prod_vw (_P fields) on TAZ ID.
    Closes both views on completion — do not reuse them after this call.
    """
    print("\n--- Step 1C: Trip Balancing ---")

    pa_file = os.path.join(MODEL_DIR, output_file)
    _delete_if_exists(pa_file)

    # Find the correct join key — TAZ bins use "TAZ" not "ID"
    taz_fields,  _ = dk.GetFields(taz_vw,  "All")
    prod_fields, _ = dk.GetFields(prod_vw, "All")

    def find_key(fields, candidates):
        for c in candidates:
            if c in fields:
                return c
        raise ValueError(f"No join key found. Tried {candidates}. Have: {fields}")

    taz_key  = find_key(taz_fields,  ["TAZ", "ID", "ZoneID", "ZONE"])
    prod_key = find_key(prod_fields, ["TAZ", "ID", "ZoneID", "ZONE"])
    print(f"  Joining on {taz_vw}.{taz_key} ↔ {prod_vw}.{prod_key}")

    joined = dk.JoinViews(
        "TAZ+Productions",
        f"{taz_vw}.{taz_key}",
        f"{prod_vw}.{prod_key}",
        None
    )
    if not joined:
        raise RuntimeError("JoinViews failed — check view names and join key types.")
    print(f"  Joined view: '{joined}'")

    obj = dk.CreateObject("Generation.Balance", None)
    obj.AddDataSource({"ViewName": joined})   # ViewName for open view, not TableName
    obj.OutputFile = pa_file

    obj.AddPurpose({"Production": "HBW_P",       "Attraction": "HBW_A",
                    "Method": "HoldProductions"})
    obj.AddPurpose({"Production": "HBNW_P",      "Attraction": "HBNW_A",
                    "Method": hold_method})
    obj.AddPurpose({"Production": "NHB_P",       "Attraction": "NHB_A",
                    "Method": hold_method})
    obj.AddPurpose({"Production": "TRUCKTAXI_P", "Attraction": "TRUCKTAXI_A",
                    "Method": "HoldProductions"})
    ok = obj.Run()
    if not ok:
        raise RuntimeError("Generation.Balance failed.")
    if not os.path.exists(pa_file):
        raise RuntimeError(f"Balance ran but output not found: {pa_file}")

    dk.CloseView(joined)
    dk.CloseView(taz_vw)
    dk.CloseView(prod_vw)

    print(f"  Balanced P-A → {pa_file}")
    return pa_file


def build_network(dk: caliperpy.Gisdk,
                  net_output: str = "Script_Network.net") -> str:
    """
    Build highway network from network.dbd.
    UseLinkTypes requires LinkTypeInfo() to be called on Network.Create first.
    """
    print("\n--- Step 2A: Build Highway Network ---")

    net_file = os.path.join(MODEL_DIR, net_output)
    _delete_if_exists(net_file)

    net_obj = dk.CreateObject("Network.Create", None)
    net_obj.LayerDB        = os.path.join(MODEL_DIR, "network.dbd")
    net_obj.TimeUnits      = "Minutes"
    net_obj.OutNetworkName = net_file

    net_obj.AddLinkField({"Name": "Time",     "Field": "TIME",
                          "IsTimeField": True})
    net_obj.AddLinkField({"Name": "Capacity", "Field": ["AB_CAPACITY",
                                                         "BA_CAPACITY"]})
    net_obj.AddLinkField({"Name": "Alpha",    "Field": "ALPHA"})
    net_obj.AddLinkField({"Name": "Beta",     "Field": "BETA"})

    # LinkTypeInfo must be called before Run() for UseLinkTypes to work
    net_obj.LinkTypeInfo({"Label": "FUNCL", "LayerField": "FUNCL"})

    ok = net_obj.Run()
    if not ok:
        raise RuntimeError("Network.Create failed.")
    print(f"  Network created: {net_file}")

    net_set = dk.CreateObject("Network.Settings", None)
    net_set.Network        = net_file
    net_set.CentroidFilter = "TAZ <> null"
    net_set.UseLinkTypes   = True
    ok2 = net_set.Run()
    if not ok2:
        raise RuntimeError("Network.Settings failed.")
    print("  Centroids and link types configured.")

    return net_file

def _build_taz_index(dk, matrix, node_bin_path: str):
    """
    Remap skim matrix from node IDs → TAZ IDs.
    Closes any stale Nodes views before opening to prevent :1 deduplication.
    """
    # Close any open views whose name starts with "Node" or "Nodes"
    try:
        views = dk.GetViews(None)[0] or []
        for vw in views:
            if vw.lower().startswith("node"):
                try: dk.CloseView(vw)
                except: pass
    except: pass

    node_vw = dk.OpenTable("Nodes", "FFB", [node_bin_path, None])
    print(f"  Node view: '{node_vw}'")

    # Verify IDs overlap with matrix before attempting index
    node_ids = dk.VectorToArray(dk.GetDataVector(node_vw + "|", "ID",  None))
    taz_vals = dk.VectorToArray(dk.GetDataVector(node_vw + "|", "TAZ", None))
    centroids = [(i, t) for i, t in zip(node_ids, taz_vals) if t is not None]
    print(f"  Centroids: {len(centroids)}  sample: {centroids[:3]}")

    dk.SetView(node_vw)
    dk.SelectByQuery("Centroids", "Several",
                     "Select * where TAZ <> null", None)

    idx = dk.CreateMatrixIndex(
        "TAZ", matrix, "Both",
        node_vw + "|Centroids",
        "ID",   # old: node IDs (current matrix index)
        "TAZ"   # new: TAZ numbers (1–390)
    )
    dk.CloseView(node_vw)
    print(f"  TAZ index: '{idx}'")
    return idx

def run_skims(dk: caliperpy.Gisdk,
              net_file:    str = None,
              skim_output: str = "Script_Skim.mtx") -> tuple:
    print("\n--- Step 2B: Skim Matrix ---")

    skim_file = os.path.join(MODEL_DIR, skim_output)
    _delete_if_exists(skim_file, dk)

    obj = dk.CreateObject("Network.Skims", None)
    obj.Network      = net_file
    obj.LayerDB      = os.path.join(MODEL_DIR, "Network.dbd")
    obj.Origins      = "TAZ <> null"
    obj.Destinations = "TAZ <> null"
    obj.Minimize     = "Time"
    obj.OutputMatrix({
        "MatrixFile":  skim_file,
        "Matrix":      "Skim",
        "Compression": True,
        "ColumnMajor": False,
    })

    ok = obj.Run()
    if not ok:
        raise RuntimeError("Network.Skims failed.")

    # OutputMatrix path is sometimes ignored — find what was actually written
    if not os.path.exists(skim_file):
        import glob as _glob
        # Only look for files newer than 5 seconds ago to avoid stale matches
        import time
        cutoff  = time.time() - 10
        recent  = [f for f in _glob.glob(os.path.join(MODEL_DIR, "*.mtx"))
                   if os.path.getmtime(f) > cutoff]
        # Exclude known non-skim files
        exclude = {"pa.mtx", "od.mtx", "ScriptPA.mtx"}
        recent  = [f for f in recent
                   if os.path.basename(f).lower() not in
                   {e.lower() for e in exclude}]
        if not recent:
            raise RuntimeError(
                f"Skim ran but no new .mtx found. "
                f"OutputMatrix path '{skim_file}' was ignored by TransCAD."
            )
        # Copy the most recent to our stable path
        import shutil
        actual = max(recent, key=os.path.getmtime)
        shutil.copy2(actual, skim_file)
        print(f"  Copied {os.path.basename(actual)} → {skim_file}")

    matrix    = dk.OpenMatrix(skim_file, "True")
    core_name = dk.GetMatrixCoreNames(matrix)[0]

    mc      = dk.CreateMatrixCurrency(matrix, core_name, None, None, None)
    row_ids = dk.VectorToArray(dk.GetMatrixVector(mc, [["Index", "Row"]]))
    print(f"  Core: '{core_name}'  IDs: {row_ids[:3]}...{row_ids[-3:]}")

    # Always remap node IDs → TAZ IDs
    _build_taz_index(dk, matrix, os.path.join(MODEL_DIR, "Network_.bin"))

    print(f"  Skim → {skim_file}")
    return skim_file, core_name

def run_intrazonal(dk: caliperpy.Gisdk, skim_file: str, skim_core: str):
    """
    Fill the skim matrix diagonal with intrazonal travel times.
    skim_core must be the actual core name from run_skims() — never hardcode.
    """
    print("\n--- Step 2C: Intrazonal Travel Times ---")

    obj = dk.CreateObject("Distribution.Intrazonal", None)
    obj.Factor    = 0.5
    obj.Neighbors = 3
    obj.SetMatrix({"MatrixFile": skim_file, "MatrixCore": skim_core})

    ok = obj.Run()
    if not ok:
        raise RuntimeError("Distribution.Intrazonal failed.")
    print("  Intrazonal times filled.")


def run_gravity(dk: caliperpy.Gisdk,
                pa_file:     str,
                skim_file:   str,
                skim_core:   str,
                output_file: str = "Script_PA.mtx") -> str:
    """
    Doubly-constrained gravity model.
    Uses the TAZ index on the skim matrix (built in run_skims) so that
    matrix row/col IDs match the TAZ IDs in the PA table.
    """
    print("\n--- Step 3: Trip Distribution (Gravity Model) ---")
    gravity_out = os.path.join(MODEL_DIR, output_file)
    _delete_if_exists(gravity_out, dk)

    sp_mat = {
        "MatrixFile": skim_file,
        "Matrix":     skim_core,
        "RowIndex":   "TAZ",    # use the remapped TAZ index
        "ColIndex":   "TAZ",
    }    
    
    ff_table = os.path.join(MODEL_DIR, "FFDATA.DBF")

    obj = dk.CreateObject("Distribution.Gravity", None)
    obj.CalculateTLD = True
    obj.AddDatasource({"TableName": pa_file})

    for purpose, ff_field in [("HBW",       "HBW"),
                               ("HBNW",      "HBNW"),
                               ("NHB",       "NHB"),
                               ("TRUCKTAXI", "TRUCKTAXI")]:
        obj.AddPurpose({
            "Name":            purpose,
            "Production":      purpose + "_P",
            "Attraction":      purpose + "_A",
            "ConstraintType":  "Doubly",
            "Iterations":      100,
            "Convergence":     0.01,
            "ImpedanceMatrix": sp_mat,
            "Table": {
                "Name":          ff_table,
                "TimeField":     "TIME",
                "FrictionField": ff_field,
            },
        })

    obj.OutputMatrix({
        "MatrixFile":  gravity_out,
        "MatrixLabel": "Gravity Output",
        "Compression": True,
    })

    ok = obj.Run()
    if not ok:
        raise RuntimeError("Distribution.Gravity failed.")
    if not os.path.exists(gravity_out):
        raise RuntimeError(f"Gravity ran but output not found: {gravity_out}")

    print(f"  Gravity matrix → {gravity_out}")
    return gravity_out


def run_pa2od(dk: caliperpy.Gisdk,
              gravity_file: str,
              output_file:  str = "Script_OD.mtx",
              occupancy_overrides: dict = None) -> str:
    """
    Convert PA matrix to OD vehicle trips.
    occupancy_overrides: dict of {purpose: occupancy} to override defaults.
    """
    print("\n--- Step 4: PA to OD ---")

    od_out = os.path.join(MODEL_DIR, output_file)
    _delete_if_exists(od_out, dk)

    occ = {"HBW": 1.1, "HBNW": 1.3, "NHB": 1.5, "TRUCKTAXI": 1.0}
    if occupancy_overrides:
        occ.update(occupancy_overrides)

    o = dk.CreateObject("Distribution.PA2OD", None)
    o.Matrix(gravity_file)
    o.Daily        = True
    o.ReportByHour = False
    for purpose, occupancy in occ.items():
        o.AddPurpose({"Name": purpose, "Occupancy": occupancy})
    o.OutputMatrix(od_out)

    ok = o.Run()
    if not ok:
        raise RuntimeError("Distribution.PA2OD failed.")
    if not os.path.exists(od_out):
        raise RuntimeError(f"PA2OD ran but output not found: {od_out}")

    print(f"  OD matrix → {od_out}")
    return od_out

def add_ie_ee_to_od(dk, od_file, ie_mtx_file="ie.mtx", ee_trips_file="EE Trips.bin"):
    print("\n--- Step 4B: Adding IE/EE External Trips ---")

    od_matrix = dk.OpenMatrix(od_file, "True")

    # Add cores if missing
    od_cores = list(dk.GetMatrixCoreNames(od_matrix))
    if "IE (0-24)" not in od_cores:
        dk.AddMatrixCore(od_matrix, "IE (0-24)")
    if "EE (0-24)" not in od_cores:
        dk.AddMatrixCore(od_matrix, "EE (0-24)")

    # ── IE: fill row by row ───────────────────────────────────────────────
    ie_matrix    = dk.OpenMatrix(os.path.join(MODEL_DIR, ie_mtx_file), "True")
    ie_core_name = dk.GetMatrixCoreNames(ie_matrix)[0]
    ie_mc = dk.CreateMatrixCurrency(ie_matrix, ie_core_name, None, None, None)
    od_ie = dk.CreateMatrixCurrency(od_matrix, "IE (0-24)",  None, None, None)

    row_ids = dk.VectorToArray(dk.GetMatrixVector(ie_mc, [["Index", "Row"]]))
    for row_id in row_ids:
        if row_id is None:
            continue
        row_vec = dk.GetMatrixVector(ie_mc, [["Row", row_id]])
        dk.SetMatrixVector(od_ie, row_vec, [["Row", row_id]])
    print("  IE done")

    # ── EE: group by origin, fill row by row ─────────────────────────────
    import collections
    import numpy as np

    ee_vw   = dk.OpenTable("EETrips", "FFB", [os.path.join(MODEL_DIR, ee_trips_file), None])
    origins = dk.VectorToArray(dk.GetDataVector(ee_vw + "|", "Origin",      None))
    dests   = dk.VectorToArray(dk.GetDataVector(ee_vw + "|", "Destination", None))
    flows   = dk.VectorToArray(dk.GetDataVector(ee_vw + "|", "Flow",        None))
    dk.CloseView(ee_vw)

    od_ee   = dk.CreateMatrixCurrency(od_matrix, "EE (0-24)", None, None, None)
    col_ids = dk.VectorToArray(dk.GetMatrixVector(od_ee, [["Index", "Column"]]))
    col_pos = {int(float(c)): i for i, c in enumerate(col_ids) if c is not None}

    row_flows = collections.defaultdict(dict)
    for o, d, f in zip(origins, dests, flows):
        if f is not None and f > 0:
            row_flows[int(float(o))][int(float(d))] = float(f)

    for row_id, cell_dict in row_flows.items():
        vals = [0.0] * len(col_ids)
        for col_id, val in cell_dict.items():
            if col_id in col_pos:
                vals[col_pos[col_id]] = val
        row_vec = dk.ArrayToVector(vals)
        dk.SetMatrixVector(od_ee, row_vec, [["Row", row_id]])
    print("  EE done")


    # ── Verify totals ─────────────────────────────────────────────────────
    for core in dk.GetMatrixCoreNames(od_matrix):
        mc    = dk.CreateMatrixCurrency(od_matrix, core, None, None, None)
        rs    = dk.VectorToArray(dk.GetMatrixVector(mc, [["Marginal", "Row Sum"]]))
        total = sum(x for x in rs if x is not None)
        print(f"    {core}: {total:,.0f}")

def run_assignment(dk: caliperpy.Gisdk,
                   net_file:          str,
                   od_file:           str,
                   flow_output:       str   = "Script_Daily_Assign.bin",
                   demand_multiplier: float = 1.0,
                   vc_threshold:      float = 1.0) -> dict:
    """
    CUE traffic assignment with BPR delay function.
    Returns dict: {VMT, VHT, flow_bin, bottlenecks_df}
    """
    print("\n--- Step 5: Traffic Assignment ---")

    flow_bin = os.path.join(MODEL_DIR, flow_output)
    _delete_if_exists(flow_bin)

    # ── Build TAZ→NodeID index on OD matrix ──────────────────────────────
    od_matrix = dk.OpenMatrix(od_file, "True")
    od_cores  = dk.GetMatrixCoreNames(od_matrix)
    print(f"  OD cores: {od_cores}")

    net_db   = os.path.join(MODEL_DIR, "network.dbd")
    node_bin = os.path.join(MODEL_DIR, "Network_.bin")

    try:
        views = dk.GetViews(None)[0] or []
        for vw in (views or []):
            if vw.lower().startswith("node"):
                try: dk.CloseView(vw)
                except: pass
    except: pass

    node_vw = dk.OpenTable("Nodes", "FFB", [node_bin, None])
    print(f"  Node view: '{node_vw}'")
    dk.SetView(node_vw)
    dk.SelectByQuery("Centroids", "Several", "Select * where TAZ <> null", None)
    dk.CreateMatrixIndex(
        "TAZ to Node ID", od_matrix, "Both",
        node_vw + "|Centroids", "TAZ", "ID"
    )
    dk.CloseView(node_vw)

    # ── Assignment ────────────────────────────────────────────────────────
    obj = dk.CreateObject("Network.Assignment", None)
    obj.LayerDB     = net_db
    obj.Network     = net_file
    obj.Method      = "UE"
    obj.Iterations  = 100
    obj.Convergence = 0.0001
    obj.FlowTable   = flow_bin

    if demand_multiplier != 1.0:
        obj.DemandMultiplier = demand_multiplier

    obj.ResetClasses()
    obj.DemandMatrix({
        "MatrixFile":  od_file,
        "RowIndex":    "TAZ to Node ID",
        "ColumnIndex": "TAZ to Node ID",
    })
    for core in od_cores:
        obj.AddClass({"Demand": core})

    obj.DelayFunction = {
        "Function": "bpr.vdf",
        "Fields":   ["Time", "Capacity", "Alpha", "Beta", "None"],
    }

    ok = obj.Run()
    if not ok:
        raise RuntimeError("Network.Assignment failed.")

    # ── Read results before releasing object ──────────────────────────────
    task_results = obj.GetTaskResults()
    result_dict  = dict(task_results)
    vmt = float(result_dict.get("VMT w/o Centroids", result_dict.get("Total VMT", 0)))
    vht = float(result_dict.get("VHT w/o Centroids", result_dict.get("Total VHT", 0)))

    del obj  # release COM lock on flow table

    if not os.path.exists(flow_bin):
        raise RuntimeError(f"Assignment ran but flow table not found: {flow_bin}")

    # ── Read flow table and compute bottlenecks ───────────────────────────
    flow_vw_name = f"Flow_{os.path.basename(flow_bin).replace('.bin', '')}"
    try:
        dk.CloseView(flow_vw_name)
    except:
        pass
    flow_vw = dk.OpenTable(flow_vw_name, "FFB", [flow_bin, None])

    max_voc_vals = dk.VectorToArray(dk.GetDataVector(flow_vw + "|", "Max_VOC",  None))
    id1_vals     = dk.VectorToArray(dk.GetDataVector(flow_vw + "|", "ID1",      None))
    tot_flow     = dk.VectorToArray(dk.GetDataVector(flow_vw + "|", "Tot_Flow", None))
    tot_vmt_vals = dk.VectorToArray(dk.GetDataVector(flow_vw + "|", "Tot_VMT",  None))

    try:
        dk.CloseView(flow_vw)
    except:
        pass

    rows = []
    for id1, voc, flow, tvmt in zip(id1_vals, max_voc_vals, tot_flow, tot_vmt_vals):
        if voc is not None and float(voc) >= vc_threshold:
            rows.append({
                "ID1":      id1,
                "Max_VOC":  float(voc),
                "Tot_Flow": float(flow) if flow is not None else None,
                "Tot_VMT":  float(tvmt) if tvmt is not None else None,
            })

    bottlenecks = (
        pd.DataFrame(rows).sort_values("Max_VOC", ascending=False)
        if rows else
        pd.DataFrame(columns=["ID1", "Max_VOC", "Tot_Flow", "Tot_VMT"])
    )

    print(f"  Flow table  → {flow_bin}")
    print(f"  VMT: {vmt:,.0f}   VHT: {vht:,.0f}")
    print(f"  Bottlenecks (V/C >= {vc_threshold}): {len(bottlenecks)}")
    if len(bottlenecks) > 0:
        print(bottlenecks.to_string(index=False))

    return {
        "VMT":            vmt,
        "VHT":            vht,
        "flow_bin":       flow_bin,
        "bottlenecks_df": bottlenecks,
    }
