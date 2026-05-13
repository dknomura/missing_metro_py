# %%
import caliperpy
from transcad.constants import MODEL_DIR
from transcad.caliper_helpers import _delete_if_exists, add_field


import os
def run_cross_classification(
        dk: caliperpy.Gisdk,
        taz_file:     str  = "taz.dbd",
        output_file:  str  = "Script_Productions.bin",
        rates_table:  str  = "PRATES.BIN",
        rates_fields_by_purpose: dict = {
            "HBW_P":       "R_HBW_P",
            "HBNW_P":      "R_HBNW_P",
            "NHB_P":       "R_NHB_P",
            "TRUCKTAXI_P": "R_TRUCKTAXI_P",
        },
        segment_by_classification: dict = {"HH": ["HHSize", "INC"]}):

    output_path = os.path.join(MODEL_DIR, output_file)

    _delete_if_exists(output_path)

    o = dk.CreateObject("Generation.CrossClass", None)
    o.RatesTable = os.path.join(MODEL_DIR, rates_table)
    o.DataFile({"FileName": os.path.join(MODEL_DIR, "taz.bin")})
    o.OutputFile = output_path

    for purpose, rate_field in rates_fields_by_purpose.items():
        o.AddRate({"RateField": rate_field, "Purpose": purpose})
    for seg_name, class_fields in segment_by_classification.items():
        o.AddSegment({"Name": seg_name, "ClassifyBy": class_fields})

    ok = o.Run()
    if not ok:
        raise RuntimeError("Generation.CrossClass failed.")

    # Don't use GetResults() for the view name — it returns a message tuple.
    # Instead open the output file we already know the path of.
    prod_vw = dk.OpenTable("Productions", "FFB", [output_path, None])
    print(f"  Productions → {output_path}")
    print(f"  Open view name: '{prod_vw}'")
    return output_path, prod_vw


def run_attractions(dk: caliperpy.Gisdk, taz_vw: str):
    print("\n--- Step 1B: Trip Attractions ---")

    dk.SetView(taz_vw)

    field_names, _ = dk.GetFields(taz_vw, "All")
    print(f"  Fields: {field_names}")

    def find_field(candidates):
        for c in candidates:
            if c in field_names:
                return c
        raise ValueError(f"None of {candidates} in {field_names}")

    hh_f  = find_field(["HH",      "HOUSEHOLDS", "HHS"])
    ret_f = find_field(["RETAIL",  "RET_EMP",    "RETEMP"])
    bas_f = find_field(["BASIC",   "BASIC_EMP",  "BASEMP"])
    svc_f = find_field(["SERVICE", "SERV_EMP",   "SVCEMP"])
    print(f"  Using: {hh_f}, {ret_f}, {bas_f}, {svc_f}")

    existing, _ = dk.GetFields(taz_vw, "All")

    for fld in ["HBW_A", "HBNW_A", "NHB_A", "TRUCKTAXI_A"]:
        add_field(dk, taz_vw, fld, "Real", 12, 4)

    independents = [f"{taz_vw}.{f}" for f in [hh_f, ret_f, bas_f, svc_f]]

    # "viewname|" = all records of view, no selection set filter
    zone_set = taz_vw + "|"

    purposes = {
        "HBW_A":       [0, 0.1033, 1.2321, 1.3089, 1.2341],
        "HBNW_A":      [0, 0.6775, 7.4483, 0.4073, 1.2355],
        "NHB_A":       [0, 0.3951, 6.2293, 0.7082, 1.5902],
        "TRUCKTAXI_A": [0, 0.1130, 0.4209, 0.4967, 0.6361],
    }

    for dep_field, coeffs in purposes.items():
        print(f"  Computing {dep_field} ...")
        dk.ApplyLinearModel({
            "Input":  {"Zone Set":     zone_set},       # "TAZ|" not "TAZ"
            "Global": {"Method":       "R",
                       "Coefficients": coeffs,
                       "Output to Report File": 0},
            "Field":  {"Dependent":    f"{taz_vw}.{dep_field}",
                       "Independents": independents},
        })
        print(f"    {dep_field} OK")

    print("  Attractions done.")


def run_balancing(dk: caliperpy.Gisdk, taz_vw: str, prod_vw: str,
                  output_file: str = "MY_PA.bin") -> str:
    """
    Balance productions and attractions.
    taz_vw:  open view of taz.bin  — has HBW_A, HBNW_A etc.
    prod_vw: open view of Script_Productions.bin — has HBW_P, HBNW_P etc.

    Generation.Balance needs a single joined view that has BOTH
    the _P and _A fields visible together.
    """
    print("\n--- Step 1C: Trip Balancing ---")

    pa_file = os.path.join(MODEL_DIR, output_file)
    _delete_if_exists(pa_file)

    # Join the two open views on TAZ ID so Balance can see P and A together
    joined = dk.JoinViews("TAZ+Productions", f"{taz_vw}.ID",
                           f"{prod_vw}.ID", None)

    obj = dk.CreateObject("Generation.Balance", None)
    obj.AddDataSource({"ViewName": joined})
    obj.OutputFile = pa_file

    obj.AddPurpose({"Production": "HBW_P",       "Attraction": "HBW_A",
                    "HoldAttrFilter": f"{joined}.SP_HBW <> null"})
    obj.AddPurpose({"Production": "HBNW_P",      "Attraction": "HBNW_A",
                    "HoldAttrFilter": f"{joined}.SP_HBNW <> null"})
    obj.AddPurpose({"Production": "NHB_P",       "Attraction": "NHB_A",
                    "HoldAttrFilter": f"{joined}.SP_NHB <> null"})
    obj.AddPurpose({"Production": "TRUCKTAXI_P", "Attraction": "TRUCKTAXI_A",
                    "HoldAttrFilter": f"{joined}.SP_TRUCKTAXI <> null"})

    ok = obj.Run()
    if not ok:
        raise RuntimeError("Generation.Balance failed.")

    # Clean up intermediate views — downstream steps open their own
    dk.CloseView(joined)
    dk.CloseView(taz_vw)
    dk.CloseView(prod_vw)

    print(f"  Balanced P-A → {pa_file}")
    return pa_file


# Growth factor for Task 1B / Task 3 scenarios
