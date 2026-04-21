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
import os
from typing import List

import caliperpy
MODEL_DIR = r"C:\Users\dknom\Documents\school\CE5640_transportation_planning\Base Model - Data\Base Model_Script"

# %%
def run_cross_classification(
        dk: caliperpy.Gisdk,     
        rates_table="PRATES.BIN",
        output_file="ScriptProductions.bin",
        taz_file="taz.dbd",
        rates_fields_by_purpose={
            "HBW_P": "R_HBW_P",
            "HBNW_P": "R_HBNW_P",
            "NHB_P": "R_NHB_P",
            "TRUCKTAXI_P": "R_TRUCKTAXI_P"    
        },
        segment_by_classification={"HH": ["HHSize", "INC"]}
    ):
    output_path = os.path.join(MODEL_DIR, output_file)
    
    o = dk.CreateObject("Generation.CrossClass", None)

    o.RatesTable = os.path.join(MODEL_DIR, rates_table)
    o.DataFile({"FileName": os.path.join(MODEL_DIR, taz_file)})
    o.OutputFile = output_path

    for purpose, rate_field in rates_fields_by_purpose.items():
        o.AddRate({"RateField": rate_field, "Purpose": purpose})

    for segment_name, classification_fields in segment_by_classification.items():
        o.AddSegment({"Name": segment_name, "ClassifyBy": classification_fields})

    ok = o.Run()
    if ok:
        results = o.GetResults()
        print("  Productions written to:", output_path)
        print("  Results summary:", results)
        return results
    else:
        raise RuntimeError("Cross-classification failed. Check amarillo_model.log.")

dk = caliperpy.TransCAD.connect(log_file="amarillo_model.log")
productions_file = "ScriptProductions.bin"
run_cross_classification(dk, output_file=productions_file)
# %%
"""
How to join taz.dbd and My Productions.bin in caliperpy
--------------------------------------------------------
GISDK functions used (from TransCAD 10.0 docs):

  CreateMap()   – create a blank map so layers have somewhere to live
  AddLayer()    – open a .dbd geographic file and add it to the map
                  syntax: AddLayer(map, layer_name, db_path, db_layer_name)
  GetDBLayers() – inspect what layer names are inside a .dbd file
  OpenTable()   – open a tabular file (.bin, .dbf, etc.) as a view
                  syntax: OpenTable(view_name, type, [file, dict])
                  type for .bin files = "FFB"
  JoinViews()   – link two open views on a shared field
                  syntax: JoinViews(joined_name, left_field, right_field, opts)
  CloseView()   – clean up / close a view when done
"""


def join_tables(dk=caliperpy.Gisdk, left_table="taz", right_table="ScriptProductions", join_options:List[str]=None) -> str:
    left_view = dk.OpenTable(
        left_table,
        "FFB",
        [os.path.join(MODEL_DIR, left_table + ".bin"), None]
    )
    print("left view:", left_view)
    right_view = dk.OpenTable(
        right_table,
        "FFB",
        [os.path.join(MODEL_DIR, right_table + ".bin"), None]
    )
    print("Right view:", right_view)

    joined_view = dk.JoinViews(
        f"{left_table}+{right_table}",
        left_view + ".ID",
        right_view + ".ID",
        join_options
    )
    print("Joined view created:", joined_view)

    # ── Step 4: Verify — check the fields in the joined view ─────────────
    field_names, field_specs = dk.GetFields(joined_view, "All")
    print("\nFields in joined view:")
    for name in field_names:
        print(" ", name)

    n = dk.GetRecordCount(joined_view, None)
    print(f"\nRecord count: {n} TAZs")

    dk.CloseView(left_view)
    dk.CloseView(right_view)

    return joined_view


def run_attractions(dk, purposes=["HBW", "HBNW", "NHB", "TRUCKTAXI"]):
    taz_my_prod_view = join_tables(dk, left_table="taz", right_table="ScriptProductions")
    for purpose in purposes:
        model_file = os.path.join(MODEL_DIR, purpose + "_A.MOD")
        print(f"  Applying attraction model: {model_file}")

        # G30 Trip Attractions applies a .MOD regression file to an open view.
        # The joined view "TAZ+My Productions" must be active.
        # Results are stored in the field <PURPOSE>_A in that view.
        dk.RunMacro("G30 Trip Attractions", {
            "Model File":  model_file,
            "Apply To":    taz_my_prod_view,
            "Results In":  purpose + "_A"
        })

    print("  Attractions computed for all purposes.")

# %%

# =============================================================================
# STEP 1C: TRIP BALANCING  –  Generation.Balance
# =============================================================================
def run_balancing(dk):
    """
    Balance productions and attractions so totals are equal.
    Holds productions constant; adjusts attractions.

    GISDK class: Generation.Balance
    Key properties:
        OutputFile  – path for balanced output table (optional;
                      if omitted, writes back into the same table)
    Key methods:
        AddDataSource({TableName})         – input P-A table
        AddPurpose({Production,           – one call per trip purpose
                    Attraction,
                    Method,
                    HoldAttrFilter})
        Run()
    """
    print("\n--- Step 1C: Trip Balancing ---")

    obj = dk.CreateObject("Generation.Balance")

    # Input: the joined productions+TAZ table created in steps 1A/1B
    obj.AddDataSource({"TableName": MODEL_DIR + "ScriptProductions.bin"})

    # Output: new balanced file (MY PA.BIN)
    obj.OutputFile = MODEL_DIR + "MY PA.bin"

    # HoldAttrFilter = "SG" means special-generator attraction records
    # are held constant during balancing (they were set manually).
    # Method defaults to "HoldProductions" which is what the tutorial uses.
    obj.AddPurpose({
        "Production": "HBW_P", "Attraction": "HBW_A",
        "HoldAttrFilter": "SP_HBW <> null"
    })
    obj.AddPurpose({
        "Production": "HBNW_P", "Attraction": "HBNW_A",
        "HoldAttrFilter": "SP_HBNW <> null"
    })
    obj.AddPurpose({
        "Production": "NHB_P", "Attraction": "NHB_A",
        "HoldAttrFilter": "SP_NHB <> null"
    })
    obj.AddPurpose({
        "Production": "TRUCKTAXI_P", "Attraction": "TRUCKTAXI_A",
        "HoldAttrFilter": "SP_TRUCKTAXI <> null"
    })

    ok = obj.Run()
    if ok:
        print("  Balanced P-A table written to:", MODEL_DIR + "MY PA.bin")
    else:
        raise RuntimeError("Trip balancing failed. Check amarillo_model.log.")

    return ok


# =============================================================================
# STEP 2A: BUILD HIGHWAY NETWORK  –  Network.Create + Network.Settings
# =============================================================================
def build_network(dk):
    """
    Create a TransCAD highway network (.net) from the line geographic file.

    GISDK class: Network.Create
    Key properties:
        LayerDB         – path to the line geographic file (.dbd)
        TimeUnits       – "Minutes"
        OutNetworkName  – path for the output network file (.net)
    Key methods:
        AddLinkField({Name, Field, IsTimeField})  – include a link attribute
        Run()

    Then Network.Settings to configure centroids and link types.
    """
    print("\n--- Step 2A: Build Highway Network ---")

    net_file = MODEL_DIR + "My Network.net"

    # ── Build the network ──────────────────────────────────────────────────
    net_obj = dk.CreateObject("Network.Create")
    net_obj.LayerDB       = MODEL_DIR + "network.dbd"
    net_obj.TimeUnits     = "Minutes"
    net_obj.OutNetworkName = net_file

    # Include the fields needed for skimming and assignment
    # TIME is the free-flow travel time field (IsTimeField = true)
    net_obj.AddLinkField({"Name": "Time",        "Field": "TIME",
                          "IsTimeField": True})
    net_obj.AddLinkField({"Name": "Capacity",
                          "Field": ["AB_CAPACITY", "BA_CAPACITY"]})
    net_obj.AddLinkField({"Name": "Alpha",       "Field": "ALPHA"})
    net_obj.AddLinkField({"Name": "Beta",        "Field": "BETA"})

    ok = net_obj.Run()
    if not ok:
        raise RuntimeError("Network.Create failed.")
    print("  Network created:", net_file)

    # ── Set centroids and link types ───────────────────────────────────────
    # Network.Settings tells TransCAD which nodes are zone centroids and
    # enables reporting by functional class.
    net_set = dk.CreateObject("Network.Settings", {"Network": net_file})
    net_set.CentroidFilter = "TAZ <> null"   # nodes where TAZ field is not null
    net_set.UseLinkTypes   = True            # report by functional class (FUNCL)
    ok2 = net_set.Run()
    if not ok2:
        raise RuntimeError("Network.Settings failed.")
    print("  Centroids and link types configured.")

    return net_file


# =============================================================================
# STEP 2B: SKIM MATRIX  –  Network.Skims
# =============================================================================
def run_skims(dk, net_file):
    """
    Compute the all-pairs shortest-path impedance (travel time) matrix.

    GISDK class: Network.Skims
    Key properties:
        Network      – path to the .net file
        LayerDB      – path to the geographic file
        Origins      – SQL filter selecting origin nodes (centroids)
        Destinations – SQL filter selecting destination nodes (centroids)
        Minimize     – network field to minimize (here: "Time")
    Key methods:
        AddSkimField({field_name, skim_type})  – fields to skim
        OutputMatrix({MatrixFile, Matrix})     – output path and name
        Run()
    """
    print("\n--- Step 2B: Skim Matrix ---")

    skim_file = MODEL_DIR + "My Skim.mtx"

    obj = dk.CreateObject("Network.Skims")
    obj.Network      = net_file
    obj.LayerDB      = MODEL_DIR + "network.dbd"
    obj.Origins      = "TAZ <> null"
    obj.Destinations = "TAZ <> null"
    obj.Minimize     = "Time"

    # Skim travel time across all link types
    obj.AddSkimField(["Time", "All"])

    obj.OutputMatrix({
        "MatrixFile":  skim_file,
        "Matrix":      "Shortest Path",
        "Compression": True,
        "ColumnMajor": False
    })

    ok = obj.Run()
    if not ok:
        raise RuntimeError("Network.Skims failed.")

    results = obj.GetResults().Data
    print("  Skim matrix written to:", skim_file)
    return skim_file


# =============================================================================
# STEP 3: TRIP DISTRIBUTION  –  Distribution.Gravity
# =============================================================================
def run_gravity(dk, skim_file):
    """
    Distribute trips between zones using a doubly-constrained gravity model.

    GISDK class: Distribution.Gravity
    Key properties:
        CalculateTLD  – if True, returns trip length distribution stats
    Key methods:
        AddDataSource({TableName})   – P-A input table
        AddPurpose({Name,            – one call per trip purpose
                    Production,
                    Attraction,
                    ConstraintType,
                    Iterations,
                    Convergence,
                    ImpedanceMatrix,
                    Table})
        OutputMatrix({MatrixFile, MatrixLabel})
        Run()

    ImpedanceMatrix is an "options array" (dict in Python) with keys:
        MatrixFile, Matrix, RowIndex, ColIndex
    """
    print("\n--- Step 3: Trip Distribution (Gravity Model) ---")

    gravity_out = MODEL_DIR + "My PA.mtx"

    # Matrix currency descriptor for the skim matrix
    sp_mat = {
        "MatrixFile": skim_file,
        "Matrix":     "Shortest Path",
        "RowIndex":   "Origin",
        "ColIndex":   "Destination"
    }

    # Friction factor table (time vs. friction factor lookup)
    ff_table = MODEL_DIR + "FFDATA.DBF"

    obj = dk.CreateObject("Distribution.Gravity")
    obj.CalculateTLD = True

    # Input: balanced P-A table from Step 1C
    obj.AddDataSource({"TableName": MODEL_DIR + "MY PA.bin"})

    # Each purpose uses the Table-based friction factor method (not Gamma).
    # TimeField maps to the time column in FFDATA.DBF;
    # FrictionField maps to the FF column for that purpose.
    for purpose, ff_field in [("HBW",      "HBW"),
                               ("HBNW",     "HBNW"),
                               ("NHB",      "NHB"),
                               ("TRUCKTAXI","TRUCKTAXI")]:
        obj.AddPurpose({
            "Name":             purpose,
            "Production":       purpose + "_P",
            "Attraction":       purpose + "_A",
            "ConstraintType":   "Doubly",
            "Iterations":       20,
            "Convergence":      0.01,
            "ImpedanceMatrix":  sp_mat,
            "Table": {
                "Name":           ff_table,
                "TimeField":      "TIME",
                "FrictionField":  ff_field
            }
        })

    obj.OutputMatrix({
        "MatrixFile":   gravity_out,
        "MatrixLabel":  "Gravity Output",
        "Compression":  True,
        "ColumnMajor":  False
    })

    ok = obj.Run()
    if not ok:
        raise RuntimeError("Distribution.Gravity failed.")

    results = obj.GetResult()
    print("  Gravity matrix written to:", gravity_out)
    print("  Results:", results)
    return gravity_out


# =============================================================================
# STEP 4: PA TO OD CONVERSION  –  Distribution.PA2OD
# =============================================================================
def run_pa2od(dk, gravity_out):
    """
    Convert production-attraction matrices to origin-destination matrices,
    applying vehicle occupancy factors.

    GISDK class: Distribution.PA2OD
    Key properties:
        Daily        – True for a 24-hour daily model (no time-of-day split)
        ReportByHour – False for daily
    Key methods:
        Matrix(string)               – input PA matrix file
        AddPurpose({Name,            – one call per purpose
                    Occupancy})
        OutputMatrix(string)         – output OD matrix file path
        Run()
    """
    print("\n--- Step 4: PA to OD Conversion ---")

    od_out = MODEL_DIR + "My OD.mtx"

    o = dk.CreateObject("Distribution.PA2OD")

    # Input: gravity output matrix from Step 3
    o.Matrix(gravity_out)

    # Daily model (no hour-by-hour split)
    o.Daily        = True
    o.ReportByHour = False

    # Occupancy values from the tutorial:
    #   HBW=1.1, HBNW=1.3, NHB=1.5, TRUCKTAXI=1.0
    o.AddPurpose({"Name": "HBW",       "Occupancy": 1.1})
    o.AddPurpose({"Name": "HBNW",      "Occupancy": 1.3})
    o.AddPurpose({"Name": "NHB",       "Occupancy": 1.5})
    o.AddPurpose({"Name": "TRUCKTAXI", "Occupancy": 1.0})

    o.OutputMatrix(od_out)

    ok = o.Run()
    if not ok:
        raise RuntimeError("Distribution.PA2OD failed.")

    results = o.GetResults().Data
    print("  OD matrix written to:", od_out)
    print("  Matrix handle:", results.get("Matrix"))
    return od_out


# =============================================================================
# STEP 5: TRAFFIC ASSIGNMENT  –  Network.Assignment
# =============================================================================
def run_assignment(dk, net_file, od_file):
    """
    User Equilibrium traffic assignment using the BPR delay function.

    GISDK class: Network.Assignment
    Key properties:
        LayerDB     – path to the geographic file
        Network     – path to the .net file
        Method      – "CUE" (Conjugate UE, the default and recommended method)
        Iterations  – max iterations (100 is standard)
        Convergence – relative gap stopping criterion (0.0001)
        FlowTable   – path for the output flow table
    Key methods:
        DemandMatrix({MatrixFile, Matrix, RowIndex, ColumnIndex})
        AddClass({Demand})          – one class for simple single-class assignment
        DelayFunction               – BPR function spec (property, not method)
        Run()
        GetTaskResults()            – returns VMT, VHT, etc.
    """
    print("\n--- Step 5: Traffic Assignment ---")

    flow_table = MODEL_DIR + "My Daily Assign.bin"

    obj = dk.CreateObject("Network.Assignment")
    obj.LayerDB     = MODEL_DIR + "network.dbd"
    obj.Network     = net_file
    obj.Method      = "CUE"          # Conjugate User Equilibrium
    obj.Iterations  = 100
    obj.Convergence = 0.0001
    obj.FlowTable   = flow_table

    # OD demand matrix — use QuickSum core (sum of all purposes)
    # RowIndex / ColumnIndex must match node IDs, not TAZ IDs.
    # TransCAD uses the index named "TAZ to Node ID" that was built
    # when the matrix index was set up in the tutorial.
    obj.DemandMatrix({
        "MatrixFile":    od_file,
        "Matrix":        "QuickSum",
        "RowIndex":      "TAZ to Node ID",
        "ColumnIndex":   "TAZ to Node ID"
    })

    # Single demand class
    obj.AddClass({"Demand": "QuickSum"})

    # BPR volume-delay function
    # Fields array order: [Time, Capacity, Alpha, Beta, Preload]
    obj.DelayFunction = {
        "Function": "bpr.vdf",
        "Fields":   ["Time", "Capacity", "Alpha", "Beta", "None"],
        "Defaults": ["0",    "1800",     "0.15",  "4",    "0"]
    }

    ok = obj.Run()
    if not ok:
        raise RuntimeError("Network.Assignment failed.")

    results = obj.GetTaskResults()
    print("  Flow table written to:", flow_table)
    print("  Assignment results:")
    print("    VMT:", results.get("VMT"))
    print("    VHT:", results.get("VHT"))
    return results


# =============================================================================
# MAIN
# =============================================================================
def main():
    dk = connect()

    # Step 1: Trip Generation
    run_cross_classification(dk)
    run_attractions(dk)
    run_balancing(dk)

    # Step 2: Network + Skim
    net_file  = build_network(dk)
    skim_file = run_skims(dk, net_file)

    # Step 3: Trip Distribution
    gravity_out = run_gravity(dk, skim_file)

    # Step 4: PA to OD
    od_file = run_pa2od(dk, gravity_out)

    # Step 5: Traffic Assignment
    results = run_assignment(dk, net_file, od_file)

    print("\n=== Model run complete ===")
    print(f"  Daily VMT: {results.get('VMT')}")
    print(f"  Daily VHT: {results.get('VHT')}")


if __name__ == "__main__":
    main()