import logging
import sys
from typing import List, Tuple, Union

import pulp

from utils.manage_paths import format_data_file, format_plot_file, format_statistic_file
from utils.manage_statistics import checking_instances, save_statistics
from utils.mip_utils import (
    check_mip_admissable_timeout,
    check_mip_solver_exists,
    configure_cplex_solver,
    configure_mosek_solver,
    parse_mip_argument,
)
from utils.solution_log import print_logging
from utils.smt_utils import extract_input_from_txt
from utils.plot import plot_solution
from utils.minizinc_solver import compute_solve_time, run_minizinc
from utils.types import (
    SOLUTION_ADMISSABLE,
    InputMode,
    ModelType,
    Solution,
    SolverMinizinc,
    SolverMIP,
    RunType,
    StatusEnum,
)

from create_model import build_pulp_model, build_pulp_rotation_model

run_type: RunType = RunType.MIP


def run_mip_solver(
    input_name: str, model_type: ModelType, solver: SolverMIP, timeout: int
):
    solver_verbose = False

    sol = Solution()
    data_file = format_data_file(input_name, InputMode.TXT)
    # TODO change to take only data_file
    W, N, widths, heights = extract_input_from_txt(
        data_file.rsplit("/", maxsplit=1)[0] + "/{file}",
        data_file.rsplit("/", maxsplit=1)[1],
    )

    sol.input_name = input_name
    sol.width = W
    sol.n_circuits = N
    sol.circuits = [[widths[i], heights[i]] for i in range(N)]

    # Model selection
    if model_type == ModelType.BASE:
        prob = build_pulp_model(W, N, widths, heights)
    elif model_type == ModelType.ROTATION:
        prob = build_pulp_rotation_model(W, N, widths, heights)
    else:
        raise BaseException("Model type not available")

    if solver == SolverMIP.CPLEX:
        solver = configure_cplex_solver(timeout)
    elif solver == SolverMIP.MOSEK:
        solver = configure_mosek_solver(timeout)
    else:
        raise BaseException("Solver not available")

    try:
        prob.solve(solver)
    except BaseException as err:
        logging.error(f"Unexpected {err}")
        sol.status = StatusEnum.ERROR
        return sol

    sol.status = StatusEnum(prob.sol_status)
    sol.solve_time = compute_solve_time(prob.solutionTime)

    if SOLUTION_ADMISSABLE(sol.status):
        sol.height = round(pulp.value(prob.objective))
        rotation = [False] * N
        coords = {"x": [None] * N, "y": [None] * N}
        for v in prob.variables():
            # print(f"{v.name}: {v.value()}")
            if str(v.name).startswith("coord_x"):
                coords["x"][int(v.name[8:])] = round(v.varValue)
            elif str(v.name).startswith("coord_y"):
                coords["y"][int(v.name[8:])] = round(v.varValue)
            elif str(v.name).startswith("rot"):
                rotation[int(v.name[4:])] = bool(round(v.varValue))

        sol.coords = coords

        # FIXME use rotation from solver
        sol.rotation = rotation if len(rotation) > 0 else None

    return sol


def compute_solution(
    input_name: str,
    model_type: ModelType,
    solver: SolverMIP,
    timeout: int,
    verbose: bool,
):
    # plot path
    plot_file = format_plot_file(run_type, input_name, model_type)

    if solver == SolverMIP.MINIZINC:
        mz_solver = SolverMinizinc.CHUFFED
        free_search = True

        sol = run_minizinc(
            input_name,
            run_type,
            model_type,
            mz_solver,
            timeout,
            free_search,
        )
    elif solver == SolverMIP.MOSEK or solver == SolverMIP.CPLEX:
        sol = run_mip_solver(input_name, model_type, solver, timeout)

    print_logging(sol, verbose)
    plot_solution(sol, plot_file)

    return sol


def compute_tests(
    test_instances: Union[Tuple[int], List[int]],
    model_type: ModelType,
    solver: SolverMIP,
    timeout: int,
    verbose: bool,
):
    test_iterator = checking_instances(test_instances)
    statistics_path = format_statistic_file(
        run_type, test_instances, model_type, solver=solver.value
    )

    for i in test_iterator:
        sol = compute_solution(f"ins-{i}", model_type, solver, timeout, verbose)
        save_statistics(statistics_path, sol)
        print(
            f"\n- Computed instance {i}: {sol.status.name} {f'in time {sol.solve_time}' if SOLUTION_ADMISSABLE(sol.status) else ''}"
        )


if __name__ == "__main__":
    parser_args = parse_mip_argument()
    input_name: str = parser_args["instance"]
    model_type: ModelType = ModelType(parser_args["model"])
    solver: SolverMIP = SolverMIP(parser_args["solver"])
    timeout: int = parser_args["timeout"]
    verbose: bool = parser_args["verbose"]
    save_stats: bool = parser_args["statistics"]

    # Check if the solver is installed in the user's system
    if not check_mip_solver_exists(solver):
        logging.error(f"{solver.name} not available in the current system")
        sys.exit(2)

    # Check if the timeout is out of range
    if not check_mip_admissable_timeout(timeout):
        logging.error("Timeout out of range")
        sys.exit(2)

    if save_stats:
        # TODO pass instances through cmd line
        test_instances = (1, 5)
        compute_tests(test_instances, model_type, solver, timeout, verbose)
    else:
        compute_solution(input_name, model_type, solver, timeout, verbose)
