# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
# ---

# %% [markdown]
# # Amarillo 4-Step Travel Demand Model
#
# Covers:
#   - Task 1A: Baseline (current) model run → VMT, VHT, V/C bottlenecks
#   - Task 1B: No-Build future scenario (20 % growth applied to TAZ data)
#   - Task 1C: Lane addition estimate at bottlenecks
#   - Task 3B: Single-input sensitivity runs (one input changed per step)
#   - Task 3C: Combined multi-input scenario targeting VMT ≤ baseline
#
# API reference: TransCAD 10.0 GISDK Help
#   GetDBInfo(db)        → [scope, label, revision]
#   GetDBLayers(db)      → [layer_name, ...]
#   CreateMap(name, [[option, value], ...])
#   AddLayer(map, name, db, db_layer)
#   OpenTable(name, "FFB", [path, None])
#   GetDataVector(viewset, field, None)
#   SetDataVector(viewset, field, vector, None)
#   VectorStatistic(vector, stat, None)
#   GetRecordCount(view, None)
#   CloseView(view)

# %%
%load_ext autoreload
%autoreload 2

import os
import sys
import shutil
from pathlib import Path
import pandas as pd
import caliperpy

from transcad.constants import MODEL_DIR
from transcad.run_cross_classification import run_attractions, run_balancing, run_cross_classification
from transcad.caliper_helpers import get_bottlenecks, get_dk, open_taz
from transcad.caliper_helpers import scale_taz_fields, sum_flow_field


# TAZ fields that represent households / employment (scale for future scenario)
# Adjust these names to match the actual field names in taz.dbd / taz.bin
GROWTH = 1.20   # 20 % population and employment growth
GROWTH_FIELDS_HH   = ["HH"]                          # household count field
GROWTH_FIELDS_EMP  = ["BASIC", "RETAIL", "SERVICE"]  # employment count fields

dk = get_dk()

# %%

taz_vw          = open_taz(dk)                          # open once
prods_file, prod_vw = run_cross_classification(dk, taz_vw)
run_attractions(dk, taz_vw)  
pa = run_balancing(dk, taz_vw, prod_vw)                            # reuse same view
# %%

# view_bin(dk, taz_vw)
# %%

def build_network(dk: caliperpy.Gisdk, net_output: str = "Script_Network.net") -> str:
    """
    Network.Create + Network.Settings
    Docs: GISDK/api/networksettings.htm
    """
    net_file = os.path.join(MODEL_DIR, net_output)

    net_obj = dk.CreateObject("Network.Create")
    net_obj.LayerDB        = os.path.join(MODEL_DIR, "network.dbd")
    net_obj.TimeUnits      = "Minutes"
    net_obj.OutNetworkName = net_file

    net_obj.AddLinkField({"Name": "Time",     "Field": "TIME",
                           "IsTimeField": True})
    net_obj.AddLinkField({"Name": "Capacity", "Field": ["AB_CAPACITY",
                                                          "BA_CAPACITY"]})
    net_obj.AddLinkField({"Name": "Alpha",    "Field": "ALPHA"})
    net_obj.AddLinkField({"Name": "Beta",     "Field": "BETA"})

    ok = net_obj.Run()
    if not ok:
        raise RuntimeError("Network.Create failed.")

    net_set = dk.CreateObject("Network.Settings", {"Network": net_file})
    net_set.CentroidFilter = "TAZ <> null"
    net_set.UseLinkTypes   = True
    ok2 = net_set.Run()
    if not ok2:
        raise RuntimeError("Network.Settings failed.")
    print(f"  Network → {net_file}")
    return net_file


def run_skims(dk: caliperpy.Gisdk, net_file: str, skim_output: str = "Script_Skim.mtx") -> str:
    """
    Network.Skims — all-pairs shortest path travel time matrix.
    Docs: GISDK/api/networkskims.htm
    """
    skim_file = os.path.join(MODEL_DIR, skim_output)
    obj = dk.CreateObject("Network.Skims")
    obj.Network      = net_file
    obj.LayerDB      = os.path.join(MODEL_DIR, "network.dbd")
    obj.Origins      = "TAZ <> null"
    obj.Destinations = "TAZ <> null"
    obj.Minimize     = "Time"
    obj.AddSkimField(["Time", "All"])
    obj.OutputMatrix({
        "MatrixFile":  skim_file,
        "Matrix":      "Shortest Path",
        "Compression": True,
    })
    ok = obj.Run()
    if not ok:
        raise RuntimeError("Network.Skims failed.")
    print(f"  Skim matrix → {skim_file}")
    return skim_file


def run_intrazonal(dk: caliperpy.Gisdk, skim_file: str):
    """
    Distribution.Intrazonal — fill diagonal of skim matrix.
    Docs: GISDK/api/distributionintrazonal.htm
    Factor = 0.5 per tutorial (half the average of nearest neighbours).
    """
    obj = dk.CreateObject("Distribution.Intrazonal")
    obj.Factor    = 0.5
    obj.Neighbors = 3
    obj.SetMatrix({"MatrixFile": skim_file, "MatrixCore": "Shortest Path"})
    ok = obj.Run()
    if not ok:
        raise RuntimeError("Distribution.Intrazonal failed.")
    print("  Intrazonal times filled.")


# %%

def run_gravity(dk: caliperpy.Gisdk, pa_file: str, skim_file: str,
                output_file: str = "Script_PA.mtx") -> str:
    """
    Distribution.Gravity — doubly-constrained gravity model.
    Docs: GISDK/api/distributiongravity.htm
    """
    gravity_out = os.path.join(MODEL_DIR, output_file)
    sp_mat = {
        "MatrixFile": skim_file,
        "Matrix":     "Shortest Path",
        "RowIndex":   "Origin",
        "ColIndex":   "Destination",
    }
    ff_table = os.path.join(MODEL_DIR, "FFDATA.DBF")

    obj = dk.CreateObject("Distribution.Gravity")
    obj.CalculateTLD = True
    obj.AddDataSource({"TableName": pa_file})

    for purpose, ff_field in [("HBW",      "HBW"),
                               ("HBNW",     "HBNW"),
                               ("NHB",      "NHB"),
                               ("TRUCKTAXI","TRUCKTAXI")]:
        obj.AddPurpose({
            "Name":            purpose,
            "Production":      purpose + "_P",
            "Attraction":      purpose + "_A",
            "ConstraintType":  "Doubly",
            "Iterations":      20,
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
    print(f"  Gravity matrix → {gravity_out}")
    return gravity_out


# %%

def run_pa2od(dk: caliperpy.Gisdk, gravity_file: str,
              output_file: str = "Script_OD.mtx") -> str:
    """
    Distribution.PA2OD — convert PA matrix to OD vehicle trips.
    Docs: GISDK/api/distributionpa2od.htm
    """
    od_out = os.path.join(MODEL_DIR, output_file)
    o = dk.CreateObject("Distribution.PA2OD")
    o.Matrix(gravity_file)
    o.Daily        = True
    o.ReportByHour = False

    # Occupancy: HBW=1.1, HBNW=1.3, NHB=1.5, TRUCKTAXI=1.0 (tutorial p.28)
    o.AddPurpose({"Name": "HBW",       "Occupancy": 1.1})
    o.AddPurpose({"Name": "HBNW",      "Occupancy": 1.3})
    o.AddPurpose({"Name": "NHB",       "Occupancy": 1.5})
    o.AddPurpose({"Name": "TRUCKTAXI", "Occupancy": 1.0})

    o.OutputMatrix(od_out)
    ok = o.Run()
    if not ok:
        raise RuntimeError("Distribution.PA2OD failed.")
    print(f"  OD matrix → {od_out}")
    return od_out


# %%

def run_assignment(dk: caliperpy.Gisdk, net_file: str, od_file: str,
                   flow_output: str = "Script_Daily_Assign.bin",
                   demand_multiplier: float = 1.0) -> dict:
    """
    Network.Assignment — User Equilibrium (CUE) with BPR delay function.
    Docs: GISDK/api/assignment/assignment.htm

    demand_multiplier: scale OD matrix demand (use for sensitivity tests).
    Returns dict with keys: VMT, VHT, flow_bin, bottlenecks_df.
    """
    flow_bin = os.path.join(MODEL_DIR, flow_output)

    obj = dk.CreateObject("Network.Assignment")
    obj.LayerDB     = os.path.join(MODEL_DIR, "network.dbd")
    obj.Network     = net_file
    obj.Method      = "CUE"
    obj.Iterations  = 100
    obj.Convergence = 0.0001
    obj.FlowTable   = flow_bin

    if demand_multiplier != 1.0:
        obj.DemandMultiplier = demand_multiplier

    # OD matrix — QuickSum is the sum of all purpose cores.
    # RowIndex / ColumnIndex: the index built from TAZ → node ID mapping.
    obj.DemandMatrix({
        "MatrixFile":  od_file,
        "Matrix":      "QuickSum",
        "RowIndex":    "TAZ to Node ID",
        "ColumnIndex": "TAZ to Node ID",
    })
    obj.AddClass({"Demand": "QuickSum"})

    # BPR volume-delay function
    # Fields order: Time, Capacity, Alpha, Beta, Preload
    obj.DelayFunction = {
        "Function": "bpr.vdf",
        "Fields":   ["Time", "Capacity", "Alpha", "Beta", "None"],
        "Defaults": ["0",    "1800",     "0.15",  "4",    "0"],
    }

    ok = obj.Run()
    if not ok:
        raise RuntimeError("Network.Assignment failed.")

    task_results = obj.GetTaskResults()
    # GetFlowTable() returns a table object; .View() opens it as a view name
    flow_vw = obj.GetFlowTable().View()
    ab_flow = dk.GetDataVector(flow_vw, "AB_Flow", None)
    ba_flow = dk.GetDataVector(flow_vw, "BA_Flow", None)
    ab_time = dk.GetDataVector(flow_vw, "AB_Time",  None)
    ba_time = dk.GetDataVector(flow_vw, "BA_Time",  None)
    length  = dk.GetDataVector(flow_vw, "Length",   None)
    dk.CloseView(flow_vw)

    # VMT = sum( (AB_Flow + BA_Flow) * Length )
    # VHT = sum( AB_Flow * AB_Time/60 + BA_Flow * BA_Time/60 )
    # (TransCAD TIME field is in minutes)
    try:
        vmt = float(task_results.VMT)
        vht = float(task_results.VHT)
    except Exception:
        # Fallback: compute from flow table vectors
        vmt = sum((a + b) * l for a, b, l in zip(ab_flow, ba_flow, length)
                  if a is not None and b is not None and l is not None)
        vht = sum(a * t / 60 + b * s / 60
                  for a, b, t, s in zip(ab_flow, ba_flow, ab_time, ba_time)
                  if a is not None and b is not None)

    bottlenecks = get_bottlenecks(dk, flow_bin, vc_threshold=1.0)

    print(f"  Flow table → {flow_bin}")
    print(f"  VMT: {vmt:,.0f}   VHT: {vht:,.0f}")
    print(f"  Bottlenecks (V/C > 1): {len(bottlenecks)} links")

    return {
        "VMT":           vmt,
        "VHT":           vht,
        "flow_bin":      flow_bin,
        "bottlenecks_df": bottlenecks,
    }

# %%

def run_full_model(dk: caliperpy.Gisdk,
                   scenario_label:   str   = "Baseline",
                   taz_dbd:          str   = "taz.dbd",
                   prod_output:      str   = "Script_Productions.bin",
                   pa_output:        str   = "Script_PA.bin",
                   skim_output:      str   = "Script_Skim.mtx",
                   gravity_output:   str   = "Script_PA.mtx",
                   od_output:        str   = "Script_OD.mtx",
                   flow_output:      str   = "Script_Daily_Assign.bin",
                   # Sensitivity levers (pass non-None to override)
                   prod_rate_scale:  float = None,   # scale all prod rates
                   attr_coeff_scale: float = None,   # scale all attr coefficients
                   ff_scale:         float = None,   # scale friction factors (NOT yet implemented)
                   occupancy_overrides: dict = None, # {"HBW": 1.3, ...}
                   demand_multiplier: float = 1.0,
                   ) -> dict:
    """
    Run the complete 4-step model pipeline for one scenario.
    Returns a results dict.

    Sensitivity levers:
      prod_rate_scale    – multiply PRATES.BIN values by this factor
                           (simulates telework / changed trip rates)
      attr_coeff_scale   – multiply attraction regression coefficients
                           (simulates land-use changes)
      occupancy_overrides– dict of purpose→occupancy overrides for PA2OD
                           (simulates carpool / mode shift)
      demand_multiplier  – scale the entire OD matrix before assignment
                           (quick approximation of demand change)
    """
    print(f"\n{'='*60}")
    print(f"  SCENARIO: {scenario_label}")
    print(f"{'='*60}")

    print("\n[1] Trip Generation")
    taz_vw = open_taz(dk)
    prods_file, prod_vw = run_cross_classification(dk, taz_vw)

    if prod_rate_scale is not None:
        # Scale the production output vectors directly
        vw = dk.OpenTable("ScaleProd", "FFB", [prod_vw, None])
        for field in ["HBW_P", "HBNW_P", "NHB_P", "TRUCKTAXI_P"]:
            v = dk.GetDataVector(vw, field, None)
            dk.SetDataVector(vw, field, v * prod_rate_scale, None)
        dk.CloseView(vw)
        print(f"  Production rates scaled by {prod_rate_scale:.3f}")

    run_attractions(dk, taz_vw)
    
    if attr_coeff_scale is not None:
        vw = dk.OpenTable("ScaleAttr", "FFB", [prod_vw, None])
        for field in ["HBW_A", "HBNW_A", "NHB_A", "TRUCKTAXI_A"]:
            v = dk.GetDataVector(vw, field, None)
            dk.SetDataVector(vw, field, v * attr_coeff_scale, None)
        dk.CloseView(vw)
        print(f"  Attraction values scaled by {attr_coeff_scale:.3f}")

    pa = run_balancing(dk, taz_vw, prod_vw)      # reuse same view
    # ── Step 2: Network + Skim ────────────────────────────────────────
    print("\n[2] Network & Skim")
    net  = build_network(dk)
    skim = run_skims(dk, net, skim_output=skim_output)
    run_intrazonal(dk, skim)

    # ── Step 3: Trip Distribution ─────────────────────────────────────
    print("\n[3] Trip Distribution")
    grav = run_gravity(dk, pa, skim, output_file=gravity_output)

    # ── Step 4: PA to OD ──────────────────────────────────────────────
    print("\n[4] PA to OD")
    # Build dynamic occupancy kwargs
    occ = {"HBW": 1.1, "HBNW": 1.3, "NHB": 1.5, "TRUCKTAXI": 1.0}
    if occupancy_overrides:
        occ.update(occupancy_overrides)

    od_out = os.path.join(MODEL_DIR, od_output)
    o = dk.CreateObject("Distribution.PA2OD")
    o.Matrix(grav)
    o.Daily = True
    o.ReportByHour = False
    for purpose, occupancy in occ.items():
        o.AddPurpose({"Name": purpose, "Occupancy": occupancy})
    o.OutputMatrix(od_out)
    ok = o.Run()
    if not ok:
        raise RuntimeError("Distribution.PA2OD failed.")
    print(f"  OD matrix → {od_out}")

    # ── Step 5: Traffic Assignment ────────────────────────────────────
    print("\n[5] Traffic Assignment")
    results = run_assignment(dk, net, od_out,
                             flow_output=flow_output,
                             demand_multiplier=demand_multiplier)
    results["scenario"] = scenario_label
    return results


# %%

def task_1a_baseline(dk: caliperpy.Gisdk) -> dict:
    """
    Run the model on the existing taz.dbd with no modifications.
    Reports: VMT, VHT, V/C map bottlenecks (daily).
    """
    print("\n\n===  TASK 1A: BASELINE  ===")
    results = run_full_model(dk, scenario_label="1A_Baseline")

    vmt = results["VMT"]
    vht = results["VHT"]
    bn  = results["bottlenecks_df"]

    print(f"\n  Daily VMT: {vmt:,.0f}")
    print(f"  Daily VHT: {vht:,.0f}")
    print(f"\n  Bottleneck links (V/C > 1.0):")
    if len(bn) > 0:
        print(bn[["ID1", "AB_Flow", "BA_Flow", "AB_VOC", "BA_VOC",
                   "AB_CAPACITY", "BA_CAPACITY"]].head(20).to_string(index=False))
    else:
        print("  None found.")
    return results




# %%

def task_1b_no_build(dk: caliperpy.Gisdk, baseline_vmt: float) -> dict:
    """
    Scale all household and employment fields in taz by GROWTH=1.20,
    then run the full model.  Uses a copy of the taz data so the original
    is never modified.
    """
    print("\n\n===  TASK 1B: NO-BUILD FUTURE (20% growth)  ===")

    # Create a scaled copy of taz.bin (the attribute table behind taz.dbd)
    # TransCAD .dbd files have a companion .bin — scale that, then redirect
    # the model to use the scaled version.
    future_taz_bin = os.path.join(MODEL_DIR, "taz_future.bin")
    scale_taz_fields(
        dk,
        taz_bin_path = os.path.join(MODEL_DIR, "taz.bin"),
        fields       = GROWTH_FIELDS_HH + GROWTH_FIELDS_EMP,
        factor       = GROWTH,
        output_bin   = future_taz_bin,
    )

    # Also need to copy taz.dbd → taz_future.dbd pointing at the new .bin
    future_taz_dbd = os.path.join(MODEL_DIR, "taz_future.dbd")
    if not os.path.exists(future_taz_dbd):
        shutil.copy2(os.path.join(MODEL_DIR, "taz.dbd"), future_taz_dbd)
    # Note: if taz.dbd embeds the data, use dk.ExportView to create a fresh .dbd.
    # For this project taz.bin is assumed to be the editable attribute file.

    results = run_full_model(
        dk,
        scenario_label = "1B_NoBuild_Future",
        taz_dbd        = "taz_future.dbd",
        prod_output    = "Future_Productions.bin",
        pa_output      = "Future_PA.bin",
        skim_output    = "Future_Skim.mtx",
        gravity_output = "Future_PA.mtx",
        od_output      = "Future_OD.mtx",
        flow_output    = "Future_Daily_Assign.bin",
    )

    vmt = results["VMT"]
    vht = results["VHT"]
    bn  = results["bottlenecks_df"]
    pct_change_vmt = (vmt - baseline_vmt) / baseline_vmt * 100

    print(f"\n  Future Daily VMT : {vmt:,.0f}  ({pct_change_vmt:+.1f}% vs baseline)")
    print(f"  Future Daily VHT : {vht:,.0f}")
    print(f"\n  Future Bottleneck links (V/C > 1.0):")
    if len(bn) > 0:
        print(bn[["ID1", "AB_Flow", "BA_Flow", "AB_VOC", "BA_VOC",
                   "AB_CAPACITY", "BA_CAPACITY"]].head(20).to_string(index=False))
    else:
        print("  None found.")
    return results


# %%

def task_1c_lanes_needed(bottlenecks_df: pd.DataFrame,
                         lanes_per_capacity: float = 1800.0) -> pd.DataFrame:
    """
    For each bottleneck estimate the additional lanes needed:
        extra_lanes = ceil( (flow - capacity) / lanes_per_capacity )

    Returns augmented DataFrame with column 'Extra_Lanes_Needed'.
    lanes_per_capacity: vehicles/hour per lane (default 1800, typical urban).
    """
    print("\n\n===  TASK 1C: LANES NEEDED AT BOTTLENECKS  ===")
    import math

    df = bottlenecks_df.copy()

    def extra_lanes(row):
        flow     = max(row.get("AB_Flow", 0) or 0,
                       row.get("BA_Flow", 0) or 0)
        capacity = max(row.get("AB_CAPACITY", 0) or 0,
                       row.get("BA_CAPACITY", 0) or 0)
        if capacity == 0:
            return None
        shortfall = flow - capacity
        return int(math.ceil(shortfall / lanes_per_capacity)) if shortfall > 0 else 0

    df["Extra_Lanes_Needed"] = df.apply(extra_lanes, axis=1)
    show_cols = ["ID1", "AB_VOC", "BA_VOC", "AB_Flow", "BA_Flow",
                 "AB_CAPACITY", "BA_CAPACITY", "Extra_Lanes_Needed"]
    print(df[show_cols].head(20).to_string(index=False))
    return df


# %%

def task_3b_sensitivity(dk: caliperpy.Gisdk, baseline_vmt: float) -> pd.DataFrame:
    """
    Run four sensitivity tests, one per model step:

      S1 (Step 1): Reduce HBW production rates by 10 %  
                   → simulates telework / reduced trip-making
      S2 (Step 1): Reduce attraction coefficients by 10 %  
                   → simulates mixed-use / reduced attraction
      S3 (Step 3): Increase occupancy (HBNW 1.3→1.6, NHB 1.5→1.8)  
                   → simulates carpooling policy
      S4 (Step 5): Apply 90 % demand multiplier  
                   → simulates overall 10 % demand reduction
    """
    print("\n\n===  TASK 3B: SENSITIVITY ANALYSIS  ===")
    rows = []

    tests = [
        dict(label="S1_ReduceProdRates_10pct",
             prod_rate_scale=0.90),
        dict(label="S2_ReduceAttrCoeff_10pct",
             attr_coeff_scale=0.90),
        dict(label="S3_HigherOccupancy",
             occupancy_overrides={"HBNW": 1.6, "NHB": 1.8}),
        dict(label="S4_Demand_10pct_Reduction",
             demand_multiplier=0.90),
    ]

    for t in tests:
        label = t.pop("label")
        res = run_full_model(
            dk,
            scenario_label = label,
            prod_output    = f"{label}_Prod.bin",
            pa_output      = f"{label}_PA.bin",
            skim_output    = "Script_Skim.mtx",   # reuse baseline skim
            gravity_output = f"{label}_PA.mtx",
            od_output      = f"{label}_OD.mtx",
            flow_output    = f"{label}_Flow.bin",
            **t
        )
        pct = (res["VMT"] - baseline_vmt) / baseline_vmt * 100
        rows.append({
            "Scenario":         label,
            "VMT":              f"{res['VMT']:,.0f}",
            "VHT":              f"{res['VHT']:,.0f}",
            "VMT_change_pct":   f"{pct:+.1f}%",
            "Bottlenecks":      len(res["bottlenecks_df"]),
        })

    df = pd.DataFrame(rows)
    print("\n  Sensitivity Results:")
    print(df.to_string(index=False))
    return df


# %%

def task_3c_combined(dk: caliperpy.Gisdk, baseline_vmt: float) -> dict:
    """
    Simultaneously change inputs from at least three of the four steps to
    keep VMT ≤ baseline while accommodating 20 % growth.

    Strategy (justification in report):
      Step 1 – Production: reduce HBW rate 15 % (telework policy)
      Step 1 – Attraction: reduce retail attraction 10 % (online shopping)
      Step 4 – Occupancy: raise HBNW 1.3→1.7, NHB 1.5→2.0 (carpool incentive)
      Step 5 – Demand: 20 % future growth already baked into TAZ data,
               but higher occupancy converts person-trips to fewer vehicles.

    If VMT target is not met, tighten levers and re-run.
    The loop below tries up to MAX_ITER attempts, tightening by 5 % each pass.
    """
    print("\n\n===  TASK 3C: COMBINED SCENARIO (target VMT ≤ baseline)  ===")

    # Start with 20 % growth TAZ data
    future_taz_bin = os.path.join(MODEL_DIR, "taz_future.bin")
    if not os.path.exists(future_taz_bin):
        scale_taz_fields(
            dk, os.path.join(MODEL_DIR, "taz.bin"),
            GROWTH_FIELDS_HH + GROWTH_FIELDS_EMP,
            GROWTH, future_taz_bin
        )

    MAX_ITER = 6
    prod_scale  = 0.85   # 15 % reduction in production rates
    attr_scale  = 0.90   # 10 % reduction in attraction coefficients
    hbnw_occ    = 1.70
    nhb_occ     = 2.00
    tighten_by  = 0.05

    for iteration in range(1, MAX_ITER + 1):
        label = f"3C_Combined_iter{iteration}"
        print(f"\n  Iteration {iteration}: prod_scale={prod_scale:.2f}  "
              f"attr_scale={attr_scale:.2f}  "
              f"HBNW_occ={hbnw_occ:.2f}  NHB_occ={nhb_occ:.2f}")

        res = run_full_model(
            dk,
            scenario_label    = label,
            taz_dbd           = "taz_future.dbd",
            prod_output       = f"{label}_Prod.bin",
            pa_output         = f"{label}_PA.bin",
            skim_output       = "Script_Skim.mtx",
            gravity_output    = f"{label}_PA.mtx",
            od_output         = f"{label}_OD.mtx",
            flow_output       = f"{label}_Flow.bin",
            prod_rate_scale   = prod_scale,
            attr_coeff_scale  = attr_scale,
            occupancy_overrides = {"HBNW": hbnw_occ, "NHB": nhb_occ},
        )

        vmt = res["VMT"]
        pct = (vmt - baseline_vmt) / baseline_vmt * 100
        print(f"  → VMT {vmt:,.0f}  ({pct:+.1f}% vs baseline {baseline_vmt:,.0f})")

        if vmt <= baseline_vmt:
            print(f"\n  ✓ Target achieved in iteration {iteration}!")
            res["scenario"]         = label
            res["prod_rate_scale"]  = prod_scale
            res["attr_coeff_scale"] = attr_scale
            res["hbnw_occ"]         = hbnw_occ
            res["nhb_occ"]          = nhb_occ
            return res

        # Tighten levers for next iteration
        prod_scale -= tighten_by
        attr_scale -= tighten_by
        hbnw_occ   += 0.10
        nhb_occ    += 0.10

    print("\n  ✗ Target not met within iteration limit — report best result.")
    return res


# %%

def main():
    # ── Task 1A: Baseline ─────────────────────────────────────────────
    baseline = task_1a_baseline(dk)
    baseline_vmt = baseline["VMT"]
    baseline_vht = baseline["VHT"]

    # ── Task 1B: No-Build Future ──────────────────────────────────────
    future = task_1b_no_build(dk, baseline_vmt)

    # ── Task 1C: Lane additions needed at future bottlenecks ──────────
    lanes_df = task_1c_lanes_needed(future["bottlenecks_df"])

    # ── Task 3B: Sensitivity analysis ────────────────────────────────
    sensitivity_df = task_3b_sensitivity(dk, baseline_vmt)

    # ── Task 3C: Combined scenario ────────────────────────────────────
    combined = task_3c_combined(dk, baseline_vmt)

    # ── Summary table ─────────────────────────────────────────────────
    print("\n\n" + "="*60)
    print("  FINAL SUMMARY")
    print("="*60)
    rows = [
        ("1A Baseline",           baseline_vmt,       baseline_vht),
        ("1B No-Build Future",    future["VMT"],       future["VHT"]),
        ("3C Combined Scenario",  combined.get("VMT"), combined.get("VHT")),
    ]
    for label, vmt, vht in rows:
        pct = (vmt - baseline_vmt) / baseline_vmt * 100 if vmt else 0
        print(f"  {label:<30}  VMT: {vmt:>12,.0f}  ({pct:+.1f}%)   "
              f"VHT: {vht:>10,.0f}")

    print("\n  Sensitivity results:")
    print(sensitivity_df.to_string(index=False))

    print("\n  Lanes needed at future bottlenecks (top 10):")
    show_cols = ["ID1", "max_VOC", "AB_Flow", "AB_CAPACITY", "Extra_Lanes_Needed"]
    show_cols = [c for c in show_cols if c in lanes_df.columns]
    print(lanes_df[show_cols].head(10).to_string(index=False))


if __name__ == "__main__":
    main()