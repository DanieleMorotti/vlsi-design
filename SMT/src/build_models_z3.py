from os.path import join as join_path
import math, time
import z3

import sys
sys.path.append("./")

from utils.smt_utils import extract_input_from_txt, z3_parse_solution, get_w_and_h_from_txt, check_smt_parameters
from utils.smt_utils import offline_omt
from utils.types import SolverSMT, LogicSMT, ModelType
from utils.plot import plot_cmap

root_path = "./SMT"
plot_path = join_path(root_path, "out/plots/{model}/{file}")
statistics_path = join_path(root_path, "out/statistics/{model}/{file}.csv")
data_path = {
    "dzn": "./vlsi-instances/dzn-instances/{file}",
    "txt": "./vlsi-instances/txt-instances/{file}",
}


# We append to the string all the script to avoid writing it manually
def build_SMTLIB_model(W, N, widths, heights, logic: LogicSMT="LIA"):
    # Lower and upper bounds for the height
    l_low = math.ceil(sum([widths[i]*heights[i] for i in range(N)]) / W)
    l_up = sum(heights)
    lines = []

    # Options
    lines.append(f"(set-logic {logic})")

    # Variables declaration
    lines += [f"(declare-fun coord_x{i} () Int)" for i in range(N)]
    lines += [f"(declare-fun coord_y{i} () Int)" for i in range(N)]
    lines.append("(declare-fun l () Int)")

    # Domain of variables
    lines += [f"(assert (and (>= coord_x{i} 0) (<= coord_x{i} {W-min(widths)})))" for i in range(N)]
    lines += [f"(assert (and (>= coord_y{i} 0) (<= coord_y{i} {l_up-min(heights)})))" for i in range(N)]
    lines.append(f"(assert (and (>= l {l_low}) (<= l {l_up})))")


    # Non-Overlap constraints, at least one needs to be satisfied
    for i in range(N):
        for j in range(N):
            if i < j:
                lines.append(f"(assert (or (<= (+ coord_x{i} {widths[i]}) coord_x{j}) "
                                         f"(<= (+ coord_y{i} {heights[i]}) coord_y{j}) "
                                         f"(>= (- coord_x{i} {widths[j]}) coord_x{j}) "
                                         f"(>= (- coord_y{i} {heights[j]}) coord_y{j})))"
                )

    # Boundary constraints
    lines += [f"(assert (and (<= (+ coord_x{i} {widths[i]}) {W}) (<= (+ coord_y{i} {heights[i]}) l)))" for i in range(N)]

    
    # Cumulative constraints 
    for w in widths:
        sum_var = [f"(ite (and (<= coord_y{i} {w}) (< {w} (+ coord_y{i} {heights[i]}))) {widths[i]} 0)" for i in range(N)]
        lines.append(f"(assert (<= (+ {' '.join(sum_var)}) {W}))")

    for h in heights:
        sum_var = [f"(ite (and (<= coord_x{i} {h}) (< {h} (+ coord_x{i} {widths[i]}))) {heights[i]} 0)" for i in range(N)]
        lines.append(f"(assert (<= (+ {' '.join(sum_var)}) l))")

    # Symmetry breaking same size 
    for i in range(N):
        for j in range(N):
            if i < j:
                lines.append(f"(assert (ite (and (= {widths[i]} {widths[j]}) (= {heights[i]} {heights[j]})) (<= coord_x{i} coord_x{j}) true))")
    

    # Symmetry breaking that inserts the circuit with the maximum area in (0, 0)
    areas = [widths[i]*heights[i] for i in range(N)]
    max_area_ind = areas.index(max(areas))
    lines.append(f"(assert (= coord_x{max_area_ind} 0))")
    lines.append(f"(assert (= coord_y{max_area_ind} 0))")

    lines.append("(check-sat)")
    lines.append("(get-model)")
    
    with open(f"{root_path}/src/model.smt2", "w+") as f:
        for line in lines:
            f.write(line + '\n')


if __name__ == "__main__":
    params = check_smt_parameters(data_path['txt'])
    solver_name = params['solver_name']
    logic = params['logic']
    instance_file = params['instance_val']
    timeout = params['timeout']
    rotation = params['rotation']
    verbose = params['verbose']

    plot_file = plot_path.format(model=ModelType.BASE.value, file=instance_file.split(".")[0])

    W, N, widths, heights = extract_input_from_txt(data_path["txt"], instance_file)

    if not rotation:
        model_type = "base"
        build_SMTLIB_model(W, N, widths, heights, logic=LogicSMT.LIA.value)
    else:
        model_type = "rotation"
        print("Not supported yet")
        #build_SMTLIB_model_rot(W, N, widths, heights, logic=LogicSMT.LIA.value)

    if solver_name != 'z3':
        print("Work in progress")
    else:
        solver = z3.Solver()
        solver.set(timeout=timeout*1000)
        formula = z3.parse_smt2_file(f"{root_path}/src/model.smt2")
        solver.add(formula)

        l_low = math.ceil(sum([widths[i]*heights[i] for i in range(N)]) / W)
        
        solution = offline_omt(solver, l_low, sum(heights), timeout, verbose)

        if len(solution[0].keys()) != 0:
            l, coord_x, coord_y = solution[0]['l'], solution[0]['coord_x'], solution[0]['coord_y']
            sol_time = solution[1]
            print(f"Minimum found l is {l}, found in {round(sol_time,4)} seconds.")
            plot_cmap(
                W, l, N, get_w_and_h_from_txt(instance_file), {'x': coord_x, 'y': coord_y},
                    plot_file, rotation=None, cmap_name="Set3"
            )
        else:
            print(f"Something goes wrong.")
            sys.exit(1)         