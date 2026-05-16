# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
# ---

# %%
import importlib
import transcad.caliper_4_step_model as m
import transcad.caliper_helpers as h

importlib.reload(m)
importlib.reload(h)

import os
import shutil
import pandas as pd
import caliperpy

from transcad.constants import MODEL_DIR
from transcad.caliper_4_step_model import (
    add_ie_ee_to_od,
    apply_special_attractions,
    apply_special_generators,
    run_cross_classification,
    run_attractions,
    run_balancing,
    build_network,
    run_skims,
    run_intrazonal,
    run_gravity,
    run_pa2od,
    run_assignment,
)
from transcad.caliper_helpers import (
    get_dk,
    open_taz,
    close_all_views,
    set_data_vector_scaled,
    view_mtx,
    view_bin,
    get_bottlenecks,
    scale_taz_fields,
    _delete_if_exists,
)
try: caliperpy.TransCAD.disconnect()
except: pass
import importlib
import time
importlib.reload(caliperpy)

# TAZ fields to scale for future scenario
GROWTH            = 1.20
GROWTH_FIELDS_HH  = ["HH"]
GROWTH_FIELDS_EMP = ["BASIC", "RETAIL", "SERVICE"]

dk = get_dk()


# ──────────────────────────────────────────────────────────────────────────────
# DEV: run individual steps (comment out when using run_full_model)
# ──────────────────────────────────────────────────────────────────────────────

# %%
# %%
# ──────────────────────────────────────────────────────────────────────────────
# FULL MODEL PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

def run_full_model(
        dk: caliperpy.Gisdk,
        scenario_label:      str   = "Baseline",
        taz_bin:             str   = "taz.bin",
        prod_output:         str   = "Script_Productions.bin",
        pa_output:           str   = "Script_PA.bin",
        skim_output:         str   = "Script_Skim.mtx",
        flow_output:         str   = "Script_Daily_Assign.bin",
        gravity_output:      str   = None,
        od_output:           str   = None,
        # Sensitivity levers
        prod_rate_scale:     float = None,   # Step 1: scale _P fields
        attr_coeff_scale:    float = None,   # Step 1: scale _A fields
        occupancy_overrides: dict  = None,   # Step 4: {purpose: occupancy}
        demand_multiplier:   float = 1.0,    # Step 5: scale OD demand
) -> dict:
    """
    Run the complete 4-step model pipeline for one scenario.
    Returns dict: {scenario, VMT, VHT, flow_bin, bottlenecks_df}
    """
    print(f"\n{'='*60}")
    print(f"  SCENARIO: {scenario_label}")
    print(f"{'='*60}")
    ts = str(int(time.time()))
    prod_base = os.path.splitext(prod_output)[0] if prod_output else "prod"
    prod_output = rf"ScriptOutput\{prod_base}_{scenario_label}_{ts}.bin"
    pa_base = os.path.splitext(pa_output)[0] if pa_output else "pa"
    pa_output = rf"ScriptOutput\{pa_base}_{scenario_label}_{ts}.bin"
    skim_base = os.path.splitext(skim_output)[0] if skim_output else "skim"
    skim_output = rf"ScriptOutput\{skim_base}_{scenario_label}_{ts}.mtx"
    flow_base = os.path.splitext(flow_output)[0] if flow_output else "flow"
    flow_output = rf"ScriptOutput\{flow_base}_{scenario_label}_{ts}.bin"
    gravity_base = os.path.splitext(gravity_output)[0] if gravity_output else "grav"
    od_base      = os.path.splitext(od_output)[0]      if od_output      else "od"
    gravity_output = rf"ScriptOutput\{gravity_base}_{scenario_label}_{ts}.mtx"
    od_output      = rf"ScriptOutput\{od_base}_{scenario_label}_{ts}.mtx"

    # ── Step 1: Trip Generation ───────────────────────────────────────────
    print("\n[1] Trip Generation")
    taz_vw = open_taz(dk, taz_bin=taz_bin)
    prods_file, prod_vw = run_cross_classification(
        dk, taz_vw, output_file=prod_output, taz_bin=taz_bin    
    )
    apply_special_generators(dk, prod_vw, taz_vw)

    if prod_rate_scale is not None:
        print(f"  Scaling productions by {prod_rate_scale:.3f}")
        for field in ["HBW_P"]:
            set_data_vector_scaled(dk, prod_vw + "|", field, prod_rate_scale)    
    
    run_attractions(dk, taz_vw)
    apply_special_attractions(dk, taz_vw)

    if attr_coeff_scale is not None:
        print(f"  Scaling attractions by {attr_coeff_scale:.3f}")
        for field in ["HBNW_A", "NHB_A"]:
            set_data_vector_scaled(dk, taz_vw + "|", field, attr_coeff_scale)

    hold_method = "WeightedSum" if attr_coeff_scale else "HoldProductions"        
    pa = run_balancing(dk, taz_vw, prod_vw, output_file=pa_output, hold_method=hold_method)

    # ── Step 2: Network & Skim ────────────────────────────────────────────
    print("\n[2] Network & Skim")
    net                  = build_network(dk)
    skim_file, skim_core = run_skims(dk, net, skim_output=skim_output)
    run_intrazonal(dk, skim_file, skim_core)

    # ── Step 3: Trip Distribution ─────────────────────────────────────────
    print("\n[3] Trip Distribution")
    grav = run_gravity(dk, pa, skim_file, skim_core, output_file=gravity_output)

    # ── Step 4: PA to OD ──────────────────────────────────────────────────
    print("\n[4] PA to OD")
    od_file = run_pa2od(dk, grav,
                        output_file         = od_output,
                        occupancy_overrides = occupancy_overrides)
    
    add_ie_ee_to_od(dk, od_file)
    if demand_multiplier != 1.0:
        print(f"  Scaling OD demand by {demand_multiplier:.3f}")
        od_matrix = dk.OpenMatrix(od_file, "True")
        cores = dk.GetMatrixCoreNames(od_matrix)
        for core in cores:
            mc      = dk.CreateMatrixCurrency(od_matrix, core, None, None, None)
            row_ids = dk.VectorToArray(dk.GetMatrixVector(mc, [["Index", "Row"]]))
            for row_id in row_ids:
                if row_id is None:
                    continue
                row_vec  = dk.VectorToArray(dk.GetMatrixVector(mc, [["Row", row_id]]))
                scaled   = [v * demand_multiplier if v is not None else 0.0 
                            for v in row_vec]
                dk.SetMatrixVector(mc, dk.ArrayToVector(scaled), [["Row", row_id]])
    # ── Step 5: Traffic Assignment ────────────────────────────────────────
    print("\n[5] Traffic Assignment")
    results = run_assignment(
        dk, net, od_file,
        flow_output       = flow_output,
    )
    results["scenario"] = scenario_label
    close_all_views(dk)
    
    return results


# ──────────────────────────────────────────────────────────────────────────────
# TASK 1A — BASELINE
# ──────────────────────────────────────────────────────────────────────────────

# %%
def task_1a_baseline(dk: caliperpy.Gisdk) -> dict:
    print("\n\n===  TASK 1A: BASELINE  ===")
    results = run_full_model(dk, scenario_label="1A_Baseline")

    bn = results["bottlenecks_df"]
    print(f"\n  Daily VMT: {results['VMT']:,.0f}")
    print(f"  Daily VHT: {results['VHT']:,.0f}")
    print(f"\n  Bottleneck links (V/C > 1.0): {len(bn)}")
    if len(bn) > 0:
        show = [c for c in ["ID1", "AB_Flow", "BA_Flow",
                             "AB_VOC", "BA_VOC",
                             "AB_VMT", "BA_VMT"] if c in bn.columns]        
        print(bn[show].head(20).to_string(index=False))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# TASK 1B — NO-BUILD FUTURE (20 % growth)
# ──────────────────────────────────────────────────────────────────────────────

def task_1b_no_build(dk: caliperpy.Gisdk, baseline_vmt: float) -> dict:
    print("\n\n===  TASK 1B: NO-BUILD FUTURE (20% growth)  ===")

    future_bin = os.path.join(MODEL_DIR, "taz_future.bin")
    scale_taz_fields(
        dk,
        taz_bin_path = os.path.join(MODEL_DIR, "taz.bin"),
        fields       = GROWTH_FIELDS_HH + GROWTH_FIELDS_EMP,
        factor       = GROWTH,
        output_bin   = future_bin,
    )

    # Copy taz.dbd to taz_future.dbd so open_taz() finds the right geometry
    future_dbd = os.path.join(MODEL_DIR, "taz_future.dbd")
    if not os.path.exists(future_dbd):
        shutil.copy2(os.path.join(MODEL_DIR, "taz.dbd"), future_dbd)

    results = run_full_model(
        dk,
        taz_bin        = "taz_future.bin",
        scenario_label = "1B_NoBuild_Future",
        prod_output    = "Future_Productions.bin",
        pa_output      = "Future_PA.bin",
        skim_output    = "Future_Skim.mtx",
        flow_output    = "Future_Daily_Assign.bin",
    )

    pct = (results["VMT"] - baseline_vmt) / baseline_vmt * 100
    bn  = results["bottlenecks_df"]
    print(f"\n  Future VMT: {results['VMT']:,.0f}  ({pct:+.1f}% vs baseline)")
    print(f"  Future VHT: {results['VHT']:,.0f}")
    print(f"  Future bottlenecks (V/C > 1.0): {len(bn)}")
    if len(bn) > 0:
        show = [c for c in ["ID1", "AB_Flow", "BA_Flow",
                             "AB_VOC", "BA_VOC",
                             "AB_VMT", "BA_VMT"] if c in bn.columns]
        print(bn[show].head(20).to_string(index=False))
    return results


# ──────────────────────────────────────────────────────────────────────────────
# TASK 1C — LANES NEEDED
# ──────────────────────────────────────────────────────────────────────────────

def task_1c_lanes_needed(bottlenecks_df, lanes_per_capacity=1800.0):
    import math
    print("\n\n===  TASK 1C: LANES NEEDED AT BOTTLENECKS  ===")
    df = bottlenecks_df.copy()

    def extra_lanes(row):
        flow = row.get("Tot_Flow") or 0
        voc  = row.get("Max_VOC")  or 0
        if voc == 0:
            return None
        capacity = flow / voc
        shortfall = flow - capacity
        return int(math.ceil(shortfall / lanes_per_capacity)) if shortfall > 0 else 0

    df["Extra_Lanes_Needed"] = df.apply(extra_lanes, axis=1)
    print(df.to_string(index=False))
    return df
# ──────────────────────────────────────────────────────────────────────────────
# TASK 3B — SENSITIVITY ANALYSIS
# ──────────────────────────────────────────────────────────────────────────────

def task_3b_sensitivity(dk: caliperpy.Gisdk, baseline_vmt: float) -> pd.DataFrame:
    print("\n\n===  TASK 3B: SENSITIVITY ANALYSIS  ===")
    rows = []

    tests = [
        dict(label="S1_ReduceProdRates_10pct",  prod_rate_scale=0.90),
        dict(label="S2_ReduceAttrCoeff_10pct",  attr_coeff_scale=0.99),
        dict(label="S3_HigherOccupancy",
             occupancy_overrides={"HBW": 1.2, "HBNW": 1.4, "NHB": 1.6}),
        dict(label="S4_Demand_10pct_Reduction", demand_multiplier=0.97),
    ]
    future_bin = os.path.join(MODEL_DIR, "taz_future.bin")
    if not os.path.exists(future_bin):
        scale_taz_fields(
            dk,
            os.path.join(MODEL_DIR, "taz.bin"),
            GROWTH_FIELDS_HH + GROWTH_FIELDS_EMP,
            GROWTH,
            future_bin,
        )


    for t in tests:
        label = t.pop("label")
        res = run_full_model(
            dk,
            taz_bin        = "taz_future.bin",
            scenario_label = label,
            prod_output    = f"{label}_Prod.bin",
            pa_output      = f"{label}_PA.bin",
            skim_output    = "Script_Skim.mtx",  # reuse baseline skim
            gravity_output = f"{label}_PA.mtx",
            od_output      = f"{label}_OD.mtx",
            flow_output    = f"{label}_Flow.bin",
            **t
        )
        pct = (res["VMT"] - baseline_vmt) / baseline_vmt * 100
        rows.append({
            "Scenario":       label,
            "VMT":            f"{res['VMT']:,.0f}",
            "VHT":            f"{res['VHT']:,.0f}",
            "VMT_change_pct": f"{pct:+.1f}%",
            "Bottlenecks":    len(res["bottlenecks_df"]),
        })

    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    return df


# ──────────────────────────────────────────────────────────────────────────────
# TASK 3C — COMBINED SCENARIO
# ──────────────────────────────────────────────────────────────────────────────

def task_3c_combined(dk: caliperpy.Gisdk, baseline_vmt: float) -> dict:
    print("\n\n===  TASK 3C: COMBINED SCENARIO (target VMT ≤ baseline)  ===")

    future_bin = os.path.join(MODEL_DIR, "taz_future.bin")
    if not os.path.exists(future_bin):
        scale_taz_fields(
            dk,
            os.path.join(MODEL_DIR, "taz.bin"),
            GROWTH_FIELDS_HH + GROWTH_FIELDS_EMP,
            GROWTH,
            future_bin,
        )

    MAX_ITER   = 10
    prod_scale = .99
    attr_scale = .9975
    hbw_occ   = 1.1 * 1.05
    hbnw_occ   = 1.3 * 1.05
    nhb_occ    = 1.5 * 1.05

    res = {}
    for i in range(1, MAX_ITER + 1):
        label = f"3C_iter{i}"
        print(f"\n  Iter {i}: prod={prod_scale:.2f} attr={attr_scale:.2f} "
              f"HBW={hbw_occ:.2f} " f"HBNW={hbnw_occ:.2f} NHB={nhb_occ:.2f}")

        res = run_full_model(
            dk,
            taz_bin        = "taz_future.bin",
            scenario_label      = label,
            prod_output         = f"{label}_Prod.bin",
            pa_output           = f"{label}_PA.bin",
            skim_output         = "Script_Skim.mtx",
            gravity_output      = f"{label}_PA.mtx",
            od_output           = f"{label}_OD.mtx",
            flow_output         = f"{label}_Flow.bin",
            prod_rate_scale     = prod_scale,
            attr_coeff_scale    = attr_scale,
            occupancy_overrides = {"HBW": hbw_occ, "HBNW": hbnw_occ, "NHB": nhb_occ},
        )

        pct = (res["VMT"] - baseline_vmt) / baseline_vmt * 100
        print(f"  → VMT {res['VMT']:,.0f}  ({pct:+.1f}%)")

        if res["VMT"] <= baseline_vmt:
            print(f"\n  ✓ Target achieved in iteration {i}!")
            break
        else:
            print("\n  ✗ Target not met — reporting best result.")

        prod_scale -= 0.01
        attr_scale -= 0.01
        hbw_occ   *= 1.05
        hbnw_occ   *= 1.05
        nhb_occ    *= 1.05

    res["scenario"] = label
    return res

# %%
# %%
# Quick test
def run_hourly_assignment(
        dk:             caliperpy.Gisdk,
        gravity_file:   str,
        net_file:       str,
        scenario_label: str  = "Hourly",
        hours:          list = None,          # None = all 24 hours
        occupancy_overrides: dict = None,
) -> dict:
    """
    For each hour (or a specified subset), run PA2OD using HourlyLookup.bin,
    add IE/EE external trips, run traffic assignment, and return results.

    Returns dict keyed by hour: {hour: {VMT, VHT, flow_bin, bottlenecks_df}}
    """
    import time as _time
    import collections
    import numpy as np

    if hours is None:
        hours = list(range(24))

    hourly_bin = os.path.join(MODEL_DIR, "HourlyLookup.bin")
    ie_mtx     = os.path.join(MODEL_DIR, "ie.mtx")
    ee_bin     = os.path.join(MODEL_DIR, "EE Trips.bin")

    occ = {"HBW": 1.1, "HBNW": 1.3, "NHB": 1.5, "TRUCKTAXI": 1.0}
    if occupancy_overrides:
        occ.update(occupancy_overrides)

    # Verify HourlyLookup fields
    vw_check = dk.OpenTable("HourlyCheck", "FFB", [hourly_bin, None])
    fields, _ = dk.GetFields(vw_check, "All")
    print(f"HourlyLookup fields: {fields}")
    dk.CloseView(vw_check)

    results = {}

    for hour in hours:
        ts    = str(int(_time.time()))
        label = f"{scenario_label}_H{hour:02d}"
        print(f"\n{'='*50}")
        print(f"  HOUR {hour:02d}:00 — {label}")
        print(f"{'='*50}")

        # ── PA2OD for this hour ───────────────────────────────────────────
        od_file = os.path.join(MODEL_DIR,
                    f"ScriptOutput/od_{label}_{ts}.mtx")
        _delete_if_exists(od_file)

        o = dk.CreateObject("Distribution.PA2OD", None)
        o.Matrix(gravity_file)
        o.LoadRateTable(hourly_bin)
        o.TimePeriod(hour, hour + 1)   # single hour slice
        o.Daily        = False
        o.ReportByHour = False         # one combined output for the hour

        # HBW, HBNW, NHB use hourly rates; TRUCKTAXI uses flat daily split
        o.AddPurpose({
            "Name":           "HBW",
            "DepartureField": "DEP_HBW",
            "ReturnField":    "RET_HBW",
            "Occupancy":      occ["HBW"],
        })
        o.AddPurpose({
            "Name":           "HBNW",
            "DepartureField": "DEP_HBNW",
            "ReturnField":    "RET_HBNW",
            "Occupancy":      occ["HBNW"],
        })
        o.AddPurpose({
            "Name":           "NHB",
            "DepartureField": "DEP_NHB",
            "ReturnField":    "RET_NHB",
            "Occupancy":      occ["NHB"],
        })
        # TRUCKTAXI — no hourly rates in lookup, use flat 1/24 share
        o.AddPurpose({
            "Name":      "TRUCKTAXI",
            "Occupancy": occ["TRUCKTAXI"],
        })

        o.OutputMatrix(od_file)
        ok = o.Run()
        if not ok:
            print(f"  WARNING: PA2OD failed for hour {hour} — skipping")
            continue
        print(f"  OD matrix → {od_file}")

        # ── Add IE/EE scaled to this hour ─────────────────────────────────
        # IE and EE are daily totals — scale by hourly fraction (1/24 approx)
        # A more accurate approach uses DEP_ALL from HourlyLookup
        vw_hl   = dk.OpenTable("HourlyLookup2", "FFB", [hourly_bin, None])
        dep_all = dk.VectorToArray(dk.GetDataVector(vw_hl + "|", "DEP_ALL", None))
        hour_vals = dk.VectorToArray(dk.GetDataVector(vw_hl + "|", "HOUR",   None))
        dk.CloseView(vw_hl)

        # Find the fraction for this hour
        hour_fraction = 1.0 / 24.0  # fallback
        for h, dep in zip(hour_vals, dep_all):
            if h is not None and int(float(h)) == hour and dep is not None:
                hour_fraction = float(dep) / 100.0
                break
        print(f"  Hour fraction (DEP_ALL): {hour_fraction:.4f}")

        # Add IE/EE cores to OD matrix scaled by hour fraction
        od_matrix = dk.OpenMatrix(od_file, "True")
        od_cores  = list(dk.GetMatrixCoreNames(od_matrix))

        if "IE (0-24)" not in od_cores:
            dk.AddMatrixCore(od_matrix, "IE (0-24)")
        if "EE (0-24)" not in od_cores:
            dk.AddMatrixCore(od_matrix, "EE (0-24)")

        # IE — scale daily matrix by hour fraction
        ie_matrix    = dk.OpenMatrix(ie_mtx, "True")
        ie_core_name = dk.GetMatrixCoreNames(ie_matrix)[0]
        ie_mc = dk.CreateMatrixCurrency(ie_matrix, ie_core_name, None, None, None)
        od_ie = dk.CreateMatrixCurrency(od_matrix, "IE (0-24)",  None, None, None)

        row_ids = dk.VectorToArray(dk.GetMatrixVector(ie_mc, [["Index", "Row"]]))
        for row_id in row_ids:
            if row_id is None:
                continue
            row_vec  = dk.VectorToArray(dk.GetMatrixVector(ie_mc, [["Row", row_id]]))
            scaled   = [v * hour_fraction if v is not None else 0.0
                        for v in row_vec]
            dk.SetMatrixVector(od_ie, dk.ArrayToVector(scaled), [["Row", row_id]])
        print("  IE added (scaled)")

        # EE — scale sparse table by hour fraction
        ee_vw   = dk.OpenTable("EETrips_h", "FFB", [ee_bin, None])
        origins = dk.VectorToArray(dk.GetDataVector(ee_vw + "|", "Origin",      None))
        dests   = dk.VectorToArray(dk.GetDataVector(ee_vw + "|", "Destination", None))
        flows   = dk.VectorToArray(dk.GetDataVector(ee_vw + "|", "Flow",        None))
        dk.CloseView(ee_vw)

        od_ee   = dk.CreateMatrixCurrency(od_matrix, "EE (0-24)", None, None, None)
        col_ids = dk.VectorToArray(dk.GetMatrixVector(od_ee, [["Index", "Column"]]))
        col_pos = {int(float(c)): i for i, c in enumerate(col_ids) if c is not None}

        row_flows = collections.defaultdict(dict)
        for o_id, d_id, f in zip(origins, dests, flows):
            if f is not None and f > 0:
                row_flows[int(float(o_id))][int(float(d_id))] = \
                    float(f) * hour_fraction

        for row_id, cell_dict in row_flows.items():
            vals = [0.0] * len(col_ids)
            for col_id, val in cell_dict.items():
                if col_id in col_pos:
                    vals[col_pos[col_id]] = val
            dk.SetMatrixVector(od_ee, dk.ArrayToVector(vals), [["Row", row_id]])
        print("  EE added (scaled)")

        # Verify totals
        total = 0
        for core in dk.GetMatrixCoreNames(od_matrix):
            mc  = dk.CreateMatrixCurrency(od_matrix, core, None, None, None)
            rs  = dk.VectorToArray(dk.GetMatrixVector(mc, [["Marginal", "Row Sum"]]))
            ct  = sum(x for x in rs if x is not None)
            print(f"    {core}: {ct:,.0f}")
            total += ct
        print(f"    Total: {total:,.0f}")

        # ── Assignment ────────────────────────────────────────────────────
        flow_output = f"ScriptOutput/flow_{label}_{ts}.bin"
        flow_bin    = os.path.join(MODEL_DIR, flow_output)
        _delete_if_exists(flow_bin)

        # Build TAZ→NodeID index
        node_bin = os.path.join(MODEL_DIR, "Network_.bin")
        try:
            views = dk.GetViews(None)[0] or []
            for vw in (views or []):
                if vw.lower().startswith("node"):
                    try: dk.CloseView(vw)
                    except: pass
        except: pass

        node_vw = dk.OpenTable("Nodes", "FFB", [node_bin, None])
        dk.SetView(node_vw)
        dk.SelectByQuery("Centroids", "Several",
                         "Select * where TAZ <> null", None)
        dk.CreateMatrixIndex(
            "TAZ to Node ID", od_matrix, "Both",
            node_vw + "|Centroids", "TAZ", "ID"
        )
        dk.CloseView(node_vw)

        net_db  = os.path.join(MODEL_DIR, "network.dbd")
        obj     = dk.CreateObject("Network.Assignment", None)
        obj.LayerDB     = net_db
        obj.Network     = net_file
        obj.Method      = "CUE"
        obj.Iterations  = 100
        obj.Convergence = 0.0001
        obj.FlowTable   = flow_bin

        obj.ResetClasses()
        obj.DemandMatrix({
            "MatrixFile":  od_file,
            "RowIndex":    "TAZ to Node ID",
            "ColumnIndex": "TAZ to Node ID",
        })
        all_cores = dk.GetMatrixCoreNames(od_matrix)
        for core in all_cores:
            obj.AddClass({"Demand": core})

        obj.DelayFunction = {
            "Function": "bpr.vdf",
            "Fields":   ["Time", "Capacity", "Alpha", "Beta", "None"],
        }

        ok = obj.Run()
        if not ok:
            print(f"  WARNING: Assignment failed for hour {hour}")
            del obj
            continue

        task_results = obj.GetTaskResults()
        result_dict  = dict(task_results)
        vmt = float(result_dict.get("VMT w/o Centroids",
                    result_dict.get("Total VMT", 0)))
        vht = float(result_dict.get("VHT w/o Centroids",
                    result_dict.get("Total VHT", 0)))
        del obj

        # Bottlenecks
        flow_vw_name = f"Flow_H{hour:02d}_{ts}"
        try: dk.CloseView(flow_vw_name)
        except: pass
        flow_vw      = dk.OpenTable(flow_vw_name, "FFB", [flow_bin, None])
        max_voc_vals = dk.VectorToArray(
                           dk.GetDataVector(flow_vw + "|", "Max_VOC", None))
        id1_vals     = dk.VectorToArray(
                           dk.GetDataVector(flow_vw + "|", "ID1",     None))
        tot_flow     = dk.VectorToArray(
                           dk.GetDataVector(flow_vw + "|", "Tot_Flow",None))
        tot_vmt_vals = dk.VectorToArray(
                           dk.GetDataVector(flow_vw + "|", "Tot_VMT", None))
        try: dk.CloseView(flow_vw)
        except: pass

        rows = []
        for id1, voc, flow, tvmt in zip(id1_vals, max_voc_vals,
                                         tot_flow, tot_vmt_vals):
            if voc is not None and float(voc) >= 1.0:
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

        print(f"  VMT: {vmt:,.0f}   VHT: {vht:,.0f}")
        print(f"  Bottlenecks (V/C >= 1.0): {len(bottlenecks)}")
        if len(bottlenecks) > 0:
            print(bottlenecks.to_string(index=False))

        results[hour] = {
            "hour":           hour,
            "VMT":            vmt,
            "VHT":            vht,
            "flow_bin":       flow_bin,
            "bottlenecks_df": bottlenecks,
            "od_file":        od_file,
        }

    # ── Summary table ─────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  HOURLY SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Hour':>6}  {'VMT':>12}  {'VHT':>10}  {'Bottlenecks':>12}")
    for h, r in sorted(results.items()):
        print(f"  {h:02d}:00   {r['VMT']:>12,.0f}  "
              f"{r['VHT']:>10,.0f}  {len(r['bottlenecks_df']):>12}")

    return results
# %%

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

# %%
# %%
def main():
    baseline     = task_1a_baseline(dk)
    baseline_vmt = baseline["VMT"]
    baseline_vht = baseline["VHT"]

    future   = task_1b_no_build(dk, baseline_vmt)
    lanes_df = task_1c_lanes_needed(future["bottlenecks_df"])
    sens_df  = task_3b_sensitivity(dk, baseline_vmt)
    combined = task_3c_combined(dk, baseline_vmt)

    print("\n\n" + "="*60)
    print("  FINAL SUMMARY")
    print("="*60)
    print("\nLanes needed:")
    print(lanes_df.to_string(index=False))
    for label, vmt, vht in [
        ("1A Baseline",          baseline_vmt,       baseline_vht),
        ("1B No-Build Future",   future["VMT"],       future["VHT"]),
        ("3C Combined",          combined.get("VMT"), combined.get("VHT")),
    ]:
        pct = (vmt - baseline_vmt) / baseline_vmt * 100 if vmt else 0
        print(f"  {label:<25}  VMT: {vmt:>12,.0f}  ({pct:+.1f}%)  "
              f"VHT: {vht:>10,.0f}")

    print("\nSensitivity:")
    print(sens_df.to_string(index=False))


if __name__ == "__main__":
    main()
# %%
# %%
