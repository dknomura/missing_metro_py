import caliperpy

def main():
    dk = caliperpy.TransCAD.connect()
    model_dir = r"C:\Users\dknom\Documents\school\CE5640_transportation_planning\Base Model - Data\Base Model"

    # ── 1a. Open TAZ layer ──────────────────────────────────────────────
    taz_map = dk.OpenMap(model_dir + "taz.dbd", None)
    taz_layer = dk.GetLayer(taz_map, "TAZ")

    # ── 1b. Trip Productions – Cross Classification ─────────────────────
    prates = dk.OpenTable("PRATES", "ffb", [model_dir + "PRATES.BIN", None])

    prod_opts = {
        "Zone Data":        "TAZ",
        "Size Field":       "HH",
        "Trip Rate Table":  "PRATES",
        "Trip Purposes":    ["HBW", "HBNW", "NHB", "TRUCKTAXI"],
        "Match Fields":     [["[Household Size]", "HHSize"],
                             ["INCOME",           "INC"]]
    }
    dk.RunMacro("G30 Trip Productions Cross Class", prod_opts,
                [model_dir + "My Productions.bin", None])

    # ── 1c. Trip Attractions – Regression ───────────────────────────────
    for purpose in ["HBW", "HBNW", "NHB", "TRUCKTAXI"]:
        attr_opts = {
            "Model File":  model_dir + purpose + "_A.MOD",
            "Apply To":    "TAZ+My Productions",
            "Results In":  purpose + "_A"
        }
        dk.RunMacro("G30 Trip Attractions Apply Model", attr_opts)

    # ── 1d. Special Generators ──────────────────────────────────────────
    dk.SetView("TAZ+My Productions")
    n = dk.SelectByQuery("SG", "several",
                         "select * where SP_HBW <> null", None)

    for purpose in ["HBW", "HBNW", "NHB", "TRUCKTAXI"]:
        # Fill production field with special generator values for SG set
        dk.RunMacro("G30 Fill", {
            "View":   "TAZ+My Productions|SG",
            "Field":  purpose + "_P",
            "Value":  "SP_" + purpose
        })
        # Fill attraction field
        dk.RunMacro("G30 Fill", {
            "View":   "TAZ+My Productions|SG",
            "Field":  purpose + "_A",
            "Value":  "SA_" + purpose
        })

    # ── 1e. Trip Balancing ──────────────────────────────────────────────
    balance_opts = {
        "Dataview": "TAZ+My Productions",
        "Vectors": [
            {"V1": "HBW_P",      "V2": "HBW_A",      "V2 Hold": "SG"},
            {"V1": "HBNW_P",     "V2": "HBNW_A",     "V2 Hold": "SG"},
            {"V1": "NHB_P",      "V2": "NHB_A",      "V2 Hold": "SG"},
            {"V1": "TRUCKTAXI_P","V2": "TRUCKTAXI_A","V2 Hold": "SG"}
        ],
        "Method": "Hold Vector 1"
    }
    dk.RunMacro("G30 Balance Vectors", balance_opts,
                [model_dir + "MY PA.bin", None])

main()

def build_skim(dk, model_dir):

    # Open network geographic file
    net_map = dk.OpenMap(model_dir + "network.dbd", None)

    # Select centroid nodes
    dk.SetLayer("Nodes")
    dk.SelectByQuery("Centroids", "several",
                     "select * where TAZ <> null", None)

    # Create highway network
    net_opts = {
        "Link Fields": ["[AB_CAPACITY]", "[BA_CAPACITY]",
                        "TIME", "ALPHA", "BETA"],
        "Time Field":  "TIME",
        "Type Field":  "FUNCL"
    }
    dk.RunMacro("G30 Create Network", net_opts,
                model_dir + "My Network.net")

    # Set centroids
    dk.RunMacro("G30 Network Settings", {
        "Centroids": "Centroids",
        "Link Types": True
    })

    # Compute shortest path matrix
    sp_opts = {
        "Minimize": "TIME",
        "From":     "Centroids",
        "To":       "Centroids"
    }
    dk.RunMacro("G30 Multiple Shortest Paths", sp_opts,
                model_dir + "My Skim.mtx")

    # Add TAZ-based matrix index
    idx_opts = {
        "Dataview":  "Nodes",
        "From Field": "ID",
        "To Field":   "TAZ",
        "Name":       "Node ID to TAZ",
        "Selection":  "Centroids"
    }
    dk.RunMacro("G30 Add Matrix Index",
                model_dir + "My Skim.mtx", idx_opts)

    # Intrazonal travel times
    dk.RunMacro("G30 Intrazonal Travel Times", {
        "Matrix": model_dir + "My Skim.mtx",
        "Factor": 0.5
    })

def run_gravity(dk, model_dir):

    pa_table  = dk.OpenTable("PA", "ffb", [model_dir + "MY PA.BIN", None])
    ff_table  = dk.OpenTable("FFData", "dbase", [model_dir + "FFDATA.DBF", None])
    skim_mtx  = dk.OpenMatrix(model_dir + "My Skim.mtx", None)

    grav_opts = {
        "PA Table":       "PA",
        "FF Table":       "FFData",
        "Impedance Matrix": skim_mtx,
        "Constraint":     "Doubly",
        "Purposes": [
            {"Name": "HBW",      "Production": "HBW_P",
             "Attraction": "HBW_A",  "FF Field": "HBW",
             "Method": "Table", "Iterations": 20},
            {"Name": "HBNW",     "Production": "HBNW_P",
             "Attraction": "HBNW_A", "FF Field": "HBNW",
             "Method": "Table", "Iterations": 20},
            {"Name": "NHB",      "Production": "NHB_P",
             "Attraction": "NHB_A",  "FF Field": "NHB",
             "Method": "Table", "Iterations": 20},
            {"Name": "TRUCKTAXI","Production": "TRUCKTAXI_P",
             "Attraction": "TRUCKTAXI_A","FF Field": "TRUCKTAXI",
             "Method": "Table", "Iterations": 20}
        ]
    }
    dk.RunMacro("G30 Gravity Application", grav_opts,
                model_dir + "My PA.mtx")

def run_pa_to_od(dk, model_dir):

    pa_mtx = dk.OpenMatrix(model_dir + "My PA.mtx", None)

    pa_od_opts = {
        "PA Matrix":    pa_mtx,
        "Report Hours": False,   # 24-hour daily model
        "Matrices": [
            {"Name": "HBW",       "Veh": True, "Avg Occupancy": 1.1},
            {"Name": "HBNW",      "Veh": True, "Avg Occupancy": 1.3},
            {"Name": "NHB",       "Veh": True, "Avg Occupancy": 1.5},
            {"Name": "TRUCKTAXI", "Veh": True, "Avg Occupancy": 1.0}
        ]
    }
    dk.RunMacro("G30 PA to OD", pa_od_opts,
                model_dir + "My OD.mtx")

    # Merge I-E trips
    ie_mtx = dk.OpenMatrix(model_dir + "IE.mtx", None)
    dk.RunMacro("G30 Matrix Update", {
        "Target Matrix": model_dir + "My OD.mtx",
        "Target Core":   "IE (0-24)",
        "Source Matrix": ie_mtx,
        "Source Core":   "Trips",
        "Missing":       "Ignore"
    })

    # QuickSum to get total vehicle O-D matrix
    od_mtx = dk.OpenMatrix(model_dir + "My OD.mtx", None)
    dk.RunMacro("G30 Matrix QuickSum", od_mtx)


def run_assignment(dk, model_dir):

    # Build TAZ-to-Node index on OD matrix
    od_mtx = dk.OpenMatrix(model_dir + "My OD.mtx", None)
    dk.RunMacro("G30 Add Matrix Index", model_dir + "My OD.mtx", {
        "Dataview":   "Nodes",
        "From Field": "TAZ",
        "To Field":   "ID",
        "Name":       "TAZ to Node ID",
        "Selection":  "Centroids"
    })
    dk.SetMatrixIndex(od_mtx, "TAZ to Node ID", "TAZ to Node ID")

    # Run User Equilibrium assignment
    assign_opts = {
        "Method":      "User Equilibrium BFW",
        "Matrix File": model_dir + "My OD.mtx",
        "Matrix":      "QuickSum",
        "Delay Function": "Bureau of Public Roads (BPR)",
        "Fields": {
            "Time":     "TIME",
            "Capacity": "[AB_CAPACITY]/[BA_CAPACITY]",
            "Alpha":    "ALPHA",
            "Beta":     "BETA"
        },
        "Iterations": 100,
        "Rel Gap":    0.0001
    }
    dk.RunMacro("G30 Static Traffic Assignment", assign_opts,
                model_dir + "My Daily Assign.bin")

    # Extract VMT and VHT summary
    report = dk.RunMacro("G30 Get Assignment Report",
                         model_dir + "My Daily Assign.bin")
    print("Daily VMT:", report["VMT"])
    print("Daily VHT:", report["VHT"])


import caliperpy
import pandas as pd

def run_full_model(dk, model_dir, scenario_name, se_data_overrides=None):
    """Run the complete 4-step model for one scenario."""

    print(f"\n=== Running scenario: {scenario_name} ===")

    # Optionally modify SE data before running
    if se_data_overrides:
        taz_table = dk.OpenTable("TAZ", "dbd",
                                 [model_dir + "taz.dbd", None])
        for field, multiplier in se_data_overrides.items():
            # e.g., scale HH by 1.2 for future year
            dk.RunMacro("G30 Fill Field Multiply", {
                "Table": "TAZ",
                "Field": field,
                "Factor": multiplier
            })

    # Run all steps in sequence
    build_skim(dk, model_dir)
    run_gravity(dk, model_dir)
    run_pa_to_od(dk, model_dir)
    vmt, vht = run_assignment(dk, model_dir)

    return {"Scenario": scenario_name, "VMT": vmt, "VHT": vht}


def main():
    dk = caliperpy.TransCAD.connect(log_file="model_runs.log")
    model_dir = "C:/TransCAD/Base Model/"

    results = []

    # Base year
    results.append(run_full_model(dk, model_dir, "Base Year"))

    # No-Build: 20% population and employment growth
    results.append(run_full_model(dk, model_dir, "No-Build 2034",
        se_data_overrides={"HH": 1.20, "TOTEMP": 1.20}))

    # Sensitivity: reduced HBW trip rate (remote work policy)
    results.append(run_full_model(dk, model_dir, "Reduced HBW Rates",
        se_data_overrides={"HH": 1.20, "TOTEMP": 1.20,
                           "HBW_RATE_FACTOR": 0.85}))

    # Export results
    df = pd.DataFrame(results)
    df.to_csv(model_dir + "sensitivity_results.csv", index=False)
    print("\n", df)

main()