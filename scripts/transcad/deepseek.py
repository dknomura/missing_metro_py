
# sensitivity_analysis.py
# Runs the Amarillo 4-step model with varying trip production reductions
# and plots the sensitivity of VMT and VHT.

import sys
import caliperpy
import pandas as pd
import matplotlib.pyplot as plt

# ----------------------------------------------------------------------
# Helper: Run the full model for a given trip production reduction factor
# ----------------------------------------------------------------------
def run_model(dk, tutorial_folder, reduction):
    """
    Runs the 4-step model (Trip Generation, Balancing, Distribution,
    PA->OD, Traffic Assignment) and returns VMT, VHT, and bottleneck links.
    
    Parameters:
    -----------
    dk : caliperpy connection
    tutorial_folder : str, path to tutorial data
    reduction : float, factor to reduce all production trip ends (0 = no reduction, 0.2 = 20% reduction)
    
    Returns:
    --------
    vmt : float, total vehicle miles traveled
    vht : float, total vehicle hours traveled
    bottlenecks : list of (link_id, vc_ratio) for links with V/C > 1.0
    """
    # ------------------------------------------------------------------
    # 1. Open base data
    # ------------------------------------------------------------------
    taz_table = dk.OpenTable("TAZ", "dbd", [tutorial_folder + "taz.dbd", None])
    rates_table = dk.OpenTable("PRATES", "bin", [tutorial_folder + "PRATES.BIN", None])
    
    # ------------------------------------------------------------------
    # 2. Trip Generation - Productions (Cross‑Classification)
    # ------------------------------------------------------------------
    # Note: The actual GISDK macro name may be "CrossClassification"
    productions = dk.RunMacro("RunCrossClassification",
                              taz_table,          # zone data
                              "HH",               # zone size field
                              "INC",              # classification field (income)
                              rates_table,        # trip rate table
                              ["HBW_P", "HBNW_P", "NHB_P", "TRUCKTAXI_P"],
                              output_file=None)   # returns a dataview
    
    # Apply reduction to all production fields
    prod_fields = ["HBW_P", "HBNW_P", "NHB_P", "TRUCKTAXI_P"]
    for fld in prod_fields:
        dk.RunMacro("SetField", productions, fld, f"{fld} * (1 - {reduction})")
    
    # ------------------------------------------------------------------
    # 3. Trip Generation - Attractions (Regression models)
    # ------------------------------------------------------------------
    # Apply pre‑defined regression models for each purpose
    # (Assuming model files: HBW_A_MOD, HBNW_A_MOD, NHB_A_MOD, TRUCKTAXI_A_MOD)
    attraction_models = {
        "HBW_A": "HBW_A_MOD",
        "HBNW_A": "HBNW_A_MOD",
        "NHB_A": "NHB_A_MOD",
        "TRUCKTAXI_A": "TRUCKTAXI_A_MOD"
    }
    for attr_field, model_file in attraction_models.items():
        dk.RunMacro("ApplyRegressionModel",
                    productions,          # dataview to update
                    tutorial_folder + model_file,
                    attr_field)           # output field name
    
    # ------------------------------------------------------------------
    # 4. Special Generators (replace with SP_* fields where not null)
    # ------------------------------------------------------------------
    # Create selection set of zones with special productions/attractions
    dk.RunMacro("SelectByCondition", productions, "SP_HBW <> null", "SG")
    # Fill production/attraction fields from SP_* fields
    for fld in prod_fields:
        sp_fld = f"SP_{fld[:-2]}"   # e.g., SP_HBW for HBW_P
        dk.RunMacro("FillField", productions, fld, sp_fld, selection="SG")
    # Similarly for attractions (SA_* fields) – omitted for brevity
    
    # ------------------------------------------------------------------
    # 5. Trip Balancing (Productions fixed, attractions adjusted)
    # ------------------------------------------------------------------
    balance_pairs = [
        ("HBW_P", "HBW_A"),
        ("HBNW_P", "HBNW_A"),
        ("NHB_P", "NHB_A"),
        ("TRUCKTAXI_P", "TRUCKTAXI_A")
    ]
    balanced_pa = dk.RunMacro("BalanceVectors",
                              productions,
                              balance_pairs,
                              method="hold_vec1",        # hold productions
                              output_file=tutorial_folder + "temp_pa.bin")
    
    # ------------------------------------------------------------------
    # 6. Impedance Matrix (Shortest Path Times)
    # ------------------------------------------------------------------
    # Create network if not already existing
    network_file = tutorial_folder + "MyNetwork.NET"
    dk.RunMacro("CreateNetwork", tutorial_folder + "NETWORK.DBD", "TIME", network_file)
    # Compute skim matrix
    skim_matrix = dk.RunMacro("MultipleShortestPaths",
                              network=network_file,
                              origin_set="Centroids",
                              dest_set="Centroids",
                              cost_field="TIME",
                              output_file=tutorial_folder + "temp_skim.mtx")
    
    # ------------------------------------------------------------------
    # 7. Trip Distribution (Doubly Constrained Gravity)
    # ------------------------------------------------------------------
    friction_file = tutorial_folder + "FFDATA.DBF"
    purposes = ["HBW", "HBNW", "NHB", "TruckTaxi"]
    dist_matrix = dk.RunMacro("GravityApplication",
                              pa_table=balanced_pa,
                              impedance_matrix=skim_matrix,
                              ff_table=friction_file,
                              purposes=purposes,
                              output_file=tutorial_folder + "temp_dist.mtx")
    
    # ------------------------------------------------------------------
    # 8. Mode Split (simplified: assume all trips are auto for this exercise)
    #    In a full model you would apply a logit model; here we skip.
    #    We just use the distributed PA matrix as auto trips.
    # ------------------------------------------------------------------
    auto_pa = dist_matrix   # for simplicity
    
    # ------------------------------------------------------------------
    # 9. PA to OD conversion (daily model, half trips each direction)
    # ------------------------------------------------------------------
    # Average occupancies: HBW=1.1, HBNW=1.3, NHB=1.5, TruckTaxi=1.0
    occupancies = [1.1, 1.3, 1.5, 1.0]
    od_matrix = dk.RunMacro("PAtoOD", auto_pa, occupancies,
                            output_file=tutorial_folder + "temp_od.mtx")
    
    # Optional: add internal‑external and external‑external trips
    # (not shown for brevity – see tutorial pages 28‑30)
    
    # ------------------------------------------------------------------
    # 10. Traffic Assignment (User Equilibrium)
    # ------------------------------------------------------------------
    assign_result = dk.RunMacro("TrafficAssignment",
                                method="User Equilibrium (BFW)",
                                matrix=od_matrix,
                                network=network_file,
                                time_field="TIME",
                                capacity_field="AB_CAPACITY",
                                alpha_field="ALPHA",
                                beta_field="BETA",
                                output_file=tutorial_folder + "temp_assign.bin")
    
    # ------------------------------------------------------------------
    # 11. Extract results
    # ------------------------------------------------------------------
    # VMT and VHT are usually written to the master report.
    # We can retrieve them from the assignment result dataview.
    vmt = dk.GetField(assign_result, "VMT")      # example field name
    vht = dk.GetField(assign_result, "VHT")      # example field name
    
    # Bottlenecks: links with volume / capacity > 1.0
    # The assignment result table contains fields AB_FLOW, BA_FLOW, AB_CAPACITY, BA_CAPACITY
    link_table = assign_result   # actually a dataview joined to the line layer
    vc_ratio_ab = dk.RunMacro("EvalExpression", link_table, "AB_FLOW / AB_CAPACITY")
    vc_ratio_ba = dk.RunMacro("EvalExpression", link_table, "BA_FLOW / BA_CAPACITY")
    
    bottlenecks = []
    for i in range(dk.GetRecordCount(link_table)):
        link_id = dk.GetField(link_table, "ID", i)
        vc_ab = dk.GetField(vc_ratio_ab, i)
        vc_ba = dk.GetField(vc_ratio_ba, i)
        if vc_ab > 1.0 or vc_ba > 1.0:
            bottlenecks.append((link_id, max(vc_ab, vc_ba)))
    
    return vmt, vht, bottlenecks


# ----------------------------------------------------------------------
# Main script: run sensitivity analysis and plot results
# ----------------------------------------------------------------------
def main():
    # Connect to TransCAD
    dk = caliperpy.TransCAD.connect()
    tutorial_folder = dk.RunMacro("G30 Tutorial Folder")   # returns path like "C:/TransCAD90/Tutorial/"
    
    # Define reduction factors to test (0% to 20% reduction)
    reductions = [0.0, 0.05, 0.10, 0.15, 0.20]
    
    # Store results
    results = []
    
    print("Running sensitivity analysis...")
    for red in reductions:
        print(f"  Reduction = {red*100:.0f}%")
        try:
            vmt, vht, bottlenecks = run_model(dk, tutorial_folder, red)
            results.append({
                "reduction": red,
                "VMT": vmt,
                "VHT": vht,
                "num_bottlenecks": len(bottlenecks)
            })
            print(f"    VMT = {vmt:.2f}, VHT = {vht:.2f}, bottlenecks = {len(bottlenecks)}")
        except Exception as e:
            print(f"    Error: {e}")
            results.append({"reduction": red, "VMT": None, "VHT": None, "num_bottlenecks": None})
    
    # Convert to DataFrame for easy plotting
    df = pd.DataFrame(results)
    
    # Plot VMT and VHT vs. reduction factor
    fig, ax1 = plt.subplots(figsize=(8,5))
    
    ax1.set_xlabel("Trip Production Reduction Factor")
    ax1.set_ylabel("Vehicle Miles Traveled (VMT)", color="tab:blue")
    ax1.plot(df["reduction"], df["VMT"], marker="o", color="tab:blue", label="VMT")
    ax1.tick_params(axis="y", labelcolor="tab:blue")
    
    ax2 = ax1.twinx()
    ax2.set_ylabel("Vehicle Hours Traveled (VHT)", color="tab:red")
    ax2.plot(df["reduction"], df["VHT"], marker="s", color="tab:red", label="VHT")
    ax2.tick_params(axis="y", labelcolor="tab:red")
    
    plt.title("Sensitivity of VMT and VHT to Trip Production Reduction")
    fig.tight_layout()
    plt.show()
    
    # Also plot number of bottlenecks
    plt.figure(figsize=(8,4))
    plt.plot(df["reduction"], df["num_bottlenecks"], marker="^", color="green")
    plt.xlabel("Trip Production Reduction Factor")
    plt.ylabel("Number of Bottlenecks (V/C > 1.0)")
    plt.title("Sensitivity of Bottleneck Count")
    plt.grid(True)
    plt.show()
    
    # Print summary table
    print("\nSummary Table:")
    print(df.to_string(index=False))
    
    # Disconnect
    dk.Quit()
    dk = None


if __name__ == "__main__":
    main()
# %%
