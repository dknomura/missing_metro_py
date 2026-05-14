import os
import shutil

import numpy as np
import pandas as pd
import caliperpy
from transcad.constants import MODEL_DIR

def view_mtx(dk: caliperpy.Gisdk, path: str, core: str = None, rows: int = 10) -> "pd.DataFrame":
    """
    Read a TransCAD .mtx file into a pandas DataFrame.
    
    GISDK vectors must be converted with dk.VectorToArray(v) before
    passing to list() or pandas — they are not Python iterables.
    """
    import pandas as pd

    matrix     = dk.OpenMatrix(path, "True")
    core_names = dk.GetMatrixCoreNames(matrix)
    print(f"File : {path}")
    print(f"Cores: {core_names}")

    def vec_to_list(v):
        """Convert a GISDK vector to a plain Python list."""
        return dk.VectorToArray(v)

    # ── Marginals-only mode (no core specified) ───────────────────────────
    if core is None:
        records = {}
        for cname in core_names:
            mc       = dk.CreateMatrixCurrency(matrix, cname, None, None, None)
            row_sums = dk.GetMatrixVector(mc, [["Marginal", "Row Sum"]])
            records[cname] = vec_to_list(row_sums)   # ← VectorToArray here
        df = pd.DataFrame(records)
        print(f"Shape: {len(df)} zones × {len(core_names)} cores (row sums)\n")
        return df.head(rows)

    # ── Full matrix mode for a single core ───────────────────────────────
    if core not in core_names:
        raise ValueError(f"Core '{core}' not found. Available: {core_names}")

    mc      = dk.CreateMatrixCurrency(matrix, core, None, None, None)
    row_ids = vec_to_list(dk.GetMatrixVector(mc, [["Index", "Row"]]))     # ←
    col_ids = vec_to_list(dk.GetMatrixVector(mc, [["Index", "Column"]]))  # ←

    row_data = {}
    for rid in row_ids[:rows]:
        row_vec          = dk.GetMatrixVector(mc, [["Row", rid]])
        row_data[rid]    = vec_to_list(row_vec)                           # ←

    df = pd.DataFrame(row_data, index=col_ids).T
    df.index.name   = "Origin"
    df.columns.name = "Destination"

    total = sum(v for row in row_data.values()
                for v in row if v is not None)
    print(f"Core : '{core}'")
    print(f"Shape: {len(row_ids)} × {len(col_ids)}")
    print(f"Total (first {rows} rows): {total:,.1f}\n")
    return df

def scale_taz_fields(dk: caliperpy.Gisdk, taz_bin_path: str, fields: list, factor: float,
                     output_bin: str):
    """
    Copy taz.bin to output_bin, then multiply every field in `fields` by
    `factor` in the copy.  Original file is untouched.

    Uses:
      OpenTable / GetDataVector / SetDataVector / CloseView
    """
    shutil.copy2(taz_bin_path, output_bin)
    # Copy the .dcb descriptor — required by TransCAD to open the .bin
    dcb_src = taz_bin_path.replace(".bin", ".dcb")
    dcb_dst = output_bin.replace(".bin", ".dcb")
    if os.path.exists(dcb_src):
        shutil.copy2(dcb_src, dcb_dst)

    vw = dk.OpenTable("ScaleTAZ", "FFB", [output_bin, None])
    dk.SetView(vw)
    for field in fields:
        set_data_vector_scaled(dk, vw + "|", field, factor)
    dk.CloseView(vw)
    
    print(f"  Scaled {fields} by {factor:.2f}  →  {output_bin}")

def set_data_vector_scaled(dk, view_set: str, field: str, factor: float):
    """Scale a field in-place using GetDataVector/SetDataVector safely."""
    v_arr  = dk.VectorToArray(dk.GetDataVector(view_set, field, None))
    scaled = dk.ArrayToVector([x * factor if x is not None else 0.0 for x in v_arr])
    dk.SetDataVector(view_set, field, scaled, None)

def sum_flow_field(dk: caliperpy.Gisdk, flow_bin: str, field: str) -> float:
    """Open a flow table .bin, sum one field, return the total."""
    vw = dk.OpenTable("FlowStats", "FFB", [flow_bin, None])
    v  = dk.GetDataVector(vw, field, None)
    total = dk.VectorStatistic(v, "Sum", None)
    dk.CloseView(vw)
    return total

def close_all_views(dk):
    try:
        views = dk.GetViews(None)[0] or []
        closed = 0
        for vw in (views or []):
            # Skip internal TransCAD views
            if vw.lower().startswith("table_"):
                continue
            try:
                dk.CloseView(vw)
                closed += 1
            except:
                pass
        if closed:
            print(f"  Closed {closed} open views")
    except:
        pass


def _delete_if_exists(path: str, dk=None):
    """Delete file + companion descriptor."""
    for f in [path, path.replace(".bin", ".dcb"),
              path.replace(".mtx", ".mtx.lock")]:
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"  Deleted: {f}")
            except PermissionError:
                print(f"  WARNING: could not delete {f} — still locked")


def get_dk(dk: caliperpy.Gisdk = None) -> caliperpy.Gisdk:
    """Return a live TransCAD connection, reconnecting if needed."""
    try:
        # Send a cheap probe call; if it throws, reconnect
        dk.GetViews(None)
        return dk
    except Exception:
        print("TransCAD connection lost — reconnecting...")
        fresh_dk = caliperpy.TransCAD.connect(
            log_file="amarillo_model.log")
        print("Connected to TransCAD")
        return fresh_dk


def open_taz(dk, taz_bin: str = "taz.bin") -> str:
    view_info = dk.GetViews(None)
    if view_info and view_info[0]:
        for vname in view_info[0]:
            if vname.lower().startswith("table_"):
                continue
            if vname.lower().startswith("flow_"):
                continue
            try:
                dk.CloseView(vname)
            except:
                pass
    taz_vw = dk.OpenTable("TAZ", "FFB", [os.path.join(MODEL_DIR, taz_bin), None])
    print(f"  TAZ view: '{taz_vw}'")
    return taz_vw


def require_connection(dk: caliperpy.Gisdk) -> bool:
    """Raise a clear error if TransCAD is not reachable."""
    try:
        result = dk.RunMacro("G30 Tutorial Folder")
        print(f"TransCAD alive. Tutorial folder: {result}")
        return True
    except Exception as e:
        print(f"TransCAD NOT reachable: {e}")
        print("→ Run the disconnect/reload/connect cell above first.")
        return False


def view_bin(dk: caliperpy.Gisdk, path_or_view: str, rows: int = None) -> "pd.DataFrame":
    """
    View a .bin file as a DataFrame — works whether the file is open in
    TransCAD or not.

    Pass either:
      - a file path:  view_bin(os.path.join(MODEL_DIR, "Script_Productions.bin"))
      - a view name:  view_bin(taz_vw)   ← already open, no file access

    Strategy:
      1. If the argument looks like a view name already open in TransCAD,
         use GetDataFrameFromView directly (live data, no file lock issues).
      2. If it looks like a file path, first check if it's already open as
         a view (find it via GetViews), use that view if so.
      3. Otherwise open it fresh with OpenTable, read it, then close it.
    """
    import os

    def _df_from_view(vw):
        df = dk.GetDataFrameFromView(vw, None)   # None = all fields
        print(f"  View : '{vw}'")
        print(f"  Shape: {len(df):,} rows × {len(df.columns)} columns")
        print(f"  Cols : {list(df.columns)}\n")
        return df.head(rows) if rows else df

    # ── Is it already an open view name? ─────────────────────────────────
    try:
        view_info  = dk.GetViews(None)
        open_views = view_info[0] if view_info and view_info[0] else []
    except Exception:
        open_views = []

    # Direct view name passed in
    if path_or_view in open_views:
        return _df_from_view(path_or_view)

    # ── It's a file path — check if already open under any view name ─────
    if os.path.exists(path_or_view):
        # GetViews returns all open view names; try each to find a matching file
        for vw in open_views:
            try:
                # GetViewTableInfo returns the file path for a view
                info = dk.GetViewTableInfo(vw)
                if info and os.path.normcase(info[0]) == os.path.normcase(path_or_view):
                    print(f"  '{path_or_view}' is open as view '{vw}' — reading live")
                    return _df_from_view(vw)
            except Exception:
                continue

        # Not currently open — read directly from disk (safe, file is not locked)
        try:
            df = dk.GetDataFrameFromBin(path_or_view, False)
            print(f"  File : {path_or_view}")
            print(f"  Shape: {len(df):,} rows × {len(df.columns)} columns")
            print(f"  Cols : {list(df.columns)}\n")
            return df.head(rows) if rows else df
        except Exception:
            # Last resort: open, read, close
            vw = dk.OpenTable("_viewer_tmp", "FFB", [path_or_view, None])
            df = _df_from_view(vw)
            dk.CloseView(vw)
            return df

    raise ValueError(
        f"'{path_or_view}' is neither an open view name nor an existing file path."
    )


def drop_bin_columns(dk, path_or_view: str, columns_to_drop: list):
    """
    Delete columns from a .bin file.

    Uses ModifyTable() which drops any field not included in the
    field_info_array. Requires the table to not be part of any joined view.

    Parameters
    ----------
    path_or_view : file path (os.path.join(MODEL_DIR, "file.bin")) or already-open view name
    columns_to_drop : list of field name strings to remove

    Example
    -------
    drop_bin_columns(os.path.join(MODEL_DIR, "Script_Productions.bin"), ["HBW_P", "NHB_P"])
    drop_bin_columns(taz_vw, ["HBW_A", "HBNW_A"])
    """
    import os

    # ── Resolve to a view name ────────────────────────────────────────────
    # ModifyTable needs an open view; track whether WE opened it so we
    # can close it afterward.
    we_opened = False

    if os.path.exists(str(path_or_view)):
        # It's a file path — check it isn't part of a joined view
        # (ModifyTable will error if it is)
        vw = dk.OpenTable("_mod_tmp", "FFB", [path_or_view, None])
        we_opened = True
    else:
        # Assume it's already an open view name
        vw = path_or_view

    try:
        # ── Get current table structure ───────────────────────────────────
        # {"Include Original": "True"} adds element [11] = original field name,
        # which ModifyTable needs to match existing fields correctly.
        struct = dk.GetTableStructure(vw, {"Include Original": "True"})

        to_drop = set(columns_to_drop)

        # Validate — warn about any names not found
        existing = [s[0] for s in struct]
        not_found = to_drop - set(existing)
        if not_found:
            print(f"  WARNING: columns not found (skipped): {not_found}")

        # Build new structure — omit the fields we want to drop.
        # ModifyTable drops any field absent from the array.
        new_struct = [list(s) for s in struct if s[0] not in to_drop]
        if len(new_struct) == len(struct):
            print("  No matching columns found — nothing changed.")
            return

        dropped = [s[0] for s in struct if s[0] in to_drop]
        print(f"  Dropping: {dropped}")
        print(f"  Keeping : {[s[0] for s in new_struct]}")

        # ── Apply the modification ────────────────────────────────────────
        dk.ModifyTable(vw, new_struct)
        print(f"  Done — {len(dropped)} column(s) removed.")

    finally:
        if we_opened:
            dk.CloseView(vw)


def add_field(dk, vw: str, field_name: str,
              field_type: str = "Real", width: int = 12, decimals: int = 4):
    """
    Add a field to an open .bin view using ModifyTable().
    original_name = None in the last element signals a new field.
    """
    struct = dk.GetTableStructure(vw, {"Include Original": "True"})

    # Check field doesn't already exist
    if any(s[0] == field_name for s in struct):
        return

    # Convert tuple-of-tuples → list-of-lists so we can append
    struct_list = [list(s) for s in struct]

    new_field = [field_name, field_type, width, decimals,
                 False, None, None, None, None, None, None, None]

    dk.ModifyTable(vw, struct_list + [new_field])