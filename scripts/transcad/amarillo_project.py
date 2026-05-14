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
importlib.reload(m)

import os
import shutil
import pandas as pd
import caliperpy

from transcad.constants import MODEL_DIR
from transcad.caliper_4_step_model import (
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
# ──────────────────────────────────────────────────────────────────────────────
# FULL MODEL PIPELINE
# ──────────────────────────────────────────────────────────────────────────────

# %%
def run_full_model(
        dk: caliperpy.Gisdk,
        scenario_label:      str   = "Baseline",
        prod_output:         str   = "Script_Productions.bin",
        pa_output:           str   = "Script_PA.bin",
        skim_output:         str   = "Script_Skim.mtx",
        flow_output:         str   = "Script_Daily_Assign.bin",
        taz_bin:             str   = "taz.bin",
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
    gravity_base = os.path.splitext(gravity_output)[0] if gravity_output else "grav"
    od_base      = os.path.splitext(od_output)[0]      if od_output      else "od"
    gravity_output = f"{gravity_base}_{scenario_label}_{ts}.mtx"
    od_output      = f"{od_base}_{scenario_label}_{ts}.mtx"

    # ── Step 1: Trip Generation ───────────────────────────────────────────
    print("\n[1] Trip Generation")
    close_all_views(dk)
    taz_vw = open_taz(dk, taz_bin=taz_bin)
    prods_file, prod_vw = run_cross_classification(
        dk, taz_vw, output_file=prod_output, taz_bin=taz_bin    
    )

    if prod_rate_scale is not None:
        print(f"  Scaling productions by {prod_rate_scale:.3f}")
        for field in ["HBW_P", "HBNW_P", "NHB_P", "TRUCKTAXI_P"]:
            v = dk.GetDataVector(prod_vw + "|", field, None)
            dk.SetDataVector(prod_vw + "|", field, v * prod_rate_scale, None)

    run_attractions(dk, taz_vw)

    if attr_coeff_scale is not None:
        print(f"  Scaling attractions by {attr_coeff_scale:.3f}")
        for field in ["HBW_A", "HBNW_A", "NHB_A", "TRUCKTAXI_A"]:
            v = dk.GetDataVector(taz_vw + "|", field, None)
            dk.SetDataVector(taz_vw + "|", field, v * attr_coeff_scale, None)

    pa = run_balancing(dk, taz_vw, prod_vw, output_file=pa_output)

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

    # ── Step 5: Traffic Assignment ────────────────────────────────────────
    print("\n[5] Traffic Assignment")
    results = run_assignment(
        dk, net, od_file,
        flow_output       = flow_output,
        demand_multiplier = demand_multiplier,
    )
    results["scenario"] = scenario_label
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

# %%
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

# %%
def task_1c_lanes_needed(bottlenecks_df: pd.DataFrame,
                         lanes_per_capacity: float = 1800.0) -> pd.DataFrame:
    import math
    print("\n\n===  TASK 1C: LANES NEEDED AT BOTTLENECKS  ===")

    df = bottlenecks_df.copy()

    def extra_lanes(row):
        ab_voc  = row.get("AB_VOC")  or 0
        ba_voc  = row.get("BA_VOC")  or 0
        ab_flow = row.get("AB_Flow") or 0
        ba_flow = row.get("BA_Flow") or 0
        # Derive capacity from flow / VOC
        ab_cap = ab_flow / ab_voc if ab_voc > 0 else 0
        ba_cap = ba_flow / ba_voc if ba_voc > 0 else 0
        flow     = max(ab_flow, ba_flow)
        capacity = max(ab_cap,  ba_cap)
        if capacity == 0:
            return None
        shortfall = flow - capacity
        return int(math.ceil(shortfall / lanes_per_capacity)) if shortfall > 0 else 0

    df["Extra_Lanes_Needed"] = df.apply(extra_lanes, axis=1)
    show = [c for c in ["ID1", "AB_VOC", "BA_VOC", "AB_Flow", "BA_Flow",
                         "AB_VMT", "BA_VMT", "Extra_Lanes_Needed"]
            if c in df.columns]
    print(df[show].head(20).to_string(index=False))
    return df

# ──────────────────────────────────────────────────────────────────────────────
# TASK 3B — SENSITIVITY ANALYSIS
# ──────────────────────────────────────────────────────────────────────────────

# %%
def task_3b_sensitivity(dk: caliperpy.Gisdk, baseline_vmt: float) -> pd.DataFrame:
    print("\n\n===  TASK 3B: SENSITIVITY ANALYSIS  ===")
    rows = []

    tests = [
        dict(label="S1_ReduceProdRates_10pct",  prod_rate_scale=0.90),
        dict(label="S2_ReduceAttrCoeff_10pct",  attr_coeff_scale=0.90),
        dict(label="S3_HigherOccupancy",
             occupancy_overrides={"HBNW": 1.6, "NHB": 1.8}),
        dict(label="S4_Demand_10pct_Reduction", demand_multiplier=0.90),
    ]

    for t in tests:
        label = t.pop("label")
        res = run_full_model(
            dk,
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

# %%
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

    MAX_ITER   = 6
    prod_scale = 0.85
    attr_scale = 0.90
    hbnw_occ   = 1.70
    nhb_occ    = 2.00

    res = {}
    for i in range(1, MAX_ITER + 1):
        label = f"3C_iter{i}"
        print(f"\n  Iter {i}: prod={prod_scale:.2f} attr={attr_scale:.2f} "
              f"HBNW={hbnw_occ:.2f} NHB={nhb_occ:.2f}")

        res = run_full_model(
            dk,
            scenario_label      = label,
            prod_output         = f"{label}_Prod.bin",
            pa_output           = f"{label}_PA.bin",
            skim_output         = "Script_Skim.mtx",
            gravity_output      = f"{label}_PA.mtx",
            od_output           = f"{label}_OD.mtx",
            flow_output         = f"{label}_Flow.bin",
            prod_rate_scale     = prod_scale,
            attr_coeff_scale    = attr_scale,
            occupancy_overrides = {"HBNW": hbnw_occ, "NHB": nhb_occ},
        )

        pct = (res["VMT"] - baseline_vmt) / baseline_vmt * 100
        print(f"  → VMT {res['VMT']:,.0f}  ({pct:+.1f}%)")

        if res["VMT"] <= baseline_vmt:
            print(f"\n  ✓ Target achieved in iteration {i}!")
            break

        prod_scale -= 0.05
        attr_scale -= 0.05
        hbnw_occ   += 0.10
        nhb_occ    += 0.10
    else:
        print("\n  ✗ Target not met — reporting best result.")

    res["scenario"] = label
    return res


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

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